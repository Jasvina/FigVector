from __future__ import annotations

import json
from pathlib import Path

from .analysis import RasterAnalyzer
from .config import resolve_profile
from .export_drawio import export_drawio
from .export_svg import export_svg
from .models import SceneGraph
from .ocr import OCRConfig, run_ocr
from .png import read_png
from .relations import infer_relations


def vectorize_png(
    input_path: str | Path,
    output_path: str | Path,
    report_path: str | Path | None = None,
    drawio_path: str | Path | None = None,
    profile: str = "real",
    background_threshold: int | None = None,
    min_area: int | None = None,
    color_quantization: int | None = None,
    ocr: OCRConfig | None = None,
) -> SceneGraph:
    resolved = resolve_profile(
        profile,
        background_threshold=background_threshold,
        min_area=min_area,
        color_quantization=color_quantization,
    )
    image = read_png(input_path)
    analyzer = RasterAnalyzer(
        background_threshold=resolved.background_threshold,
        min_area=resolved.min_area,
        color_quantization=resolved.color_quantization,
    )
    background, primitives = analyzer.detect_primitives(image)
    scene = SceneGraph(width=image.width, height=image.height, background=background, primitives=primitives)
    for index, primitive in enumerate(scene.primitives, start=1):
        primitive.metadata["id"] = f"primitive-{index}"
    scene.texts = run_ocr(input_path, ocr)
    for index, text_block in enumerate(scene.texts, start=1):
        text_block.metadata["id"] = f"text-{index}"
    scene.relations = infer_relations(scene)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(export_svg(scene), encoding="utf-8")

    if drawio_path is not None:
        drawio = Path(drawio_path)
        drawio.parent.mkdir(parents=True, exist_ok=True)
        drawio.write_text(export_drawio(scene), encoding="utf-8")

    if report_path is not None:
        report = Path(report_path)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(scene.to_dict(), indent=2), encoding="utf-8")

    return scene
