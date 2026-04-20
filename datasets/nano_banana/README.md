# Nano Banana real-sample kit

This folder is the local workspace for collecting and evaluating real Nano Banana PNG figures.

## How to use it

1. Put real PNG files in `inbox/`.
2. Optionally create OCR sidecars in `ocr_sidecars/` using the format:
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
3. Register each sample in `manifest.json`.
4. If you want a lightweight benchmark, add an `expected` block like:
   ```json
   {
     "min_primitives": 6,
     "min_texts": 4,
     "primitive_counts": {"rectangle": 3, "arrow": 2},
     "relation_counts": {"flows_to": 2, "labels": 4},
     "required_texts": ["EGFR", "RAS"]
   }
   ```
5. Run `figvector dataset-run datasets/nano_banana --ocr-backend sidecar-json`.
6. Inspect `outputs/<sample-id>/` for SVG, draw.io, and JSON outputs.
7. Run `figvector dataset-eval datasets/nano_banana` to compare generated scene graphs against the expected checks.

This scaffold exists so the repo can grow from a synthetic demo toward a real evaluation set without guessing hidden file layouts each time.
