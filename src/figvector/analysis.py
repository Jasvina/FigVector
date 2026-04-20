from __future__ import annotations

from collections import Counter, deque, defaultdict
from math import sqrt

from .models import BoundingBox, Primitive, RasterImage


class RasterAnalyzer:
    def __init__(self, background_threshold: int = 38, min_area: int = 32, color_quantization: int = 24):
        self.background_threshold = background_threshold
        self.min_area = min_area
        self.color_quantization = color_quantization

    def detect_primitives(self, image: RasterImage) -> tuple[tuple[int, int, int, int], list[Primitive]]:
        background = _estimate_background(image)
        primitives: list[Primitive] = []

        buckets: dict[tuple[int, int, int], set[tuple[int, int]]] = defaultdict(set)
        for x, y, pixel in image.iter_pixels():
            if not self._is_foreground(pixel, background):
                continue
            bucket = _quantize_color(pixel, self.color_quantization)
            buckets[bucket].add((x, y))

        for bucket, points in buckets.items():
            if len(points) < self.min_area:
                continue
            remaining = set(points)
            while remaining:
                start = remaining.pop()
                component = self._collect_component(remaining, start)
                if len(component) < self.min_area:
                    continue
                primitive = self._classify_component(image, component)
                primitive.metadata["bucket"] = f"rgb({bucket[0]}, {bucket[1]}, {bucket[2]})"
                primitives.append(primitive)

        primitives.sort(key=lambda item: (item.bbox.y, item.bbox.x))
        return background, primitives

    def _is_foreground(self, pixel: tuple[int, int, int, int], background: tuple[int, int, int, int]) -> bool:
        if pixel[3] < 8:
            return False
        distance = sqrt(sum((pixel[idx] - background[idx]) ** 2 for idx in range(3)))
        return distance >= self.background_threshold

    def _collect_component(self, remaining: set[tuple[int, int]], start: tuple[int, int]) -> list[tuple[int, int]]:
        queue = deque([start])
        component: list[tuple[int, int]] = []

        while queue:
            x, y = queue.popleft()
            component.append((x, y))
            for next_x, next_y in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if (next_x, next_y) in remaining:
                    remaining.remove((next_x, next_y))
                    queue.append((next_x, next_y))
        return component

    def _classify_component(self, image: RasterImage, component: list[tuple[int, int]]) -> Primitive:
        xs = [point[0] for point in component]
        ys = [point[1] for point in component]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        bbox = BoundingBox(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)
        area = len(component)
        bbox_area = bbox.width * bbox.height
        fill_ratio = area / max(1, bbox_area)
        color = _average_color(image, component)

        kind = "region"
        confidence = 0.45
        metadata: dict[str, str | float | int] = {
            "area": area,
            "fill_ratio": round(fill_ratio, 3),
        }

        if _looks_like_arrow(component, bbox):
            kind = "arrow"
            confidence = 0.74
            metadata["direction"] = _arrow_direction(component, bbox)
        elif min(bbox.width, bbox.height) <= 8 and max(bbox.width, bbox.height) >= 18:
            kind = "line"
            confidence = 0.82
        elif fill_ratio >= 0.82:
            kind = "rectangle"
            confidence = 0.86
        elif bbox.width > 10 and bbox.height > 10 and 0.45 <= fill_ratio <= 0.81:
            kind = "ellipse"
            confidence = 0.67
        elif max(bbox.width, bbox.height) >= 24:
            kind = "region"
            confidence = 0.55

        metadata["bbox_area"] = bbox_area
        return Primitive(kind=kind, bbox=bbox, color=color, confidence=confidence, metadata=metadata)


def _estimate_background(image: RasterImage) -> tuple[int, int, int, int]:
    sample_points = [
        (0, 0),
        (image.width - 1, 0),
        (0, image.height - 1),
        (image.width - 1, image.height - 1),
        (image.width // 2, 0),
        (image.width // 2, image.height - 1),
        (0, image.height // 2),
        (image.width - 1, image.height // 2),
    ]
    counter = Counter(image.get(x, y) for x, y in sample_points)
    return counter.most_common(1)[0][0]


def _average_color(image: RasterImage, component: list[tuple[int, int]]) -> tuple[int, int, int, int]:
    red = green = blue = alpha = 0
    for x, y in component:
        pixel = image.get(x, y)
        red += pixel[0]
        green += pixel[1]
        blue += pixel[2]
        alpha += pixel[3]
    count = len(component)
    return (
        red // count,
        green // count,
        blue // count,
        alpha // count,
    )


def _quantize_color(pixel: tuple[int, int, int, int], step: int) -> tuple[int, int, int]:
    if step <= 1:
        return (pixel[0], pixel[1], pixel[2])
    return tuple((channel // step) * step for channel in pixel[:3])


def _looks_like_arrow(component: list[tuple[int, int]], bbox: BoundingBox) -> bool:
    if max(bbox.width, bbox.height) < 24:
        return False
    if bbox.width >= bbox.height * 1.8:
        left_spread = _vertical_spread(component, bbox, 0.2)
        right_spread = _vertical_spread(component, bbox, 0.8)
        return max(left_spread, right_spread) >= min(left_spread, right_spread) * 1.8
    if bbox.height >= bbox.width * 1.8:
        top_spread = _horizontal_spread(component, bbox, 0.2)
        bottom_spread = _horizontal_spread(component, bbox, 0.8)
        return max(top_spread, bottom_spread) >= min(top_spread, bottom_spread) * 1.8
    return False


def _arrow_direction(component: list[tuple[int, int]], bbox: BoundingBox) -> str:
    if bbox.width >= bbox.height:
        left_spread = _vertical_spread(component, bbox, 0.2)
        right_spread = _vertical_spread(component, bbox, 0.8)
        return "right" if right_spread >= left_spread else "left"
    top_spread = _horizontal_spread(component, bbox, 0.2)
    bottom_spread = _horizontal_spread(component, bbox, 0.8)
    return "down" if bottom_spread >= top_spread else "up"


def _vertical_spread(component: list[tuple[int, int]], bbox: BoundingBox, anchor: float) -> int:
    x = bbox.x + int((bbox.width - 1) * anchor)
    ys = [point[1] for point in component if abs(point[0] - x) <= 1]
    if not ys:
        return 0
    return max(ys) - min(ys) + 1


def _horizontal_spread(component: list[tuple[int, int]], bbox: BoundingBox, anchor: float) -> int:
    y = bbox.y + int((bbox.height - 1) * anchor)
    xs = [point[0] for point in component if abs(point[1] - y) <= 1]
    if not xs:
        return 0
    return max(xs) - min(xs) + 1
