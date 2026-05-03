from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from html import escape as html_escape
from os.path import relpath
from pathlib import Path
from typing import Any

from .eval import evaluate_payload, evaluate_scene
from .models import SceneGraph
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
    existing_pngs = {item.get("png") for item in samples}
    existing_ids = {item.get("id") for item in samples}

    additions: list[dict[str, object]] = []
    inbox_pngs = sorted(path for path in (root / "inbox").iterdir() if path.is_file() and path.suffix.lower() == ".png")
    for png_path in inbox_pngs:
        relative_png = str(png_path.relative_to(root))
        if relative_png in existing_pngs:
            continue

        sample_id = _unique_sample_id(_slugify(png_path.stem), existing_ids)
        entry = {
            "id": sample_id,
            "png": relative_png,
            "ocr_sidecar": str((root / "ocr_sidecars" / f"{sample_id}.ocr.json").relative_to(root)),
            "notes": "",
        }
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
        sample_dir.mkdir(parents=True, exist_ok=True)
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
                "primitive_counts": dict(sorted(Counter(primitive.kind for primitive in scene.primitives).items())),
                "relation_counts": dict(sorted(Counter(relation.kind for relation in scene.relations).items())),
                "text_count": len(scene.texts),
                "evaluation": evaluation.to_dict() if evaluation is not None else None,
            }
        )
        _write_sample_summary(sample_dir / "summary.md", results[-1], sample.notes)
        _write_sample_review_html(sample_dir / "review.html", results[-1], sample.notes)

    summary_path = destination / "summary.json"
    summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    _write_markdown_report(destination / "report.md", results, title=f"FigVector dataset run ({profile})")
    _write_dataset_index(destination / "index.html", results, title=f"FigVector dataset run ({profile})")
    return results


def write_vectorize_review_html(
    review_path: str | Path,
    *,
    input_path: str | Path,
    svg_path: str | Path,
    scene: SceneGraph,
    profile: str,
    report_path: str | Path | None = None,
    drawio_path: str | Path | None = None,
    notes: str = "",
) -> Path:
    review_path = Path(review_path)
    review_path.parent.mkdir(parents=True, exist_ok=True)
    item = {
        "id": Path(input_path).stem,
        "input": str(Path(input_path)),
        "svg": str(Path(svg_path)),
        "report": str(Path(report_path)) if report_path is not None else None,
        "drawio": str(Path(drawio_path)) if drawio_path is not None else None,
        "profile": profile,
        "primitive_counts": dict(sorted(Counter(primitive.kind for primitive in scene.primitives).items())),
        "relation_counts": dict(sorted(Counter(relation.kind for relation in scene.relations).items())),
        "text_count": len(scene.texts),
        "evaluation": None,
        "summary": None,
    }
    _write_sample_review_html(review_path, item, notes)
    return review_path


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
    comparisons: dict[str, dict[str, dict[str, object]]] = {}

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
        for item in evaluations:
            comparisons.setdefault(item["id"], {})[profile] = item.get("evaluation") or {
                "passed": False,
                "score": 0.0,
                "checks": [],
            }
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
    comparison_rows = _comparison_rows(comparisons, profiles)
    (outputs_root / "optimization-comparison.json").write_text(json.dumps(comparison_rows, indent=2), encoding="utf-8")
    _write_optimization_comparison(outputs_root / "optimization-comparison.md", comparison_rows, profiles)
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
            "_note": "Reference template only. register_inbox_samples does not copy this block into new samples automatically.",
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
    result = evaluate_payload(payload, expected)
    return result.to_dict() if result is not None else None


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
    label_expectations = _required_labels_from_report(report, texts)
    if label_expectations:
        expected["required_labels"] = label_expectations
    object_relation_expectations = _required_object_relations_from_report(report)
    if object_relation_expectations:
        expected["required_object_relations"] = object_relation_expectations
    group_expectations = _required_group_members_from_report(report)
    if group_expectations:
        expected["required_group_members"] = group_expectations
    return expected


def _required_labels_from_report(report: dict[str, Any], texts: list[str]) -> list[dict[str, str]]:
    primitives_by_id = {
        str(item.get("metadata", {}).get("id", "")).strip(): item
        for item in report.get("primitives", [])
        if str(item.get("metadata", {}).get("id", "")).strip()
    }
    expectations: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    allowed_texts = set(texts)
    for text_block in report.get("texts", []):
        text = str(text_block.get("text", "")).strip()
        if not text or text not in allowed_texts:
            continue
        label_for = str(text_block.get("metadata", {}).get("label_for", "")).strip()
        primitive = primitives_by_id.get(label_for)
        if primitive is None:
            continue
        target_kind = str(primitive.get("kind", "")).strip()
        signature = (text, target_kind)
        if signature in seen:
            continue
        seen.add(signature)
        expectations.append({"text": text, "target_kind": target_kind})
    return expectations


