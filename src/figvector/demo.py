from __future__ import annotations

import json
from pathlib import Path

from .dataset import write_vectorize_review_html
from .models import RasterImage
from .ocr import OCRConfig
from .pipeline import vectorize_png
from .png import write_png

WHITE = (251, 250, 246, 255)
BLUE = (90, 132, 255, 255)
GREEN = (78, 196, 140, 255)
ORANGE = (255, 174, 86, 255)
INK = (46, 50, 71, 255)
GROUP = (226, 233, 242, 255)
SAND = (248, 223, 143, 255)


def build_demo_assets(output_dir: str | Path, *, variant: str = "basic") -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    spec = _demo_spec(variant)
    png_path = output_dir / f"{spec['stem']}-input.png"
    ocr_path = output_dir / f"{spec['stem']}-input.ocr.json"
    svg_path = output_dir / f"{spec['stem']}-output.svg"
    report_path = output_dir / f"{spec['stem']}-report.json"
    drawio_path = output_dir / f"{spec['stem']}-output.drawio"
    review_path = output_dir / f"{spec['stem']}-review.html"

    write_png(png_path, spec["image"]())
    ocr_path.write_text(json.dumps(spec["ocr"](), indent=2), encoding="utf-8")
    scene = vectorize_png(
        png_path,
        svg_path,
        report_path=report_path,
        drawio_path=drawio_path,
        ocr=OCRConfig(backend="sidecar-json", sidecar_path=str(ocr_path)),
    )
    write_vectorize_review_html(
        review_path,
        input_path=png_path,
        svg_path=svg_path,
        report_path=report_path,
        drawio_path=drawio_path,
        scene=scene,
        profile="real",
        notes=str(spec.get("notes", "")),
    )
    return {
        "png": png_path,
        "ocr": ocr_path,
        "svg": svg_path,
        "report": report_path,
        "drawio": drawio_path,
        "review": review_path,
    }


def _demo_spec(variant: str) -> dict[str, object]:
    if variant == "nested":
        return {
            "stem": "nested-demo",
            "image": _nested_demo_image,
            "ocr": _nested_demo_ocr_sidecar,
            "notes": "Nested/group regression sample covering container regions, internal nodes, and connector disambiguation.",
        }
    if variant != "basic":
        raise ValueError(f"Unsupported demo variant: {variant}")
    return {
        "stem": "demo",
        "image": _basic_demo_image,
        "ocr": _basic_demo_ocr_sidecar,
        "notes": "Baseline clean pipeline sample covering boxes, arrows, a polyline, and text labels.",
    }


def _basic_demo_image() -> RasterImage:
    width, height = 760, 420
    pixels = [[WHITE for _ in range(width)] for _ in range(height)]

    _rounded_rect(pixels, 60, 90, 180, 120, 18, BLUE)
    _rounded_rect(pixels, 300, 90, 180, 120, 18, GREEN)
    _rounded_rect(pixels, 540, 90, 150, 120, 18, ORANGE)
    _circle(pixels, 380, 300, 56, (122, 186, 255, 255))
    _line(pixels, 240, 150, 300, 150, INK, 6)
    _line(pixels, 480, 150, 540, 150, INK, 6)
    _arrow_head(pixels, 300, 150, "right", INK)
    _arrow_head(pixels, 540, 150, "right", INK)
    _line(pixels, 380, 210, 380, 244, INK, 6)
    _arrow_head(pixels, 380, 244, "down", INK)
    _line(pixels, 437, 300, 500, 300, INK, 6)
    _line(pixels, 500, 300, 500, 350, INK, 6)
    _line(pixels, 500, 350, 590, 350, INK, 6)
    _rounded_rect(pixels, 590, 315, 100, 70, 12, (248, 223, 143, 255))
    return RasterImage(width=width, height=height, pixels=pixels)


def _basic_demo_ocr_sidecar() -> dict[str, object]:
    return {
        "texts": [
            {"text": "Prompt", "bbox": {"x": 100, "y": 130, "width": 90, "height": 24}, "confidence": 0.99},
            {"text": "Encoder", "bbox": {"x": 340, "y": 130, "width": 100, "height": 24}, "confidence": 0.99},
            {"text": "Output", "bbox": {"x": 575, "y": 130, "width": 90, "height": 24}, "confidence": 0.99},
            {"text": "Signal", "bbox": {"x": 347, "y": 293, "width": 75, "height": 24}, "confidence": 0.98},
            {"text": "Editable", "bbox": {"x": 600, "y": 337, "width": 90, "height": 24}, "confidence": 0.98},
        ]
    }


