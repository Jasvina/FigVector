from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def register_inbox_samples(root: str | Path, *, create_sidecars: bool = True) -> list[dict[str, object]]:
    root = Path(root)
    create_dataset_scaffold(root)
    manifest_path = root / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    samples = list(payload.get("samples", []))
    template = payload.get("sample_template", {})
    existing_pngs = {item.get("png") for item in samples}
    existing_ids = {item.get("id") for item in samples}

    additions: list[dict[str, object]] = []
    for png_path in sorted((root / "inbox").glob("*.png")):
        relative_png = str(png_path.relative_to(root))
        if relative_png in existing_pngs:
            continue

        sample_id = _unique_sample_id(_slugify(png_path.stem), existing_ids)
        entry = {
            "id": sample_id,
            "png": relative_png,
            "ocr_sidecar": str((root / "ocr_sidecars" / f"{sample_id}.ocr.json").relative_to(root)),
            "notes": "",
            "expected": json.loads(json.dumps(template.get("expected", {}))),
        }
        if not entry["expected"]:
            entry.pop("expected")
        if create_sidecars:
            sidecar_path = root / entry["ocr_sidecar"]
            if not sidecar_path.exists():
                sidecar_path.write_text(json.dumps({"texts": []}, indent=2), encoding="utf-8")
        samples.append(entry)
        additions.append(entry)
        existing_ids.add(sample_id)
        existing_pngs.add(relative_png)

    payload["samples"] = samples
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return additions


def bootstrap_expected_from_outputs(
    root: str | Path,
    *,
    output_dir: str | Path | None = None,
    overwrite: bool = False,
    required_text_limit: int = 8,
) -> list[dict[str, object]]:
    root = Path(root)
    manifest_path = root / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    samples = list(payload.get("samples", []))
    source = Path(output_dir) if output_dir is not None else root / "outputs"
    source.mkdir(parents=True, exist_ok=True)

    updated: list[dict[str, object]] = []
    for item in samples:
        if item.get("expected") and not overwrite:
            continue
        report_path = source / item["id"] / "report.json"
        if not report_path.exists():
            continue

        report = json.loads(report_path.read_text(encoding="utf-8"))
        expected = _expected_from_report(report, required_text_limit=required_text_limit)
        item["expected"] = expected
        updated.append({"id": item["id"], "expected": expected})

    payload["samples"] = samples
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return updated


def run_dataset(
    root: str | Path,
    *,
    output_dir: str | Path | None = None,
    ocr_backend: str = "none",
    profile: str = "real",
    background_threshold: int | None = None,
    min_area: int | None = None,
    color_quantization: int | None = None,
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
            profile=profile,
            background_threshold=background_threshold,
            min_area=min_area,
            color_quantization=color_quantization,
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
                "profile": profile,
                "evaluation": evaluation.to_dict() if evaluation is not None else None,
            }
        )

    summary_path = destination / "summary.json"
    summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    _write_markdown_report(destination / "report.md", results, title=f"FigVector dataset run ({profile})")
    return results


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
    _write_markdown_report(source / "evaluation-report.md", results, title="FigVector dataset evaluation")
    return results


