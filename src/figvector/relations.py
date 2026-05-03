from __future__ import annotations

from math import dist

from .models import BoundingBox, Primitive, Relation, SceneGraph, TextBlock


CONNECTOR_KINDS = {"line", "arrow", "polyline"}
SHAPE_KINDS = {"rectangle", "ellipse", "region"}
REGION_DISTANCE_PENALTY = 32.0
CONTAINER_PADDING = 4.0


def infer_relations(scene: SceneGraph, max_distance: float = 48.0) -> list[Relation]:
    shapes = [primitive for primitive in scene.primitives if primitive.kind in SHAPE_KINDS]
    relations: list[Relation] = []

    for primitive in scene.primitives:
        if primitive.kind not in CONNECTOR_KINDS:
            continue

        start, end = connector_endpoints(primitive)
        source, source_distance = _nearest_shape(shapes, start)
        target, target_distance = _nearest_shape(shapes, end)

        if source is None or target is None:
            continue
        if source is target:
            continue
        if source_distance > max_distance or target_distance > max_distance:
            continue

        source_id = str(source.metadata["id"])
        target_id = str(target.metadata["id"])
        primitive.metadata["connects_from"] = source_id
        primitive.metadata["connects_to"] = target_id

        relation_kind = "flows_to" if primitive.kind == "arrow" else "linked_to"
        confidence = round(max(0.35, primitive.confidence - ((source_distance + target_distance) / 160.0)), 2)
        relations.append(
            Relation(
                source_id=source_id,
                target_id=target_id,
                kind=relation_kind,
                confidence=confidence,
            )
        )

    relations.extend(infer_text_relations(scene, shapes))
    relations.extend(infer_group_relations(scene))
    return relations


def connector_endpoints(primitive: Primitive) -> tuple[tuple[float, float], tuple[float, float]]:
    bbox = primitive.bbox
    if primitive.kind == "polyline":
        points = primitive.metadata.get("points", [])
        if isinstance(points, list) and len(points) >= 2:
            start = points[0]
            end = points[-1]
            return (float(start[0]), float(start[1])), (float(end[0]), float(end[1]))

    if primitive.kind == "arrow":
        direction = str(primitive.metadata.get("direction", "right"))
        if direction == "left":
            y = bbox.y + bbox.height / 2.0
            return (bbox.x2, y), (bbox.x, y)
        if direction == "up":
            x = bbox.x + bbox.width / 2.0
            return (x, bbox.y2), (x, bbox.y)
        if direction == "down":
            x = bbox.x + bbox.width / 2.0
            return (x, bbox.y), (x, bbox.y2)
        y = bbox.y + bbox.height / 2.0
        return (bbox.x, y), (bbox.x2, y)

    if bbox.width >= bbox.height:
        y = bbox.y + bbox.height / 2.0
        return (bbox.x, y), (bbox.x2, y)
    x = bbox.x + bbox.width / 2.0
    return (x, bbox.y), (x, bbox.y2)


def _nearest_shape(shapes: list[Primitive], point: tuple[float, float]) -> tuple[Primitive | None, float]:
    return _select_shape_for_point(shapes, point, prefer_specific_within=REGION_DISTANCE_PENALTY)


def _distance_to_bbox(point: tuple[float, float], primitive: Primitive) -> float:
    x, y = point
    bbox = primitive.bbox
    clamped_x = min(max(x, bbox.x), bbox.x2)
    clamped_y = min(max(y, bbox.y), bbox.y2)
    return dist((x, y), (clamped_x, clamped_y))


def infer_text_relations(scene: SceneGraph, shapes: list[Primitive], max_distance: float = 72.0) -> list[Relation]:
    relations: list[Relation] = []
    for text_block in scene.texts:
        target, target_distance = _nearest_shape_for_text(shapes, text_block)
        if target is None or target_distance > max_distance:
            continue
        text_id = str(text_block.metadata["id"])
        target_id = str(target.metadata["id"])
        text_block.metadata["label_for"] = target_id
        relations.append(
            Relation(
                source_id=text_id,
                target_id=target_id,
                kind="labels",
                confidence=round(max(0.35, text_block.confidence - (target_distance / 160.0)), 2),
            )
        )
    return relations


def infer_group_relations(scene: SceneGraph) -> list[Relation]:
    regions = [primitive for primitive in scene.primitives if _is_grouping_region(primitive)]
    if not regions:
        return []

    relations: list[Relation] = []
    for member in scene.primitives:
        container = _smallest_containing_region(regions, member)
        if container is None:
            continue
        if container.metadata.get("id") == member.metadata.get("id"):
            continue

        container_id = str(container.metadata["id"])
        member_id = str(member.metadata["id"])
        member.metadata["group_with"] = container_id
        confidence = round(
            min(
                0.92,
                max(
                    0.45,
                    container.confidence - 0.03 + (_containment_ratio(container.bbox, member.bbox) * 0.2),
                ),
            ),
            2,
        )
        relations.append(
            Relation(
                source_id=container_id,
                target_id=member_id,
                kind="group_with",
                confidence=confidence,
            )
        )
    return relations


