# Nano Banana real-sample kit

This folder is the local workspace for collecting and evaluating real Nano Banana PNG figures.

## How to use it

1. Put real PNG files in `inbox/`.
2. Run `figvector dataset-register datasets/nano_banana` to register new PNGs into the manifest and create empty OCR sidecars.
3. Fill OCR sidecars in `ocr_sidecars/` using the format:
   ```json
   {
     "texts": [
       {
         "text": "EGFR",
         "bbox": {"x": 10, "y": 20, "width": 60, "height": 20},
         "confidence": 0.98
       }
     ]
   }
   ```
4. Optionally add an `expected` block per sample in `manifest.json` for lightweight benchmark checks.
5. Run `figvector dataset-run datasets/nano_banana --ocr-backend sidecar-json --profile real`.
6. Run `figvector dataset-bootstrap-expected datasets/nano_banana` if you want to seed missing `expected` blocks from the current reports as a starting point.
7. Inspect `outputs/index.html`, `outputs/<sample-id>/review.html`, `outputs/<sample-id>/summary.md`, `outputs/report.md`, and `outputs/evaluation-report.md` for generated artifacts and summaries.
8. Run `figvector dataset-eval datasets/nano_banana` to compare generated scene graphs against the expected checks.
9. Run `figvector dataset-optimize datasets/nano_banana --ocr-backend sidecar-json --profiles synthetic real` to compare analysis profiles on the same dataset.

This scaffold exists so the repo can grow from a synthetic demo toward a real evaluation set without guessing hidden file layouts each time.
