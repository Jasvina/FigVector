# FigVector Project Status and Roadmap

_Last updated: 2026-04-21_

FigVector is now an early but working **scientific figure reconstruction workbench**. The repository can take clean scientific PNG diagrams, recover an initial scene graph, export editable SVG / draw.io files, and run a real-sample dataset workflow with lightweight evaluation and review pages.

This document records the current state of the project, what has already been implemented, how to reproduce the current behavior, and what should be optimized next.

---

## Current Status

### Overall stage

FigVector has moved past the empty-repository / concept stage. It is currently an **Alpha prototype with a complete local refinement loop**:

1. Put PNG samples into `datasets/nano_banana/inbox/`.
2. Register samples into `manifest.json`.
3. Run reconstruction.
4. Review generated SVG / draw.io / JSON outputs.
5. Bootstrap or edit expected checks.
6. Evaluate failures.
7. Compare analysis profiles.
8. Use the failure reports to guide the next precision improvement.

### Current conclusion

The basic project infrastructure is now in place. The next meaningful progress should come from **real Nano Banana PNG samples** and benchmark-driven refinement, not from adding more abstract scaffolding.

---

## Implemented Capabilities

### Core reconstruction pipeline

Implemented files:

- `src/figvector/png.py`
- `src/figvector/analysis.py`
- `src/figvector/relations.py`
- `src/figvector/pipeline.py`
- `src/figvector/models.py`
- `src/figvector/config.py`

Current capabilities:

- Pure Python PNG read/write path.
- RGBA raster model.
- Background estimation.
- Color quantization and connected-component segmentation.
- Primitive detection for:
  - `rectangle`
  - `ellipse`
  - `line`
  - `arrow`
  - `polyline`
  - `region`
- Basic relation recovery:
  - `flows_to`
  - `linked_to`
  - `labels`
- Analysis profiles:
  - `synthetic`
  - `real`

### Exporters

Implemented files:

- `src/figvector/export_svg.py`
- `src/figvector/export_drawio.py`

Current outputs:

- Editable SVG.
- draw.io XML.
- JSON scene graph reports.

### OCR adapter

Implemented file:

- `src/figvector/ocr.py`

Current OCR modes:

- `none`
- `sidecar-json`
- `tesseract-cli`

The recommended current workflow is `sidecar-json`, because it keeps the project dependency-light while allowing real text boxes to enter the scene graph.

### Demo assets

Implemented files:

- `examples/demo/demo-input.png`
- `examples/demo/demo-input.ocr.json`
- `examples/demo/demo-output.svg`
- `examples/demo/demo-output.drawio`
- `examples/demo/demo-report.json`

The demo exercises the current full loop: primitives, text blocks, relations, SVG output, draw.io output, and JSON scene graph output.

### Real-sample dataset workflow

Implemented files:

- `src/figvector/dataset.py`
- `src/figvector/eval.py`
- `datasets/nano_banana/README.md`
- `datasets/nano_banana/manifest.json`

Current commands:

```bash
PYTHONPATH=src python3 -m figvector dataset-init datasets/nano_banana
PYTHONPATH=src python3 -m figvector dataset-register datasets/nano_banana
PYTHONPATH=src python3 -m figvector dataset-run datasets/nano_banana --ocr-backend sidecar-json --profile real
PYTHONPATH=src python3 -m figvector dataset-bootstrap-expected datasets/nano_banana
PYTHONPATH=src python3 -m figvector dataset-eval datasets/nano_banana
PYTHONPATH=src python3 -m figvector dataset-optimize datasets/nano_banana --ocr-backend sidecar-json --profiles synthetic real
```

Dataset outputs include:

- `outputs/summary.json`
- `outputs/report.md`
- `outputs/index.html`
- `outputs/<sample-id>/summary.md`
- `outputs/<sample-id>/review.html`
- `outputs/<sample-id>/output.svg`
- `outputs/<sample-id>/output.drawio`
- `outputs/<sample-id>/report.json`
- `outputs/evaluation-summary.json`
- `outputs/evaluation-report.md`
- `outputs/optimization-summary.json`
- `outputs/optimization-report.md`
- `outputs/optimization-comparison.json`
- `outputs/optimization-comparison.md`

### README visual identity

Implemented files:

- `docs/assets/figvector-poster.svg`
- `docs/assets/figvector-poster.png`
- `docs/design/figvector-poster-philosophy.md`

The README now opens with a richer promotional poster that explains the central story visually:

`PNG raster → semantic lift → editable SVG / draw.io scene graph`

---

## Verification Status

The current core test suite passes:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Latest verified result:

```text
Ran 4 tests
OK
```

The tests currently cover:

- PNG round trip.
- Demo asset generation.
- Single-image vectorization.
- SVG / draw.io / JSON output creation.
- Dataset scaffold creation.
- Inbox sample registration.
- Dataset batch run.
- Dataset evaluation.
- Dataset optimization sweep.
- Expected-check bootstrapping.
- HTML review page generation.

---

## How to Use the Current Alpha

### Run the demo

```bash
PYTHONPATH=src python3 -m figvector demo --output-dir examples/demo
```

### Vectorize one PNG

```bash
PYTHONPATH=src python3 -m figvector vectorize path/to/input.png \
  -o output.svg \
  --report output.json \
  --drawio-output output.drawio \
  --ocr-backend sidecar-json \
  --ocr-sidecar path/to/input.ocr.json \
  --profile real
```