def _nearest_shape_for_text(shapes: list[Primitive], text_block: TextBlock) -> tuple[Primitive | None, float]:
    center = text_block.bbox.center
    return _select_shape_for_point(shapes, center, prefer_specific_within=0.0)


def _select_shape_for_point(
    shapes: list[Primitive],
    point: tuple[float, float],
    *,
    prefer_specific_within: float,
) -> tuple[Primitive | None, float]:
    contained = [primitive for primitive in shapes if _bbox_contains_point(primitive, point)]
    candidates = sorted(
        ((primitive, _distance_to_bbox(point, primitive)) for primitive in shapes),
        key=lambda item: (item[1], *_shape_specificity_key(item[0])),
    )
    if not candidates:
        return None, float("inf")

    if contained:
        contained_non_region = [primitive for primitive in contained if primitive.kind != "region"]
        if contained_non_region:
            contained_non_region.sort(key=_shape_specificity_key)
            return contained_non_region[0], 0.0

        contained.sort(key=_shape_specificity_key)
        best_contained = contained[0]
        if prefer_specific_within <= 0:
            return best_contained, 0.0

        for primitive, distance in candidates[1:]:
            if primitive.kind == "region":
                continue
            if distance <= prefer_specific_within:
                return primitive, distance
        return best_contained, 0.0

    best_primitive, best_distance = candidates[0]
    if best_primitive.kind == "region" and prefer_specific_within > 0:
        for primitive, distance in candidates[1:]:
            if primitive.kind == "region":
                continue
            if distance <= best_distance + prefer_specific_within:
                return primitive, distance
    return best_primitive, best_distance


def _shape_specificity_key(primitive: Primitive) -> tuple[int, int, int, int]:
    bbox = primitive.bbox
    area = bbox.width * bbox.height
    return (_shape_kind_rank(primitive.kind), area, bbox.y, bbox.x)


def _shape_kind_rank(kind: str) -> int:
    return 1 if kind == "region" else 0


def _bbox_contains_point(primitive: Primitive, point: tuple[float, float]) -> bool:
    x, y = point
    bbox = primitive.bbox
    return bbox.x <= x <= bbox.x2 and bbox.y <= y <= bbox.y2


def _smallest_containing_region(regions: list[Primitive], bbox: tuple[int, int, int, int] | Primitive) -> Primitive | None:
    exclude_id = None
    if isinstance(bbox, Primitive):
        child_bbox = bbox.bbox
        exclude_id = str(bbox.metadata.get("id", "")).strip() or None
    else:
        child_bbox = _bbox_from_tuple(bbox)

    candidates = [
        region
        for region in regions
        if _bbox_contains_bbox(region.bbox, child_bbox, padding=CONTAINER_PADDING)
        and (exclude_id is None or str(region.metadata.get("id", "")).strip() != exclude_id)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda primitive: (primitive.bbox.width * primitive.bbox.height, primitive.bbox.y, primitive.bbox.x))
    return candidates[0]


def _bbox_contains_bbox(
    container: tuple[int, int, int, int] | Primitive | BoundingBox,
    child: tuple[int, int, int, int] | Primitive | BoundingBox,
    *,
    padding: float = 0.0,
) -> bool:
    container_bbox = _coerce_bbox(container)
    child_bbox = _coerce_bbox(child)
    return (
        child.x >= container_bbox.x - padding
        and child.y >= container_bbox.y - padding
        and child.x2 <= container_bbox.x2 + padding
        and child.y2 <= container_bbox.y2 + padding
    )


def _containment_ratio(container: BoundingBox, child: BoundingBox) -> float:
    overlap_width = max(0, min(container.x2, child.x2) - max(container.x, child.x))
    overlap_height = max(0, min(container.y2, child.y2) - max(container.y, child.y))
    if child.width == 0 or child.height == 0:
        return 0.0
    return (overlap_width * overlap_height) / (child.width * child.height)


def _bbox_from_tuple(bbox: tuple[int, int, int, int]) -> BoundingBox:
    return BoundingBox(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])


def _is_grouping_region(primitive: Primitive) -> bool:
    bbox = primitive.bbox
    return primitive.kind == "region" and bbox.width >= 100 and bbox.height >= 80


def _coerce_bbox(value: tuple[int, int, int, int] | Primitive | BoundingBox) -> BoundingBox:
    if isinstance(value, BoundingBox):
        return value
    if isinstance(value, Primitive):
        return value.bbox
    return _bbox_from_tuple(value)
