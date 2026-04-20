from __future__ import annotations

import csv
import json
import shutil
import subprocess
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from .models import BoundingBox, TextBlock


@dataclass(frozen=True)
class OCRConfig:
    backend: str = "none"
    sidecar_path: str | None = None
    min_confidence: float = 0.45


class OCRBackendError(RuntimeError):
    pass


def run_ocr(input_path: str | Path, config: OCRConfig | None = None) -> list[TextBlock]:
    config = config or OCRConfig()
    backend = config.backend.lower().strip()
    if backend == "none":
        return []
    if backend == "sidecar-json":
        return _load_sidecar(input_path, config)
    if backend == "tesseract-cli":
        return _run_tesseract(input_path, config)
    raise OCRBackendError(f"Unsupported OCR backend: {config.backend}")


def _load_sidecar(input_path: str | Path, config: OCRConfig) -> list[TextBlock]:
    input_path = Path(input_path)
    sidecar_path = Path(config.sidecar_path) if config.sidecar_path else input_path.with_suffix(".ocr.json")
    if not sidecar_path.exists():
        return []

    payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    texts = payload.get("texts", [])
    return [_text_block_from_dict(item, source="sidecar-json") for item in texts]


def _run_tesseract(input_path: str | Path, config: OCRConfig) -> list[TextBlock]:
    executable = shutil.which("tesseract")
    if executable is None:
        raise OCRBackendError("tesseract was not found on PATH")

    command = [executable, str(input_path), "stdout", "tsv"]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise OCRBackendError(completed.stderr.strip() or "tesseract exited with an error")

    reader = csv.DictReader(StringIO(completed.stdout), delimiter="\t")
    texts: list[TextBlock] = []
    for row in reader:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        confidence_text = row.get("conf") or "-1"
        try:
            confidence = max(0.0, float(confidence_text) / 100.0)
        except ValueError:
            confidence = 0.0
        if confidence < config.min_confidence:
            continue
        left = int(float(row.get("left") or 0))
        top = int(float(row.get("top") or 0))
        width = int(float(row.get("width") or 0))
        height = int(float(row.get("height") or 0))
        if width <= 0 or height <= 0:
            continue
        texts.append(
            TextBlock(
                text=text,
                bbox=BoundingBox(x=left, y=top, width=width, height=height),
                confidence=round(confidence, 3),
                source="tesseract-cli",
                metadata={"level": row.get("level", "")},
            )
        )
    return texts


def _text_block_from_dict(item: dict, source: str) -> TextBlock:
    bbox = item.get("bbox", {})
    return TextBlock(
        text=str(item.get("text", "")),
        bbox=BoundingBox(
            x=int(bbox.get("x", 0)),
            y=int(bbox.get("y", 0)),
            width=int(bbox.get("width", 0)),
            height=int(bbox.get("height", 0)),
        ),
        confidence=float(item.get("confidence", 1.0)),
        source=source,
        metadata=item.get("metadata", {}),
    )
