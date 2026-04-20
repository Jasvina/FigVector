from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

Pixel = tuple[int, int, int, int]


@dataclass(frozen=True)
class BoundingBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def x2(self) -> int:
        return self.x + self.width

    @property
    def y2(self) -> int:
        return self.y + self.height

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)


@dataclass
class RasterImage:
    width: int
    height: int
    pixels: list[list[Pixel]]

    def get(self, x: int, y: int) -> Pixel:
        return self.pixels[y][x]

    def iter_pixels(self) -> Iterable[tuple[int, int, Pixel]]:
        for y, row in enumerate(self.pixels):
            for x, pixel in enumerate(row):
                yield x, y, pixel


@dataclass
class Primitive:
    kind: str
    bbox: BoundingBox
    color: Pixel
    confidence: float
    metadata: dict[str, str | float | int] = field(default_factory=dict)


@dataclass
class Relation:
    source_id: str
    target_id: str
    kind: str
    confidence: float


@dataclass
class SceneGraph:
    width: int
    height: int
    background: Pixel
    primitives: list[Primitive] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "background": list(self.background),
            "primitives": [
                {
                    "kind": primitive.kind,
                    "bbox": {
                        "x": primitive.bbox.x,
                        "y": primitive.bbox.y,
                        "width": primitive.bbox.width,
                        "height": primitive.bbox.height,
                    },
                    "color": list(primitive.color),
                    "confidence": primitive.confidence,
                    "metadata": primitive.metadata,
                }
                for primitive in self.primitives
            ],
            "relations": [
                {
                    "source_id": relation.source_id,
                    "target_id": relation.target_id,
                    "kind": relation.kind,
                    "confidence": relation.confidence,
                }
                for relation in self.relations
            ],
        }
