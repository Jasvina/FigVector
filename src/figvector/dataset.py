from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .eval import evaluate_scene
from .ocr import OCRConfig
from .pipeline import vectorize_png


@dataclass(frozen=True)
class DatasetSample:
    sample_id: str
    png_path: Path
    ocr_sidecar: Path | None = None
    notes: str = ""
    expected: dict[str, object] | None = None


def create_dataset_scaffold(root: str | Path) -> dict[str, Path]:
    root = Path(root)
    inbox = root / "inbox"
    sidecars = root / "ocr_sidecars"
    outputs = root / "outputs"
    inbox.mkdir(parents=True, exist_ok=True)
    sidecars.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)

    manifest_path = root / "manifest.json"
    readme_path = root / "README.md"
    if not manifest_path.exists():
        manifest_path.write_text(json.dumps(_manifest_template(), indent=2), encoding="utf-8")
    if not readme_path.exists():
        readme_path.write_text(_dataset_readme(), encoding="utf-8")
    for directory in (inbox, sidecars, outputs):
        gitkeep = directory / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("", encoding="utf-8")
    return {
        "root": root,
        "manifest": manifest_path,
        "readme": readme_path,
        "inbox": inbox,
        "ocr_sidecars": sidecars,
        "outputs": outputs,
    }


def run_dataset(
    root: str | Path,
    *,
    output_dir: str | Path | None = None,
    ocr_backend: str = "none",
) -> list[dict[str, object]]:
    root = Path(root)
    manifest = _load_manifest(root / "manifest.json")
    destination = Path(output_dir) if output_dir is not None else root / "outputs"
    destination.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, object]] = []
    for sample in manifest:
        sample_dir = destination / sample.sample_id
        svg_path = sample_dir / "output.svg"
        report_path = sample_dir / "report.json"
        drawio_path = sample_dir / "output.drawio"
        scene = vectorize_png(
            sample.png_path,
            svg_path,
            report_path=report_path,
            drawio_path=drawio_path,
            ocr=OCRConfig(backend=ocr_backend, sidecar_path=str(sample.ocr_sidecar) if sample.ocr_sidecar else None),
        )
        evaluation = evaluate_scene(scene, sample.expected)
        results.append(
            {
                "id": sample.sample_id,
                "input": str(sample.png_path),
                "svg": str(svg_path),
                "report": str(report_path),
                "drawio": str(drawio_path),
                "evaluation": evaluation.to_dict() if evaluation is not None else None,
            }
        )

    summary_path = destination / "summary.json"
    summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def _load_manifest(path: Path) -> list[DatasetSample]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    root = path.parent
    samples: list[DatasetSample] = []
    for item in payload.get("samples", []):
        png_path = root / item["png"]
        sidecar = item.get("ocr_sidecar")
        samples.append(
            DatasetSample(
                sample_id=item["id"],
                png_path=png_path,
                ocr_sidecar=(root / sidecar) if sidecar else None,
                notes=item.get("notes", ""),
                expected=item.get("expected"),
            )
        )
    return samples


def evaluate_dataset(root: str | Path, *, output_dir: str | Path | None = None) -> list[dict[str, object]]:
    root = Path(root)
    manifest = _load_manifest(root / "manifest.json")
    source = Path(output_dir) if output_dir is not None else root / "outputs"
    source.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, object]] = []
    for sample in manifest:
        report_path = source / sample.sample_id / "report.json"
        if not report_path.exists():
            results.append(
                {
                    "id": sample.sample_id,
                    "report": str(report_path),
                    "evaluation": {
                        "passed": False,
                        "score": 0.0,
                        "checks": [
                            {
                                "name": "report_exists",
                                "passed": False,
                                "expected": True,
                                "actual": False,
                            }
                        ],
                    },
                }
            )
            continue

        payload = json.loads(report_path.read_text(encoding="utf-8"))
        scene_counts = {
            "primitives": payload.get("primitives", []),
            "texts": payload.get("texts", []),
            "relations": payload.get("relations", []),
        }
        evaluation = _evaluate_payload(scene_counts, sample.expected)
        results.append(
            {
                "id": sample.sample_id,
                "report": str(report_path),
                "evaluation": evaluation,
            }
        )

    summary_path = source / "evaluation-summary.json"
    summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def _manifest_template() -> dict[str, object]:
    return {
        "dataset": "nano_banana_real_pngs",
        "description": "Drop real Nano Banana PNG samples into inbox/ and register them here.",
        "schema": {
            "id": "stable sample id",
            "png": "path relative to this manifest",
            "ocr_sidecar": "optional OCR sidecar JSON path",
            "notes": "freeform expectations",
            "expected": "optional lightweight benchmark expectations",
        },
        "sample_template": {
            "id": "replace-with-real-sample",
            "png": "inbox/replace-with-real-sample.png",
            "ocr_sidecar": "ocr_sidecars/replace-with-real-sample.ocr.json",
            "notes": "Describe the figure, expected objects, and hard parts here.",
            "expected": {
                "min_primitives": 4,
                "min_texts": 2,
                "primitive_counts": {"rectangle": 2},
                "relation_counts": {"flows_to": 1},
                "required_texts": ["EGFR", "RAS"],
            },
        },
        "samples": [],
    }