def _required_object_relations_from_report(report: dict[str, Any]) -> list[dict[str, str]]:
    primitives_by_id = {
        str(item.get("metadata", {}).get("id", "")).strip(): item
        for item in report.get("primitives", [])
        if str(item.get("metadata", {}).get("id", "")).strip()
    }
    labels_by_primitive: dict[str, list[str]] = {}
    for text_block in report.get("texts", []):
        label_for = str(text_block.get("metadata", {}).get("label_for", "")).strip()
        text = str(text_block.get("text", "")).strip()
        if not label_for or not text:
            continue
        labels_by_primitive.setdefault(label_for, [])
        if text not in labels_by_primitive[label_for]:
            labels_by_primitive[label_for].append(text)

    expectations: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for relation in report.get("relations", []):
        kind = str(relation.get("kind", "")).strip()
        if kind not in {"flows_to", "linked_to"}:
            continue
        source_id = str(relation.get("source_id", "")).strip()
        target_id = str(relation.get("target_id", "")).strip()
        source = primitives_by_id.get(source_id)
        target = primitives_by_id.get(target_id)
        if source is None or target is None:
            continue
        source_labels = labels_by_primitive.get(source_id, [])
        target_labels = labels_by_primitive.get(target_id, [])
        source_text = source_labels[0] if source_labels else ""
        target_text = target_labels[0] if target_labels else ""
        source_kind = str(source.get("kind", "")).strip()
        target_kind = str(target.get("kind", "")).strip()
        signature = (kind, source_text, target_text, source_kind, target_kind)
        if signature in seen:
            continue
        seen.add(signature)
        expectations.append(
            {
                "kind": kind,
                "source_text": source_text,
                "target_text": target_text,
                "source_kind": source_kind,
                "target_kind": target_kind,
            }
        )
    return expectations


def _required_group_members_from_report(report: dict[str, Any]) -> list[dict[str, str]]:
    primitives_by_id = {
        str(item.get("metadata", {}).get("id", "")).strip(): item
        for item in report.get("primitives", [])
        if str(item.get("metadata", {}).get("id", "")).strip()
    }
    labels_by_primitive: dict[str, list[str]] = {}
    for text_block in report.get("texts", []):
        label_for = str(text_block.get("metadata", {}).get("label_for", "")).strip()
        text = str(text_block.get("text", "")).strip()
        if not label_for or not text:
            continue
        labels_by_primitive.setdefault(label_for, [])
        if text not in labels_by_primitive[label_for]:
            labels_by_primitive[label_for].append(text)

    expectations: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for relation in report.get("relations", []):
        if str(relation.get("kind", "")).strip() != "group_with":
            continue
        container_id = str(relation.get("source_id", "")).strip()
        member_id = str(relation.get("target_id", "")).strip()
        container = primitives_by_id.get(container_id)
        member = primitives_by_id.get(member_id)
        if container is None or member is None:
            continue
        container_labels = labels_by_primitive.get(container_id, [])
        member_labels = labels_by_primitive.get(member_id, [])
        container_text = container_labels[0] if container_labels else ""
        member_text = member_labels[0] if member_labels else ""
        container_kind = str(container.get("kind", "")).strip()
        member_kind = str(member.get("kind", "")).strip()
        signature = (container_text, member_text, container_kind, member_kind)
        if signature in seen:
            continue
        seen.add(signature)
        expectations.append(
            {
                "container_text": container_text,
                "member_text": member_text,
                "container_kind": container_kind,
                "member_kind": member_kind,
            }
        )
    return expectations