### Start a real-sample refinement loop

```bash
# 1. Put PNGs into datasets/nano_banana/inbox/

# 2. Register them
PYTHONPATH=src python3 -m figvector dataset-register datasets/nano_banana

# 3. Fill OCR sidecars if available

# 4. Run reconstruction
PYTHONPATH=src python3 -m figvector dataset-run datasets/nano_banana --ocr-backend sidecar-json --profile real

# 5. Open outputs/index.html and inspect sample review pages

# 6. Bootstrap expected checks
PYTHONPATH=src python3 -m figvector dataset-bootstrap-expected datasets/nano_banana

# 7. Manually refine expected checks in manifest.json

# 8. Evaluate
PYTHONPATH=src python3 -m figvector dataset-eval datasets/nano_banana

# 9. Compare profiles
PYTHONPATH=src python3 -m figvector dataset-optimize datasets/nano_banana --ocr-backend sidecar-json --profiles synthetic real
```

---

## What Is Not Done Yet

The project is not yet a finished production vectorizer. The current bottlenecks are:

- No committed real Nano Banana PNG benchmark set yet.
- OCR quality is not solved end-to-end; the adapter exists, but robust OCR requires real samples and likely optional dependencies.
- Primitive detection is heuristic-based and will fail on complex real figures.
- Curved arrows are not robustly reconstructed.
- Multi-bend polylines need stronger path tracing.
- Grouping and layer order are still simple.
- Text-to-shape attachment is nearest-object based and needs better semantics.
- draw.io output is useful but not yet high-fidelity.
- No local web UI yet.

---

## Future Optimization Plan

### Phase 1: First real benchmark set

Goal: build a small but high-value real-sample loop.

Tasks:

- Add 5-10 real Nano Banana PNGs into `datasets/nano_banana/inbox/`.
- Register them with `dataset-register`.
- Add or generate OCR sidecars.
- Run `dataset-run`.
- Open `outputs/index.html` and inspect each `review.html`.
- Use `dataset-bootstrap-expected` to seed expected checks.
- Manually correct `expected` blocks.
- Use `dataset-eval` and `dataset-optimize` to identify failure patterns.

Success criteria:

- At least 5 real samples registered.
- Each sample has a useful OCR sidecar or explicit note explaining text gaps.
- Each sample has an `expected` block.
- Evaluation reports show which failure modes are most common.

### Phase 2: Heuristic hardening

Goal: improve real sample pass rates without adding heavy dependencies.

Candidate improvements:

- More robust shape classification.
- Better line/arrow separation.
- Multi-bend polyline tracing.
- Curved-arrow approximation.
- Better connected-component merging / splitting.
- Better relation thresholds by profile.
- Better label attachment using spatial zones, not only nearest distance.
- Optional per-sample configuration overrides.

Success criteria:

- `real` profile consistently outperforms `synthetic` on real samples.
- Evaluation failures become concentrated in a few known hard cases.
- HTML review pages visually show meaningful reconstruction for most samples.

### Phase 3: OCR and text workflow

Goal: make text recovery less manual.

Candidate improvements:

- Improve `tesseract-cli` integration and docs.
- Add OCR confidence filtering by profile.
- Merge fragmented OCR tokens into lines.
- Support label grouping and text normalization.
- Add optional OCR dependency path if the project accepts dependencies later.

Success criteria:

- Text boxes appear in scene graph with useful labels.
- `labels` relations become stable enough for real diagrams.

### Phase 4: Editable-output quality

Goal: improve downstream editing quality.

Candidate improvements:

- Better draw.io node styles.
- Grouped SVG layers.
- Stable IDs and classes for all primitives.
- Optional export profiles: `clean-svg`, `annotated-svg`, `drawio`.
- Better layer ordering and z-index recovery.

Success criteria:

- A user can open the output in Inkscape/draw.io and make meaningful edits without manually rebuilding the whole diagram.

### Phase 5: Product surface

Goal: make the project easy to try.

Candidate improvements:

- Local static web demo.
- Drag-and-drop PNG input.
- Side-by-side original/reconstructed review.
- Download SVG / draw.io / JSON.
- Error and evaluation display in the UI.

Success criteria:

- A new user can test one image without reading CLI docs first.

### Phase 6: Research/publication direction

Goal: make FigVector more than a utility script.

Candidate improvements:

- Public benchmark format.
- Real-sample annotation guide.
- Comparison against traditional tracing baselines.
- VLM-assisted repair loop.
- Optional model-based semantic correction.
- Paper-style experiments around scientific figure reconstruction.

Success criteria:

- FigVector can become a useful open-source project and a credible research artifact.

---

## Recommended Next Action

The next best action is to add the first real PNG samples. Without real images, additional infrastructure has diminishing returns.

Recommended immediate workflow:

```bash
# Put real PNG files here:
datasets/nano_banana/inbox/

# Then run:
PYTHONPATH=src python3 -m figvector dataset-register datasets/nano_banana
PYTHONPATH=src python3 -m figvector dataset-run datasets/nano_banana --ocr-backend sidecar-json --profile real
```

Then open:

```text
datasets/nano_banana/outputs/index.html
```

That review surface should guide the next precision work.