def _nested_demo_image() -> RasterImage:
    width, height = 880, 460
    pixels = [[WHITE for _ in range(width)] for _ in range(height)]

    _rounded_rect(pixels, 220, 60, 420, 280, 24, GROUP)
    _rounded_rect(pixels, 40, 130, 140, 90, 18, ORANGE)
    _rounded_rect(pixels, 270, 120, 120, 80, 18, BLUE)
    _rounded_rect(pixels, 450, 120, 120, 80, 18, GREEN)
    _rounded_rect(pixels, 360, 250, 140, 70, 16, SAND)
    _rounded_rect(pixels, 700, 250, 120, 70, 16, (122, 186, 255, 255))

    _line(pixels, 180, 175, 270, 175, INK, 6)
    _arrow_head(pixels, 270, 175, "right", INK)

    _line(pixels, 390, 160, 450, 160, INK, 6)
    _arrow_head(pixels, 450, 160, "right", INK)

    _line(pixels, 570, 160, 620, 160, INK, 6)
    _line(pixels, 620, 160, 620, 285, INK, 6)
    _line(pixels, 620, 285, 500, 285, INK, 6)

    _line(pixels, 500, 285, 700, 285, INK, 6)
    _arrow_head(pixels, 700, 285, "right", INK)

    return RasterImage(width=width, height=height, pixels=pixels)


def _nested_demo_ocr_sidecar() -> dict[str, object]:
    return {
        "texts": [
            {"text": "Input", "bbox": {"x": 82, "y": 162, "width": 60, "height": 24}, "confidence": 0.99},
            {"text": "Workspace", "bbox": {"x": 355, "y": 78, "width": 150, "height": 24}, "confidence": 0.99},
            {"text": "Detect", "bbox": {"x": 295, "y": 150, "width": 75, "height": 24}, "confidence": 0.99},
            {"text": "Refine", "bbox": {"x": 475, "y": 150, "width": 80, "height": 24}, "confidence": 0.99},
            {"text": "Review", "bbox": {"x": 392, "y": 274, "width": 80, "height": 24}, "confidence": 0.99},
            {"text": "Export", "bbox": {"x": 730, "y": 274, "width": 75, "height": 24}, "confidence": 0.99},
        ]
    }


def _rounded_rect(pixels, x, y, width, height, radius, color):
    for row in range(y, y + height):
        for column in range(x, x + width):
            dx = min(column - x, x + width - 1 - column)
            dy = min(row - y, y + height - 1 - row)
            if dx >= radius or dy >= radius:
                pixels[row][column] = color
                continue
            if (dx - radius) ** 2 + (dy - radius) ** 2 <= radius ** 2:
                pixels[row][column] = color


def _circle(pixels, cx, cy, radius, color):
    for row in range(cy - radius, cy + radius + 1):
        for column in range(cx - radius, cx + radius + 1):
            if 0 <= row < len(pixels) and 0 <= column < len(pixels[0]):
                if (column - cx) ** 2 + (row - cy) ** 2 <= radius ** 2:
                    pixels[row][column] = color


def _line(pixels, x1, y1, x2, y2, color, thickness):
    steps = max(abs(x2 - x1), abs(y2 - y1)) + 1
    for step in range(steps):
        t = step / max(1, steps - 1)
        x = round(x1 + (x2 - x1) * t)
        y = round(y1 + (y2 - y1) * t)
        _stamp_circle(pixels, x, y, thickness // 2, color)


def _stamp_circle(pixels, cx, cy, radius, color):
    for row in range(cy - radius, cy + radius + 1):
        for column in range(cx - radius, cx + radius + 1):
            if 0 <= row < len(pixels) and 0 <= column < len(pixels[0]):
                if (column - cx) ** 2 + (row - cy) ** 2 <= radius ** 2:
                    pixels[row][column] = color


def _arrow_head(pixels, x, y, direction, color):
    offsets = []
    if direction == "right":
        offsets = [(0, 0), (-14, -9), (-14, 9)]
    elif direction == "left":
        offsets = [(0, 0), (14, -9), (14, 9)]
    elif direction == "down":
        offsets = [(0, 0), (-9, -14), (9, -14)]
    else:
        offsets = [(0, 0), (-9, 14), (9, 14)]
    _triangle(pixels, [(x + dx, y + dy) for dx, dy in offsets], color)


def _triangle(pixels, points, color):
    (x1, y1), (x2, y2), (x3, y3) = points
    min_x, max_x = min(x1, x2, x3), max(x1, x2, x3)
    min_y, max_y = min(y1, y2, y3), max(y1, y2, y3)
    denominator = ((y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3))
    if denominator == 0:
        return
    for row in range(min_y, max_y + 1):
        for column in range(min_x, max_x + 1):
            if 0 <= row < len(pixels) and 0 <= column < len(pixels[0]):
                a = ((y2 - y3) * (column - x3) + (x3 - x2) * (row - y3)) / denominator
                b = ((y3 - y1) * (column - x3) + (x1 - x3) * (row - y3)) / denominator
                c = 1 - a - b
                if a >= 0 and b >= 0 and c >= 0:
                    pixels[row][column] = color