def _write_sample_summary(path: Path, item: dict[str, object], notes: str) -> None:
    evaluation = item.get("evaluation") or {}
    primitive_counts = item.get("primitive_counts", {})
    relation_counts = item.get("relation_counts", {})
    lines = [
        f"# Sample `{item['id']}`",
        "",
        f"- Input: `{item['input']}`",
        f"- Profile: `{item.get('profile', '-')}`",
        f"- SVG: `{item['svg']}`",
        f"- draw.io: `{item['drawio']}`",
        f"- Report: `{item['report']}`",
        f"- Text count: {item.get('text_count', 0)}",
        f"- Evaluation score: {evaluation.get('score', '-')}",
        f"- Evaluation passed: {evaluation.get('passed', '-')}",
    ]
    if notes:
        lines.extend(["", "## Notes", notes])
    if primitive_counts:
        lines.extend(["", "## Primitive counts"])
        for kind, count in primitive_counts.items():
            lines.append(f"- `{kind}`: {count}")
    if relation_counts:
        lines.extend(["", "## Relation counts"])
        for kind, count in relation_counts.items():
            lines.append(f"- `{kind}`: {count}")
    checks = evaluation.get("checks", [])
    if checks:
        lines.extend(["", "## Evaluation checks"])
        for check in checks:
            status = "PASS" if check.get("passed") else "FAIL"
            lines.append(f"- [{status}] `{check['name']}` expected={check.get('expected')} actual={check.get('actual')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_sample_review_html(path: Path, item: dict[str, object], notes: str) -> None:
    input_link = _relative_link(path.parent, Path(str(item["input"])))
    svg_link = _relative_link(path.parent, Path(str(item["svg"])))
    report_value = item.get("report")
    report_link = _relative_link(path.parent, Path(str(report_value))) if report_value else None
    drawio_value = item.get("drawio")
    drawio_link = _relative_link(path.parent, Path(str(drawio_value))) if drawio_value else None
    summary_value = item.get("summary", "summary.md")
    summary_link = _relative_link(path.parent, Path(str(summary_value))) if summary_value else None
    evaluation = item.get("evaluation") or {}
    checks = evaluation.get("checks", [])
    primitive_counts = item.get("primitive_counts", {})
    relation_counts = item.get("relation_counts", {})
    artifact_links: list[str] = []
    if summary_link:
        artifact_links.append(f"<a href=\"{html_escape(summary_link)}\">summary.md</a>")
    if report_link:
        artifact_links.append(f"<a href=\"{html_escape(report_link)}\">report.json</a>")
    if drawio_link:
        artifact_links.append(f"<a href=\"{html_escape(drawio_link)}\">draw.io XML</a>")
    artifact_links_html = " · ".join(artifact_links) if artifact_links else "No extra artifacts linked."

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>FigVector review - {html_escape(str(item['id']))}</title>
  <style>
    body {{ margin: 0; font-family: Avenir, Helvetica, Arial, sans-serif; background: #fbfaf6; color: #2e3247; }}
    header {{ padding: 24px 32px; border-bottom: 1px solid #d8e0ee; background: #fff; }}
    main {{ padding: 24px 32px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }}
    .card {{ background: #fff; border: 1px solid #d8e0ee; border-radius: 18px; padding: 18px; box-shadow: 0 12px 30px rgba(46, 50, 71, 0.08); }}
    img, object {{ width: 100%; height: 560px; object-fit: contain; background: #fff; border-radius: 12px; border: 1px solid #edf1f7; }}
    code {{ background: #edf1f7; padding: 2px 6px; border-radius: 6px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
    th, td {{ border-bottom: 1px solid #edf1f7; padding: 8px; text-align: left; }}
    .pass {{ color: #2f805b; font-weight: 700; }}
    .fail {{ color: #b84a4a; font-weight: 700; }}
    @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} img, object {{ height: 360px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>FigVector review: <code>{html_escape(str(item['id']))}</code></h1>
    <p>Profile: <code>{html_escape(str(item.get('profile', '-')))}</code> | Score: <code>{html_escape(str(evaluation.get('score', '-')))}</code> | Passed: <code>{html_escape(str(evaluation.get('passed', '-')))}</code></p>
    <p>{artifact_links_html}</p>
  </header>
  <main>
    <section class="grid">
      <article class="card">
        <h2>Input PNG</h2>
        <img src="{html_escape(input_link)}" alt="Input PNG">
      </article>
      <article class="card">
        <h2>Output SVG</h2>
        <object data="{html_escape(svg_link)}" type="image/svg+xml"></object>
      </article>
    </section>
    <section class="grid" style="margin-top:20px">
      <article class="card">
        <h2>Primitive counts</h2>
        {_counts_table(primitive_counts)}
      </article>
      <article class="card">
        <h2>Relation counts</h2>
        {_counts_table(relation_counts)}
      </article>
    </section>
    <section class="card" style="margin-top:20px">
      <h2>Evaluation checks</h2>
      {_checks_table(checks)}
    </section>
    <section class="card" style="margin-top:20px">
      <h2>Notes</h2>
      <p>{html_escape(notes or 'No notes recorded.')}</p>
    </section>
  </main>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def _write_dataset_index(path: Path, items: list[dict[str, object]], *, title: str) -> None:
    rows = []
    for item in items:
        sample_dir = Path(str(item["report"])).parent
        review_link = _relative_link(path.parent, sample_dir / "review.html")
        evaluation = item.get("evaluation") or {}
        passed = evaluation.get("passed", "-")
        score = evaluation.get("score", "-")
        rows.append(
            f"<tr><td><a href=\"{html_escape(review_link)}\"><code>{html_escape(str(item['id']))}</code></a></td>"
            f"<td>{html_escape(str(item.get('profile', '-')))}</td>"
            f"<td>{html_escape(str(score))}</td>"
            f"<td>{html_escape(str(passed))}</td>"
            f"<td>{html_escape(_failed_check_summary(evaluation.get('checks', [])))}</td></tr>"
        )

    body = "\n".join(rows) if rows else "<tr><td colspan=\"5\">No samples were available for this run.</td></tr>"
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html_escape(title)}</title>
  <style>
    body {{ margin: 0; font-family: Avenir, Helvetica, Arial, sans-serif; background: #fbfaf6; color: #2e3247; }}
    main {{ padding: 28px 34px; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; border: 1px solid #d8e0ee; border-radius: 16px; overflow: hidden; }}
    th, td {{ border-bottom: 1px solid #edf1f7; padding: 10px 12px; text-align: left; }}
    th {{ background: #eef5ff; }}
    code {{ background: #edf1f7; padding: 2px 6px; border-radius: 6px; }}
  </style>
</head>
<body>
  <main>
    <h1>{html_escape(title)}</h1>
    <p>Open a sample row to compare the input PNG with the reconstructed SVG.</p>
    <table>
      <thead><tr><th>Sample</th><th>Profile</th><th>Score</th><th>Passed</th><th>Notes</th></tr></thead>
      <tbody>
        {body}
      </tbody>
    </table>
  </main>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def _comparison_rows(
    comparisons: dict[str, dict[str, dict[str, object]]],
    profiles: list[str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sample_id in sorted(comparisons):
        profile_map = comparisons[sample_id]
        best_profile = None
        best_score = -1.0
        for profile in profiles:
            score = float((profile_map.get(profile) or {}).get("score", 0.0))
            if score > best_score:
                best_score = score
                best_profile = profile
        row = {"id": sample_id, "best_profile": best_profile, "profiles": {}}
        for profile in profiles:
            evaluation = profile_map.get(profile) or {"passed": False, "score": 0.0}
            row["profiles"][profile] = {
                "score": evaluation.get("score", 0.0),
                "passed": evaluation.get("passed", False),
            }
        rows.append(row)
    return rows


def _write_optimization_comparison(path: Path, rows: list[dict[str, object]], profiles: list[str]) -> None:
    lines = ["# FigVector optimization comparison", ""]
    if not rows:
        lines.append("No samples were available for profile comparison.")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    header = "| Sample | Best | " + " | ".join(f"{profile} score" for profile in profiles) + " |"
    divider = "| --- | --- | " + " | ".join("---:" for _ in profiles) + " |"
    lines.extend([header, divider])
    for row in rows:
        cells = [f"`{row['id']}`", f"`{row['best_profile']}`"]
        for profile in profiles:
            score = row["profiles"][profile]["score"]
            cells.append(str(score))
        lines.append("| " + " | ".join(cells) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _counts_table(counts: dict[str, object]) -> str:
    if not counts:
        return "<p>No counts available.</p>"
    rows = "\n".join(
        f"<tr><td><code>{html_escape(str(kind))}</code></td><td>{html_escape(str(count))}</td></tr>"
        for kind, count in counts.items()
    )
    return f"<table><thead><tr><th>Kind</th><th>Count</th></tr></thead><tbody>{rows}</tbody></table>"


def _checks_table(checks: list[dict[str, Any]]) -> str:
    if not checks:
        return "<p>No checks available.</p>"
    rows = []
    for check in checks:
        status = "PASS" if check.get("passed") else "FAIL"
        klass = "pass" if check.get("passed") else "fail"
        rows.append(
            f"<tr><td class=\"{klass}\">{status}</td><td><code>{html_escape(str(check.get('name')))}</code></td>"
            f"<td>{html_escape(str(check.get('expected')))}</td><td>{html_escape(str(check.get('actual')))}</td></tr>"
        )
    return "<table><thead><tr><th>Status</th><th>Check</th><th>Expected</th><th>Actual</th></tr></thead><tbody>" + "\n".join(rows) + "</tbody></table>"


def _relative_link(from_dir: Path, target: Path) -> str:
    return relpath(target, from_dir)
