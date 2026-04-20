from __future__ import annotations

import argparse
from pathlib import Path

from .demo import build_demo_assets
from .pipeline import vectorize_png


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FigVector: vectorize clean PNG diagrams into editable SVG.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    vectorize = subparsers.add_parser("vectorize", help="Convert a PNG into an SVG and optional JSON report.")
    vectorize.add_argument("input", help="Path to the source PNG file.")
    vectorize.add_argument("-o", "--output", required=True, help="Path to the output SVG file.")
    vectorize.add_argument("--report", help="Optional JSON report path.")
    vectorize.add_argument("--background-threshold", type=int, default=38, help="Color distance threshold for foreground detection.")
    vectorize.add_argument("--min-area", type=int, default=32, help="Minimum connected-component area to keep.")

    demo = subparsers.add_parser("demo", help="Generate a synthetic demo PNG and vectorize it.")
    demo.add_argument("--output-dir", default="examples/demo", help="Directory where demo assets will be written.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "vectorize":
        vectorize_png(
            input_path=args.input,
            output_path=args.output,
            report_path=args.report,
            background_threshold=args.background_threshold,
            min_area=args.min_area,
        )
        print(f"Wrote SVG to {Path(args.output).resolve()}")
        if args.report:
            print(f"Wrote report to {Path(args.report).resolve()}")
        return 0

    result = build_demo_assets(args.output_dir)
    print(f"Wrote demo PNG to {result['png'].resolve()}")
    print(f"Wrote demo SVG to {result['svg'].resolve()}")
    print(f"Wrote demo report to {result['report'].resolve()}")
    return 0
