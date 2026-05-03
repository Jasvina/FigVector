from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import figvector
from figvector import cli
from figvector.demo import build_demo_assets


class CLISurfaceTests(unittest.TestCase):
    def test_build_parser_exposes_expected_subcommands(self) -> None:
        parser = cli.build_parser()
        subcommands = parser._subparsers._group_actions[0].choices.keys()

        self.assertEqual(
            {
                "vectorize",
                "demo",
                "dataset-init",
                "dataset-register",
                "dataset-bootstrap-expected",
                "dataset-run",
                "dataset-eval",
                "dataset-optimize",
            },
            set(subcommands),
        )

    def test_main_help_lists_release_facing_commands(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with self.assertRaises(SystemExit) as raised:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                cli.main(["--help"])

        self.assertEqual(0, raised.exception.code)
        self.assertEqual("", stderr.getvalue())
        help_text = stdout.getvalue()
        self.assertIn("FigVector: vectorize clean PNG diagrams into editable SVG.", help_text)
        self.assertIn("vectorize", help_text)
        self.assertIn("dataset-optimize", help_text)

    def test_vectorize_help_describes_output_and_ocr_flags(self) -> None:
        stdout = io.StringIO()

        with self.assertRaises(SystemExit) as raised:
            with contextlib.redirect_stdout(stdout):
                cli.main(["vectorize", "--help"])

        self.assertEqual(0, raised.exception.code)
        help_text = stdout.getvalue()
        self.assertIn("-o, --output OUTPUT", help_text)
        self.assertIn("--drawio-output DRAWIO_OUTPUT", help_text)
        self.assertIn("--review-html REVIEW_HTML", help_text)
        self.assertIn("--ocr-backend {none,sidecar-json,tesseract-cli}", help_text)

    def test_demo_help_describes_variant_flag(self) -> None:
        stdout = io.StringIO()

        with self.assertRaises(SystemExit) as raised:
            with contextlib.redirect_stdout(stdout):
                cli.main(["demo", "--help"])

        self.assertEqual(0, raised.exception.code)
        help_text = stdout.getvalue()
        self.assertIn("--variant {basic,nested}", help_text)

    def test_invoking_without_subcommand_exits_with_usage_error(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with self.assertRaises(SystemExit) as raised:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                cli.main([])

        self.assertEqual(2, raised.exception.code)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("the following arguments are required: command", stderr.getvalue())

    def test_module_entrypoint_help_succeeds(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "figvector", "--help"],
            cwd=Path(__file__).resolve().parents[1],
            env={**dict(), **{"PYTHONPATH": "src"}},
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stderr)
        self.assertIn("FigVector: vectorize clean PNG diagrams into editable SVG.", result.stdout)

    def test_demo_command_writes_expected_cli_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "demo-cli"
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = cli.main(["demo", "--output-dir", str(output_dir)])

            self.assertEqual(0, exit_code)
            self.assertTrue((output_dir / "demo-input.png").exists())
            self.assertTrue((output_dir / "demo-input.ocr.json").exists())
            self.assertTrue((output_dir / "demo-output.svg").exists())
            self.assertTrue((output_dir / "demo-report.json").exists())
            self.assertTrue((output_dir / "demo-output.drawio").exists())
            review_html = output_dir / "demo-review.html"
            self.assertTrue(review_html.exists())
            self.assertIn("Output SVG", review_html.read_text(encoding="utf-8"))
            self.assertIn("Wrote demo SVG", stdout.getvalue())
            self.assertIn("Wrote demo review HTML", stdout.getvalue())

    def test_demo_command_supports_nested_variant(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "nested-demo-cli"
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = cli.main(["demo", "--variant", "nested", "--output-dir", str(output_dir)])

            self.assertEqual(0, exit_code)
            self.assertTrue((output_dir / "nested-demo-input.png").exists())
            self.assertTrue((output_dir / "nested-demo-input.ocr.json").exists())
            self.assertTrue((output_dir / "nested-demo-output.svg").exists())
            self.assertTrue((output_dir / "nested-demo-report.json").exists())
            self.assertTrue((output_dir / "nested-demo-output.drawio").exists())
            review_html = output_dir / "nested-demo-review.html"
            self.assertTrue(review_html.exists())
            self.assertIn("Output SVG", review_html.read_text(encoding="utf-8"))
            self.assertIn("nested-demo-output.svg", stdout.getvalue())
            self.assertIn("nested-demo-review.html", stdout.getvalue())

    def test_vectorize_command_can_emit_review_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            demo_assets = build_demo_assets(base / "seed")
            output_svg = base / "vectorized" / "output.svg"
            report = base / "vectorized" / "output.json"
            drawio = base / "vectorized" / "output.drawio"
            review = base / "reviews" / "output.html"
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = cli.main(
                    [
                        "vectorize",
                        str(demo_assets["png"]),
                        "-o",
                        str(output_svg),
                        "--report",
                        str(report),
                        "--drawio-output",
                        str(drawio),
                        "--review-html",
                        str(review),
                        "--ocr-backend",
                        "sidecar-json",
                        "--ocr-sidecar",
                        str(demo_assets["ocr"]),
                    ]
                )

            self.assertEqual(0, exit_code)
            self.assertTrue(output_svg.exists())
            self.assertTrue(report.exists())
            self.assertTrue(drawio.exists())
            self.assertTrue(review.exists())
            review_html = review.read_text(encoding="utf-8")
            self.assertIn("Input PNG", review_html)
            self.assertIn("Output SVG", review_html)
            self.assertIn("report.json", review_html)
            self.assertIn("draw.io XML", review_html)
            self.assertIn("Wrote review HTML", stdout.getvalue())

    def test_package_exports_public_api_metadata(self) -> None:
        self.assertIn("__version__", figvector.__all__)
        self.assertIn("vectorize_png", figvector.__all__)
        self.assertEqual("0.1.0", figvector.__version__)
        self.assertIs(figvector.vectorize_png, figvector.cli.vectorize_png)


if __name__ == "__main__":
    unittest.main()
