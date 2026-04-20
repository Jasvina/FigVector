from __future__ import annotations

import json
from pathlib import Path

from .analysis import RasterAnalyzer
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
    background_threshold: int = 38,
    min_area: int = 32,
    ocr: OCRConfig | None = None,
) -> SceneGraph:
    image = read_png(input_path)
    analyzer = RasterAnalyzer(background_threshold=background_threshold, min_area=min_area)
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
