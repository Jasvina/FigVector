from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from figvector.dataset import create_dataset_scaffold, evaluate_dataset, run_dataset
from figvector.demo import build_demo_assets
from figvector.ocr import OCRConfig
from figvector.pipeline import vectorize_png


class PipelineSmokeTests(unittest.TestCase):
    def test_demo_assets_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = build_demo_assets(tmpdir)
            self.assertTrue(result["png"].exists())
            self.assertTrue(result["ocr"].exists())
            self.assertTrue(result["svg"].exists())
            self.assertTrue(result["report"].exists())
            self.assertTrue(result["drawio"].exists())
            svg = result["svg"].read_text(encoding="utf-8")
            self.assertIn("<svg", svg)
            self.assertIn("primitive-1", svg)
            self.assertIn("data-figvector-from", svg)
            self.assertIn('data-figvector-kind="text"', svg)

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

    def test_dataset_scaffold_and_batch_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "dataset"
            scaffold = create_dataset_scaffold(root)
            self.assertTrue(scaffold["manifest"].exists())
            demo = build_demo_assets(root / "seed")
            manifest = {
                "dataset": "nano_banana_real_pngs",
                "samples": [
                    {
                        "id": "sample-001",
                        "png": str(demo["png"].relative_to(root)),
                        "ocr_sidecar": str(demo["ocr"].relative_to(root)),
                        "notes": "seed sample",
                        "expected": {
                            "min_primitives": 6,
                            "min_texts": 5,
                            "primitive_counts": {"rectangle": 4, "ellipse": 1, "arrow": 2, "polyline": 1},
                            "relation_counts": {"flows_to": 2, "labels": 5, "linked_to": 1},
                            "required_texts": ["Prompt", "Encoder", "Output"],
                        },
                    }
                ],
            }
            scaffold["manifest"].write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            results = run_dataset(root, ocr_backend="sidecar-json")
            self.assertEqual(1, len(results))
            self.assertTrue((root / "outputs" / "sample-001" / "output.svg").exists())
            self.assertTrue((root / "outputs" / "summary.json").exists())
            self.assertTrue(results[0]["evaluation"]["passed"])

            evaluations = evaluate_dataset(root)
            self.assertEqual(1, len(evaluations))
            self.assertTrue(evaluations[0]["evaluation"]["passed"])
            self.assertTrue((root / "outputs" / "evaluation-summary.json").exists())


if __name__ == "__main__":
    unittest.main()
