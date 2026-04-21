from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dataset import (
    bootstrap_expected_from_outputs,
    create_dataset_scaffold,
    evaluate_dataset,
    optimize_dataset,
    register_inbox_samples,
    run_dataset,
)
from .demo import build_demo_assets
from .ocr import OCRConfig
from .pipeline import vectorize_png


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FigVector: vectorize clean PNG diagrams into editable SVG.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    vectorize = subparsers.add_parser("vectorize", help="Convert a PNG into an SVG and optional JSON report.")
    vectorize.add_argument("input", help="Path to the source PNG file.")
    vectorize.add_argument("-o", "--output", required=True, help="Path to the output SVG file.")
    vectorize.add_argument("--report", help="Optional JSON report path.")
    vectorize.add_argument("--drawio-output", help="Optional draw.io XML output path.")
    vectorize.add_argument("--profile", default="real", choices=["synthetic", "real"], help="Analysis profile preset.")
    vectorize.add_argument("--background-threshold", type=int, help="Color distance threshold for foreground detection.")
    vectorize.add_argument("--min-area", type=int, help="Minimum connected-component area to keep.")
    vectorize.add_argument("--color-quantization", type=int, help="Color bucketing step for primitive splitting.")
    vectorize.add_argument("--ocr-backend", default="none", choices=["none", "sidecar-json", "tesseract-cli"], help="OCR backend to use for text recovery.")
    vectorize.add_argument("--ocr-sidecar", help="Optional OCR sidecar JSON path.")

    demo = subparsers.add_parser("demo", help="Generate a synthetic demo PNG and vectorize it.")
    demo.add_argument("--output-dir", default="examples/demo", help="Directory where demo assets will be written.")

    dataset_init = subparsers.add_parser("dataset-init", help="Create a real-sample dataset scaffold for Nano Banana PNGs.")
    dataset_init.add_argument("root", nargs="?", default="datasets/nano_banana", help="Dataset root directory.")

    dataset_register = subparsers.add_parser("dataset-register", help="Register PNGs from inbox/ into the dataset manifest.")
    dataset_register.add_argument("root", nargs="?", default="datasets/nano_banana", help="Dataset root directory.")

    dataset_bootstrap = subparsers.add_parser("dataset-bootstrap-expected", help="Populate missing expected blocks from existing dataset reports.")
    dataset_bootstrap.add_argument("root", nargs="?", default="datasets/nano_banana", help="Dataset root directory.")
    dataset_bootstrap.add_argument("--output-dir", help="Optional output directory override.")
    dataset_bootstrap.add_argument("--overwrite", action="store_true", help="Overwrite existing expected blocks.")
    dataset_bootstrap.add_argument("--required-text-limit", type=int, default=8, help="Maximum number of required texts to seed from each report.")

    dataset_run = subparsers.add_parser("dataset-run", help="Vectorize every sample registered in a dataset manifest.")
    dataset_run.add_argument("root", nargs="?", default="datasets/nano_banana", help="Dataset root directory.")
    dataset_run.add_argument("--output-dir", help="Optional output directory override.")
    dataset_run.add_argument("--ocr-backend", default="none", choices=["none", "sidecar-json", "tesseract-cli"], help="OCR backend for dataset processing.")
    dataset_run.add_argument("--profile", default="real", choices=["synthetic", "real"], help="Analysis profile preset for dataset processing.")

    dataset_eval = subparsers.add_parser("dataset-eval", help="Evaluate existing dataset outputs against lightweight expectations.")
    dataset_eval.add_argument("root", nargs="?", default="datasets/nano_banana", help="Dataset root directory.")
    dataset_eval.add_argument("--output-dir", help="Optional output directory override.")

    dataset_optimize = subparsers.add_parser("dataset-optimize", help="Sweep analysis profiles and compare dataset-level scores.")
    dataset_optimize.add_argument("root", nargs="?", default="datasets/nano_banana", help="Dataset root directory.")
    dataset_optimize.add_argument("--ocr-backend", default="none", choices=["none", "sidecar-json", "tesseract-cli"], help="OCR backend for profile optimization.")
    dataset_optimize.add_argument("--profiles", nargs="+", default=["synthetic", "real"], choices=["synthetic", "real"], help="Profile list to compare.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "vectorize":
        vectorize_png(
            input_path=args.input,
            output_path=args.output,
            report_path=args.report,
            drawio_path=args.drawio_output,
            profile=args.profile,
            background_threshold=args.background_threshold,
            min_area=args.min_area,
            color_quantization=args.color_quantization,
            ocr=OCRConfig(backend=args.ocr_backend, sidecar_path=args.ocr_sidecar),
        )
        print(f"Wrote SVG to {Path(args.output).resolve()}")
        if args.report:
            print(f"Wrote report to {Path(args.report).resolve()}")
        if args.drawio_output:
            print(f"Wrote draw.io file to {Path(args.drawio_output).resolve()}")
        return 0

    if args.command == "demo":
        result = build_demo_assets(args.output_dir)
        print(f"Wrote demo PNG to {result['png'].resolve()}")
        print(f"Wrote demo OCR sidecar to {result['ocr'].resolve()}")
        print(f"Wrote demo SVG to {result['svg'].resolve()}")
        print(f"Wrote demo report to {result['report'].resolve()}")
        print(f"Wrote demo draw.io file to {result['drawio'].resolve()}")
        return 0

    if args.command == "dataset-init":
        result = create_dataset_scaffold(args.root)
        print(f"Wrote dataset scaffold to {Path(result['root']).resolve()}")
        print(f"Manifest: {Path(result['manifest']).resolve()}")
        return 0

    if args.command == "dataset-register":
        result = register_inbox_samples(args.root)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "dataset-bootstrap-expected":
        result = bootstrap_expected_from_outputs(
            args.root,
            output_dir=args.output_dir,
            overwrite=args.overwrite,
            required_text_limit=args.required_text_limit,
        )
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "dataset-eval":
        result = evaluate_dataset(args.root, output_dir=args.output_dir)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "dataset-optimize":
        result = optimize_dataset(args.root, profiles=args.profiles, ocr_backend=args.ocr_backend)
        print(json.dumps(result, indent=2))
        return 0

    result = run_dataset(args.root, output_dir=args.output_dir, ocr_backend=args.ocr_backend, profile=args.profile)
    print(json.dumps(result, indent=2))
    return 0
