# Contributing to FigVector

Thanks for helping improve FigVector.

## Good first contribution areas

- Add real scientific PNG samples plus OCR sidecars under `datasets/nano_banana/`
- Improve heuristic detection for arrows, polylines, rounded boxes, or grouping
- Tighten evaluation expectations and review pages for real samples
- Improve exporters while keeping SVG and draw.io outputs editable
- Expand tests around CLI, dataset workflows, and scene-graph quality checks

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

If you prefer not to install the package during early experiments, the repo also supports direct source execution with `PYTHONPATH=src`.

## Development loop

```bash
figvector --help
figvector demo --output-dir examples/demo
figvector demo --variant nested --output-dir examples/demo
figvector vectorize examples/demo/demo-input.png \
  -o /tmp/figvector-demo.svg \
  --report /tmp/figvector-demo.json \
  --drawio-output /tmp/figvector-demo.drawio \
  --review-html /tmp/figvector-demo.html \
  --ocr-backend sidecar-json \
  --ocr-sidecar examples/demo/demo-input.ocr.json
python -m unittest discover -s tests -v
python -m build
```

`--review-html` 生成的是快速人工验收入口：它把输入 PNG、输出 SVG 和运行报告并排放到同一页，适合在提交前先做肉眼检查。仓库内置的 `demo` / `demo --variant nested` 也会直接产出 `examples/demo/demo-review.html` 和 `examples/demo/nested-demo-review.html`，可用来快速验收 basic / nested 两个 demo。

## Project conventions

- Keep diffs small, reviewable, and reversible.
- Prefer improving existing heuristics before adding new abstractions.
- Avoid new runtime dependencies unless there is a strong demonstrated need.
- Preserve the current editability-first goal: SVG and draw.io outputs should stay easy to tweak by hand.
- When changing reconstruction logic, include a regression test or a fixture-backed validation path.

## Dataset workflow notes

The current alpha improves fastest when changes are driven by real examples.

1. Put PNG samples into `datasets/nano_banana/inbox/`.
2. Run `figvector dataset-register datasets/nano_banana`.
3. Add OCR sidecars when text matters.
4. Run `figvector dataset-run datasets/nano_banana --ocr-backend sidecar-json --profile real`.
5. Inspect `datasets/nano_banana/outputs/index.html` and each sample review page.
6. Update `manifest.json` expectations and rerun `dataset-eval` / `dataset-optimize`.

## Pull requests

A strong pull request usually includes:

- a clear statement of the figure types or failure cases it improves;
- before/after artifacts or evaluation notes when behavior changes;
- tests that cover the change; and
- an honest note about remaining edge cases.
