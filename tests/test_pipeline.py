from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from figvector.dataset import (
    bootstrap_expected_from_outputs,
    create_dataset_scaffold,
    evaluate_dataset,
    optimize_dataset,
    register_inbox_samples,
    run_dataset,
)
from figvector.demo import build_demo_assets
from figvector.eval import evaluate_payload, evaluate_scene
from figvector.models import BoundingBox, Primitive, SceneGraph, TextBlock
from figvector.ocr import OCRConfig
from figvector.pipeline import vectorize_png
from figvector.relations import infer_relations


class PipelineSmokeTests(unittest.TestCase):
    def test_demo_assets_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = build_demo_assets(tmpdir)
            self.assertTrue(result["png"].exists())
            self.assertTrue(result["ocr"].exists())
            self.assertTrue(result["svg"].exists())
            self.assertTrue(result["report"].exists())
            self.assertTrue(result["drawio"].exists())
            self.assertTrue(result["review"].exists())
            review_html = result["review"].read_text(encoding="utf-8")
            self.assertIn("Output SVG", review_html)
            self.assertIn("draw.io XML", review_html)
            svg = result["svg"].read_text(encoding="utf-8")
            self.assertIn("<svg", svg)
            self.assertIn("primitive-1", svg)
            self.assertIn("data-figvector-from", svg)
            self.assertIn('data-figvector-kind="text"', svg)

    def test_nested_demo_assets_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = build_demo_assets(tmpdir, variant="nested")
            self.assertTrue(result["png"].exists())
            self.assertTrue(result["ocr"].exists())
            self.assertTrue(result["svg"].exists())
            self.assertTrue(result["report"].exists())
            self.assertTrue(result["drawio"].exists())
            self.assertTrue(result["review"].exists())
            review_html = result["review"].read_text(encoding="utf-8")
            self.assertIn("Output SVG", review_html)
            self.assertIn("draw.io XML", review_html)
            report = json.loads(result["report"].read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(report["primitives"]), 8)
            self.assertGreaterEqual(len(report["texts"]), 5)
            relation_kinds = {item["kind"] for item in report["relations"]}
            self.assertIn("flows_to", relation_kinds)
            self.assertIn("linked_to", relation_kinds)
            self.assertIn("group_with", relation_kinds)
            oversized = [
                primitive
                for primitive in report["primitives"]
                if primitive["bbox"]["width"] >= 400 and primitive["bbox"]["height"] >= 170
            ]
            self.assertTrue(oversized)
            self.assertTrue(all(primitive["kind"] == "region" for primitive in oversized))

            semantic_expected = {
                "required_labels": [
                    {"text": "Workspace", "target_kind": "region"},
                    {"text": "Detect", "target_kind": "rectangle"},
                    {"text": "Refine", "target_kind": "rectangle"},
                    {"text": "Export", "target_kind": "rectangle"},
                ],
                "required_object_relations": [
                    {
                        "kind": "flows_to",
                        "source_text": "Detect",
                        "target_text": "Refine",
                        "source_kind": "rectangle",
                        "target_kind": "rectangle",
                    },
                    {
                        "kind": "linked_to",
                        "source_text": "Refine",
                        "target_text": "Export",
                        "source_kind": "rectangle",
                        "target_kind": "rectangle",
                    },
                ],
            }
            semantic_result = evaluate_payload(report, semantic_expected)
            self.assertIsNotNone(semantic_result)
            self.assertTrue(semantic_result.passed)
            group_rels = [item for item in report["relations"] if item["kind"] == "group_with"]
            self.assertGreaterEqual(len(group_rels), 2)

    def test_vectorize_cli_pipeline_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            demo_assets = build_demo_assets(base)
            input_png = demo_assets["png"]
            output_svg = base / "copy.svg"
            report = base / "copy.json"
            drawio = base / "copy.drawio"
            scene = vectorize_png(
                input_png,
                output_svg,
                report_path=report,
                drawio_path=drawio,
                ocr=OCRConfig(backend="sidecar-json", sidecar_path=str(demo_assets["ocr"])),
            )
            self.assertGreaterEqual(len(scene.primitives), 4)
            self.assertGreaterEqual(len(scene.relations), 2)
            self.assertGreaterEqual(len(scene.texts), 1)
            self.assertTrue(output_svg.exists())
            self.assertTrue(report.exists())
            self.assertTrue(drawio.exists())
            drawio_xml = drawio.read_text(encoding="utf-8")
            self.assertIn("<mxfile", drawio_xml)
            self.assertIn("edge-1", drawio_xml)

    def test_scene_evaluation_can_check_semantic_labels_and_relations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            demo_assets = build_demo_assets(base)
            scene = vectorize_png(
                demo_assets["png"],
                base / "semantic.svg",
                report_path=base / "semantic.json",
                drawio_path=base / "semantic.drawio",
                ocr=OCRConfig(backend="sidecar-json", sidecar_path=str(demo_assets["ocr"])),
            )
            expected = {
                "required_labels": [
                    {"text": "Prompt", "target_kind": "rectangle"},
                    {"text": "Signal", "target_kind": "ellipse"},
                ],
                "required_object_relations": [
                    {
                        "kind": "flows_to",
                        "source_text": "Prompt",
                        "target_text": "Encoder",
                        "source_kind": "rectangle",
                        "target_kind": "rectangle",
                    },
                    {
                        "kind": "linked_to",
                        "source_text": "Signal",
                        "target_text": "Editable",
                        "source_kind": "ellipse",
                        "target_kind": "rectangle",
                    },
                ],
            }

            result = evaluate_scene(scene, expected)
            self.assertIsNotNone(result)
            self.assertTrue(result.passed)
            payload_result = evaluate_payload(scene.to_dict(), expected)
            self.assertIsNotNone(payload_result)
            self.assertTrue(payload_result.passed)

            negative = evaluate_scene(
                scene,
                {
                    "required_object_relations": [
                        {
                            "kind": "flows_to",
                            "source_text": "Prompt",
                            "target_text": "Editable",
                            "source_kind": "rectangle",
                            "target_kind": "rectangle",
                        }
                    ]
                },
            )
            self.assertIsNotNone(negative)
            self.assertFalse(negative.passed)
            self.assertIn("Prompt->Encoder", str(negative.checks[0]["actual"]))

    def test_text_relations_prefer_specific_nested_shape_over_large_region(self) -> None:
        outer = Primitive(
            kind="region",
            bbox=BoundingBox(x=20, y=20, width=300, height=180),
            color=(240, 240, 240, 255),
            confidence=0.55,
            metadata={"id": "primitive-outer"},
        )
        inner = Primitive(
            kind="rectangle",
            bbox=BoundingBox(x=80, y=70, width=120, height=60),
            color=(90, 132, 255, 255),
            confidence=0.9,
            metadata={"id": "primitive-inner"},
        )
        text = TextBlock(
            text="Inner Label",
            bbox=BoundingBox(x=95, y=85, width=80, height=20),
            confidence=0.99,
            source="sidecar-json",
            metadata={"id": "text-1"},
        )
        scene = SceneGraph(width=360, height=240, background=(255, 255, 255, 255), primitives=[outer, inner], texts=[text])

        relations = infer_relations(scene)
        label_relations = [relation for relation in relations if relation.kind == "labels"]
        self.assertEqual(1, len(label_relations))
        self.assertEqual("primitive-inner", label_relations[0].target_id)
        self.assertEqual("primitive-inner", text.metadata["label_for"])

    def test_connector_relations_prefer_specific_shape_over_nearby_region(self) -> None:
        source = Primitive(
            kind="rectangle",
            bbox=BoundingBox(x=40, y=100, width=90, height=50),
            color=(90, 132, 255, 255),
            confidence=0.9,
            metadata={"id": "primitive-source"},
        )
        outer = Primitive(
            kind="region",
            bbox=BoundingBox(x=180, y=60, width=170, height=150),
            color=(240, 240, 240, 255),
            confidence=0.55,
            metadata={"id": "primitive-outer"},
        )
        inner = Primitive(
            kind="rectangle",
            bbox=BoundingBox(x=215, y=110, width=80, height=50),
            color=(78, 196, 140, 255),
            confidence=0.92,
            metadata={"id": "primitive-inner"},
        )
        arrow = Primitive(
            kind="arrow",
            bbox=BoundingBox(x=128, y=117, width=74, height=16),
            color=(46, 50, 71, 255),
            confidence=0.8,
            metadata={"id": "primitive-arrow", "direction": "right"},
        )
        scene = SceneGraph(
            width=400,
            height=260,
            background=(255, 255, 255, 255),
            primitives=[source, outer, inner, arrow],
            texts=[],
        )

        relations = infer_relations(scene)
        flow_relations = [relation for relation in relations if relation.kind == "flows_to"]
        self.assertEqual(1, len(flow_relations))
        self.assertEqual("primitive-source", flow_relations[0].source_id)
        self.assertEqual("primitive-inner", flow_relations[0].target_id)
        self.assertEqual("primitive-inner", arrow.metadata["connects_to"])

    def test_polyline_relations_prefer_specific_shape_over_large_region(self) -> None:
        source = Primitive(
            kind="ellipse",
            bbox=BoundingBox(x=70, y=220, width=60, height=60),
            color=(122, 186, 255, 255),
            confidence=0.88,
            metadata={"id": "primitive-source"},
        )
        outer = Primitive(
            kind="region",
            bbox=BoundingBox(x=200, y=120, width=190, height=170),
            color=(240, 240, 240, 255),
            confidence=0.55,
            metadata={"id": "primitive-outer"},
        )
        inner = Primitive(
            kind="rectangle",
            bbox=BoundingBox(x=265, y=215, width=90, height=55),
            color=(248, 223, 143, 255),
            confidence=0.9,
            metadata={"id": "primitive-inner"},
        )
        polyline = Primitive(
            kind="polyline",
            bbox=BoundingBox(x=130, y=245, width=108, height=31),
            color=(46, 50, 71, 255),
            confidence=0.8,
            metadata={
                "id": "primitive-polyline",
                "points": [[130, 250], [185, 250], [185, 270], [237, 270]],
            },
        )
        scene = SceneGraph(
            width=440,
            height=340,
            background=(255, 255, 255, 255),
            primitives=[source, outer, inner, polyline],
            texts=[],
        )

        relations = infer_relations(scene)
        linked_relations = [relation for relation in relations if relation.kind == "linked_to"]
        self.assertEqual(1, len(linked_relations))
        self.assertEqual("primitive-source", linked_relations[0].source_id)
        self.assertEqual("primitive-inner", linked_relations[0].target_id)
        self.assertEqual("primitive-inner", polyline.metadata["connects_to"])

    def test_dataset_scaffold_register_run_eval_and_optimize(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "dataset"
            scaffold = create_dataset_scaffold(root)
            self.assertTrue(scaffold["manifest"].exists())

            demo = build_demo_assets(root / "seed")
            inbox_png = root / "inbox" / "real-sample.png"
            inbox_png.write_bytes(demo["png"].read_bytes())

            additions = register_inbox_samples(root)
            self.assertEqual(1, len(additions))
            self.assertTrue((root / additions[0]["ocr_sidecar"]).exists())
            self.assertNotIn("expected", additions[0])

            manifest = json.loads(scaffold["manifest"].read_text(encoding="utf-8"))
            self.assertNotIn("expected", manifest["samples"][0])
            manifest["samples"][0]["ocr_sidecar"] = str(demo["ocr"].relative_to(root))
            manifest["samples"][0]["expected"] = {
                "min_primitives": 6,
                "min_texts": 5,
                "primitive_counts": {"rectangle": 4, "ellipse": 1, "arrow": 2, "polyline": 1},
                "relation_counts": {"flows_to": 2, "labels": 5, "linked_to": 1},
                "required_texts": ["Prompt", "Encoder", "Output"],
                "required_labels": [
                    {"text": "Prompt", "target_kind": "rectangle"},
                    {"text": "Signal", "target_kind": "ellipse"},
                ],
                "required_object_relations": [
                    {
                        "kind": "flows_to",
                        "source_text": "Prompt",
                        "target_text": "Encoder",
                        "source_kind": "rectangle",
                        "target_kind": "rectangle",
                    },
                    {
                        "kind": "linked_to",
                        "source_text": "Signal",
                        "target_text": "Editable",
                        "source_kind": "ellipse",
                        "target_kind": "rectangle",
                    },
                ],
            }
            scaffold["manifest"].write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            results = run_dataset(root, ocr_backend="sidecar-json", profile="real")
            self.assertEqual(1, len(results))
            self.assertTrue((root / "outputs" / "summary.json").exists())
            self.assertTrue((root / "outputs" / "report.md").exists())
            self.assertTrue((root / "outputs" / "index.html").exists())
            self.assertTrue((root / "outputs" / "real-sample" / "summary.md").exists())
            review_html = root / "outputs" / "real-sample" / "review.html"
            self.assertTrue(review_html.exists())
            self.assertIn("Output SVG", review_html.read_text(encoding="utf-8"))
            self.assertTrue(results[0]["evaluation"]["passed"])

            evaluations = evaluate_dataset(root)
            self.assertEqual(1, len(evaluations))
            self.assertTrue(evaluations[0]["evaluation"]["passed"])
            self.assertTrue((root / "outputs" / "evaluation-summary.json").exists())
            self.assertTrue((root / "outputs" / "evaluation-report.md").exists())

            manifest = json.loads(scaffold["manifest"].read_text(encoding="utf-8"))
            manifest["samples"][0].pop("expected", None)
            scaffold["manifest"].write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            bootstrapped = bootstrap_expected_from_outputs(root)
            self.assertEqual(1, len(bootstrapped))
            refreshed_manifest = json.loads(scaffold["manifest"].read_text(encoding="utf-8"))
            self.assertIn("expected", refreshed_manifest["samples"][0])
            self.assertEqual(4, refreshed_manifest["samples"][0]["expected"]["primitive_counts"]["rectangle"])
            self.assertIn("required_labels", refreshed_manifest["samples"][0]["expected"])
            self.assertIn("required_object_relations", refreshed_manifest["samples"][0]["expected"])

            leaderboard = optimize_dataset(root, profiles=["synthetic", "real"], ocr_backend="sidecar-json")
            self.assertEqual(2, len(leaderboard))
            self.assertTrue((root / "outputs" / "optimization-summary.json").exists())
            self.assertTrue((root / "outputs" / "optimization-report.md").exists())
            self.assertTrue((root / "outputs" / "optimization-comparison.json").exists())
            self.assertTrue((root / "outputs" / "optimization-comparison.md").exists())


if __name__ == "__main__":
    unittest.main()
