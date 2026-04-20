from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from figvector.demo import build_demo_assets
from figvector.pipeline import vectorize_png


class PipelineSmokeTests(unittest.TestCase):
    def test_demo_assets_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = build_demo_assets(tmpdir)
            self.assertTrue(result["png"].exists())
            self.assertTrue(result["svg"].exists())
            self.assertTrue(result["report"].exists())
            svg = result["svg"].read_text(encoding="utf-8")
            self.assertIn("<svg", svg)
            self.assertIn("primitive-1", svg)
            self.assertIn("data-figvector-from", svg)

    def test_vectorize_cli_pipeline_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            input_png = build_demo_assets(base)["png"]
            output_svg = base / "copy.svg"
            report = base / "copy.json"
            scene = vectorize_png(input_png, output_svg, report)
            self.assertGreaterEqual(len(scene.primitives), 4)
            self.assertGreaterEqual(len(scene.relations), 2)
            self.assertTrue(output_svg.exists())
            self.assertTrue(report.exists())


if __name__ == "__main__":
    unittest.main()