def optimize_dataset(
    root: str | Path,
    *,
    profiles: list[str],
    ocr_backend: str = "none",
) -> list[dict[str, object]]:
    root = Path(root)
    outputs_root = root / "outputs"
    outputs_root.mkdir(parents=True, exist_ok=True)
    leaderboard: list[dict[str, object]] = []

    for profile in profiles:
        profile_output = outputs_root / profile
        run_dataset(root, output_dir=profile_output, ocr_backend=ocr_backend, profile=profile)
        evaluations = evaluate_dataset(root, output_dir=profile_output)
        valid = [item["evaluation"] for item in evaluations if item.get("evaluation")]
        if valid:
            average_score = round(sum(item["score"] for item in valid) / len(valid), 3)
            pass_rate = round(sum(1 for item in valid if item["passed"]) / len(valid), 3)
        else:
            average_score = 0.0
            pass_rate = 0.0
        leaderboard.append(
            {
                "profile": profile,
                "samples": len(evaluations),
                "average_score": average_score,
                "pass_rate": pass_rate,
            }
        )

    leaderboard.sort(key=lambda item: (-item["average_score"], -item["pass_rate"], item["profile"]))
    (outputs_root / "optimization-summary.json").write_text(json.dumps(leaderboard, indent=2), encoding="utf-8")
    _write_markdown_report(outputs_root / "optimization-report.md", leaderboard, title="FigVector profile sweep")
    return leaderboard


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
2. Run `figvector dataset-register datasets/nano_banana` to register new PNGs into the manifest and create empty OCR sidecars.
3. Fill OCR sidecars in `ocr_sidecars/` using the format:
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
4. Optionally add an `expected` block per sample in `manifest.json` for lightweight benchmark checks.
5. Run `figvector dataset-run datasets/nano_banana --ocr-backend sidecar-json --profile real`.
6. Inspect `outputs/<sample-id>/` plus `outputs/report.md` for generated artifacts and per-sample summaries.
7. Run `figvector dataset-eval datasets/nano_banana` to compare scene graphs against `expected` checks.
8. Run `figvector dataset-optimize datasets/nano_banana --profiles synthetic real` to compare profile-level scores.

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


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "sample"


def _unique_sample_id(base: str, existing_ids: set[str]) -> str:
    candidate = base
    index = 2
    while candidate in existing_ids:
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _write_markdown_report(path: Path, items: list[dict[str, object]], *, title: str) -> None:
    lines = [f"# {title}", ""]
    if not items:
        lines.append("No samples were available for this run.")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    if all("average_score" in item for item in items):
        lines.append("| Profile | Samples | Avg score | Pass rate |")
        lines.append("| --- | ---: | ---: | ---: |")
        for item in items:
            lines.append(
                f"| `{item['profile']}` | {item['samples']} | {item['average_score']:.3f} | {item['pass_rate']:.3f} |"
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    include_profile = any("profile" in item for item in items)
    if include_profile:
        lines.append("| Sample | Profile | Score | Passed | Notes |")
        lines.append("| --- | --- | ---: | :---: | --- |")
    else:
        lines.append("| Sample | Score | Passed | Notes |")
        lines.append("| --- | ---: | :---: | --- |")
    for item in items:
        evaluation = item.get("evaluation") or {}
        score = evaluation.get("score", "-")
        passed = "yes" if evaluation.get("passed") else "no"
        notes = _failed_check_summary(evaluation.get("checks", []))
        if include_profile:
            lines.append(f"| `{item['id']}` | `{item.get('profile', '-')}` | {score} | {passed} | {notes} |")
        else:
            lines.append(f"| `{item['id']}` | {score} | {passed} | {notes} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _failed_check_summary(checks: list[dict[str, Any]]) -> str:
    failures = [check["name"] for check in checks if not check.get("passed")]
    if not failures:
        return "all checks passed"
    return ", ".join(failures[:4])


def _expected_from_report(report: dict[str, Any], *, required_text_limit: int) -> dict[str, object]:
    primitive_counts = Counter(item.get("kind", "") for item in report.get("primitives", []))
    relation_counts = Counter(item.get("kind", "") for item in report.get("relations", []))
    texts = [item.get("text", "").strip() for item in report.get("texts", []) if item.get("text", "").strip()]

    expected: dict[str, object] = {
        "min_primitives": len(report.get("primitives", [])),
        "min_texts": len(report.get("texts", [])),
    }
    if primitive_counts:
        expected["primitive_counts"] = dict(sorted(primitive_counts.items()))
    if relation_counts:
        expected["relation_counts"] = dict(sorted(relation_counts.items()))
    if texts:
        deduped_texts = list(dict.fromkeys(texts))
        expected["required_texts"] = deduped_texts[: max(0, required_text_limit)]
    return expected
