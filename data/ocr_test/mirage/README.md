# MIRAGE 100 handwritten medical records: local OCR test sample

| Field | Value |
|---|---|
| Dataset | "100 medical records dataset" (MIRAGE public subset) |
| Source | https://huggingface.co/datasets/tavishm/100-handwritten-medical-records, revision `281d143ad1f575c6c27a6f6fc8cffdd9de15016d` (last modified 2024-10-12) |
| Described in | Mankash et al., "MIRAGE: Multimodal Identification and Recognition of Annotations in Indian General Prescriptions", arXiv:2410.09729 (2024) |
| What it is | Photographs/scans of handwritten Indian outpatient and inpatient prescriptions, written by doctors on simulated cases (the paper: "simulated medical records from 1,133 doctors across India", provided by Medyug Technology). Mostly handwritten; one sampled image is a mainly printed e-prescription with one handwritten line. English with some Hindi. |
| Labels | None released. `ground_truth.csv` here is our own reading of 13 images, made by eye; readings marked `uncertain` may be wrong. |
| License | **No license declared for the dataset** (no dataset card or license tag on Hugging Face as of 2026-10-08). The paper itself is CC BY 4.0; that covers the article, not the images. |
| Redistribution | **Not confirmed. Do not commit or republish the images.** `images/` and `results/` are git-ignored. |
| Downloaded | 2026-10-08, first 40 of 100 files in sorted file-name order, 40 JPEG images (17 MB) |

## Files

- `images/` (git-ignored): the 40 downloaded images, unmodified.
- `results/` (git-ignored): output of `scripts/ocr_real_eval.py` (`results.jsonl`, `orders.csv`).
- `ground_truth.csv`: hand-read drug lines for 13 images (see `docs/OCR_REAL_PRESCRIPTION_TEST.md`).

## Re-download

```bash
REV=281d143ad1f575c6c27a6f6fc8cffdd9de15016d
mkdir -p data/ocr_test/mirage/images
curl -s "https://huggingface.co/api/datasets/tavishm/100-handwritten-medical-records/revision/$REV" \
  | python3 -c "import json,sys; print('\n'.join(sorted(s['rfilename'] for s in json.load(sys.stdin)['siblings'] if s['rfilename'].lower().endswith('.jpg'))[:40]))" \
  | while read -r f; do
      curl -sfL "https://huggingface.co/datasets/tavishm/100-handwritten-medical-records/resolve/$REV/$f" \
        -o "data/ocr_test/mirage/images/$f"
    done
```