def _dataset_readme() -> str:
    return """# Nano Banana real-sample kit

This folder is the local workspace for collecting and evaluating real Nano Banana PNG figures.

## How to use it

1. Put real PNG files in `inbox/`.
2. Optionally create OCR sidecars in `ocr_sidecars/` using the format:
   ```json
   {
     \"texts\": [
       {
         \"text\": \"EGFR\",
         \"bbox\": {\"x\": 10, \"y\": 20, \"width\": 60, \"height\": 20},
         \"confidence\": 0.98
       }
     ]
   }
   ```
3. Register each sample in `manifest.json`, and optionally add an `expected` block for lightweight benchmark checks.
4. Run `figvector dataset-run datasets/nano_banana --ocr-backend sidecar-json`.
5. Inspect `outputs/<sample-id>/` for SVG, draw.io, and JSON outputs.
6. Run `figvector dataset-eval datasets/nano_banana` to compare predicted scene graphs against the expected counts/texts you recorded.

This scaffold exists so the repo can grow from a synthetic demo toward a real evaluation set without guessing hidden file layouts each time.
"""


def _evaluate_payload(payload: dict[str, object], expected: dict[str, object] | None) -> dict[str, object] | None:
    if not expected:
        return None

    primitive_counts = Counter(item.get("kind", "") for item in payload.get("primitives", []))
    relation_counts = Counter(item.get("kind", "") for item in payload.get("relations", []))
    text_values = [item.get("text", "") for item in payload.get("texts", [])]
    checks: list[dict[str, object]] = []

    for kind, expected_count in expected.get("primitive_counts", {}).items():
        actual_count = primitive_counts.get(kind, 0)
        checks.append(
            {
                "name": f"primitive_counts.{kind}",
                "passed": int(expected_count) == int(actual_count),
                "expected": int(expected_count),
                "actual": int(actual_count),
            }
        )

    for kind, expected_count in expected.get("relation_counts", {}).items():
        actual_count = relation_counts.get(kind, 0)
        checks.append(
            {
                "name": f"relation_counts.{kind}",
                "passed": int(expected_count) == int(actual_count),
                "expected": int(expected_count),
                "actual": int(actual_count),
            }
        )

    for text in expected.get("required_texts", []):
        checks.append(
            {
                "name": f"required_texts.{text}",
                "passed": text in text_values,
                "expected": text,
                "actual": text_values,
            }
        )

    minimum = expected.get("min_primitives")
    if minimum is not None:
        checks.append(
            {
                "name": "min_primitives",
                "passed": len(payload.get("primitives", [])) >= int(minimum),
                "expected": int(minimum),
                "actual": len(payload.get("primitives", [])),
            }
        )

    minimum_texts = expected.get("min_texts")
    if minimum_texts is not None:
        checks.append(
            {
                "name": "min_texts",
                "passed": len(payload.get("texts", [])) >= int(minimum_texts),
                "expected": int(minimum_texts),
                "actual": len(payload.get("texts", [])),
            }
        )

    if not checks:
        return {"passed": True, "score": 1.0, "checks": []}
    passed_count = sum(1 for check in checks if check["passed"])
    return {
        "passed": passed_count == len(checks),
        "score": round(passed_count / len(checks), 3),
        "checks": checks,
    }
