from __future__ import annotations

from math import dist

from .models import Primitive, Relation, SceneGraph, TextBlock


CONNECTOR_KINDS = {"line", "arrow", "polyline"}
SHAPE_KINDS = {"rectangle", "ellipse", "region"}


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
    best_primitive = None
    best_distance = float("inf")
    for primitive in shapes:
        candidate = _distance_to_bbox(point, primitive)
        if candidate < best_distance:
            best_primitive = primitive
            best_distance = candidate
    return best_primitive, best_distance


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


def _nearest_shape_for_text(shapes: list[Primitive], text_block: TextBlock) -> tuple[Primitive | None, float]:
    center = text_block.bbox.center
    best_primitive = None
    best_distance = float("inf")
    for primitive in shapes:
        candidate = _distance_to_bbox(center, primitive)
        if candidate < best_distance:
            best_primitive = primitive
            best_distance = candidate
    return best_primitive, best_distance
