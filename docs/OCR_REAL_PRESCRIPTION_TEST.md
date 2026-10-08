# Real handwritten prescription test: GLM-OCR → parser → drug catalog → evaluate_episode

Date: 2026-10-08. Code: `main` at `e8caeb8` (no pipeline or rule changes for this test).

**Answer:** the pipeline runs end to end on real handwritten Indian prescriptions without errors.
It is **safe** but **not yet useful**:
- **Safe:** no drug was ever accepted as the wrong drug, and every uncertain name stopped at R0 as CANNOT_ASSESS.
- **Not yet useful:** OCR misreads most handwritten drug names. The line parser turns clinical notes into many false "orders" and loses directions on multi-line or form-layout prescriptions. Only 2 of 6 antibiotic orders were identified.

## Dataset

| | |
|---|---|
| Name | MIRAGE "100 medical records dataset" (public subset) |
| Source | https://huggingface.co/datasets/tavishm/100-handwritten-medical-records (revision `281d143`) |
| Paper | Mankash et al., arXiv:2410.09729 (2024) |
| Content | Handwritten Indian prescriptions written by doctors on simulated cases (no real patients, per the paper); English with some Hindi |
| License | None declared for the dataset. The paper is CC BY 4.0, which does not cover the images. |
| Redistribution | Not confirmed. Images kept locally in `data/ocr_test/mirage/images/` (git-ignored). |
| Sample | First 40 of 100 images by file name. 39 are handwritten; 1 is a mainly printed e-prescription with a handwritten line. |

Rejected candidates:
- **HMR-65** (Indian, handwritten): returns HTTP 401, so it isn't public.
- **RxHandBD** and the Bangladesh word datasets: single-word crops, not full prescriptions.
- **Kaggle sets:** need a login to download.

## Method

1. **Run the pipeline.** `scripts/ocr_real_eval.py` runs the real pipeline on every image:
   - GLM-OCR at the pinned revision, on an RTX 3050 in bf16;
   - transcript cleanup and line parser;
   - `Catalog.normalize`, then `DrugOrder`;
   - `evaluate_episode()`.

   It records the transcript, every order, its fields and its findings.
2. **Fixed inputs.** The images don't provide these, so they are fixed:
   - **Rule pack:** no guideline syndromes, because Person 3's rule pack isn't merged.
   - **Patient:** an adult placeholder with unknown allergy status and no weight or creatinine.

   Indication, dose and duration rules therefore return CANNOT_ASSESS by design.
3. **Ground truth.** I read 13 images by eye and wrote down every drug line (`ground_truth.csv`): 52 drug lines, 6 of them antibiotics. One of the 13 images had no drugs. Readings marked `uncertain` may be wrong; the hardest image (`6aQTpGja`) was excluded as unreadable.
4. **Adjudication.** Each ground-truth line was compared by hand with the transcript and the pipeline order (`adjudication.csv`). The stage at fault was recorded: OCR, page layout, parser, or catalog. `scripts/ocr_score.py` prints an automatic pairing as a starting point; its pairings were checked by hand and are not used for the numbers below.

## Results

### All 40 images (automatic)

| | |
|---|---|
| Images transcribed without error | 40 / 40 (1.6-7.9 s each; 205 s total including model load) |
| Images where `evaluate_episode()` ran | 40 / 40 |
| Orders created | 342 (most are not drugs; see below) |
| Orders identified by the catalog | 2 (azithromycin, cefepime), both correct |
| Unidentified orders | 340: 338 NO_MATCH, 2 AMBIGUOUS. Every one has exactly one finding, R0 CANNOT_ASSESS, and no other rule ran on a guessed drug. |
| Antibiotic names visible in any transcript | 3 (azithromycin, cefepime, "Malacef" for Mahacef) |

### 13 hand-checked images (52 drug lines)

| Stage | Result |
|---|---|
| OCR read the drug name correctly | 14 / 52 (27%). 32 misread, 6 missing from the transcript. |
| Parser turned the line into an order | 41 / 52 |
| False orders (notes, labels, fragments) in these images | about 71 of 112 orders |
| Antibiotic orders identified correctly | 2 / 6 (azithromycin from printed text; cefepime handwritten) |
| Antibiotics returned for confirmation (R0) | 3 / 6 misread → NO_MATCH; 1 dropped by the parser |
| Drug accepted as the wrong drug | **0** |
| Non-antibiotics identified | 0 / 36. Expected: the catalog lists antibiotics only, so each becomes R0 CANNOT_ASSESS. |

Field extraction, counted only where the field had a value:

| Field | Correct | Missed | Wrong value | Not expressible |
|---|---|---|---|---|
| Dose (mg) | 9 | 0 | 6 | – |
| Frequency | 4 | 28 | 0 | – |
| Route | 14 | 24 | 0 | – |
| Duration | 4 | 8 | 0 | 10 (months) |

**Where the failures came from** (a line can have several causes):

| Cause | Lines |
|---|---|
| OCR misreading | 44 |
| Parser | 17 |
| Page layout (OCR merging form labels or struck-out text into drug lines) | 6 |
| Person 2 normalization | 0 |

Normalization never produced a wrong drug. It can't recognise misread names or Indian brands outside its small list, which is intended.

## Examples

**Successes**
- `62qlxpSw`: "Inj Cefepime 1 g IV BD" in handwriting.
  - The order became `cefepime`, 1000 mg, R0 PASS.
  - R2 ran, and the renal check returned CANNOT_ASSESS (route and creatinine unknown).
- `4J7Jyojz`: "Syp. Ostocalcium 5 ml TDS".
  - The name was read correctly; TDS gave 3 doses a day and syrup gave route PO.
  - It was then correctly not identified as an antibiotic.
- `4J7Jyojz`: "Tobramycin eye drops ... TDS x 5 days" was OCR'd as "To brachyin".
  - NO_MATCH, then R0 CANNOT_ASSESS. The misread antibiotic was stopped, not guessed.
  - Frequency and duration were still read; route was correctly left empty for eye drops.

**Failures**
- `8E7HL1bW` (cursive): "T. Augmentin 625 mg x 5 d" was transcribed as "7. Haymite 6215 x 60g". All four drug lines were unreadable. Safe: NO_MATCH.
- `8aTCyXjA`: "Tb Oflox-TZ 1-0-1" was merged with the printed "Follow up:" label. The parser then discarded it as a follow-up line, so the antibiotic disappeared without a confirmation prompt.
- `2nPPipXy` (printed): the brand, ingredient and directions are on separate lines.
  - Azithromycin was identified, but it got `dose_mg = 200`, which is the strength per 5 ml. The prescribed 3.5 ml is about 140 mg.
  - The directions line ("3.5 ml - Once a day") was dropped, so frequency was lost.
- `0fmQCjuf`: clinical notes with no drugs produced 12 "orders" ("Febrile", "CVS / MAD", ...). Each gives an R0 CANNOT_ASSESS HIGH finding: safe, but noisy.
- Common OCR confusions:
  - Tab → "Talc"/"Qb"/"7.", and Cap → "Cep"/"Cp";
  - BD → "Bs"/"IBD", OD → "00"/"1.03", TDS → "7DS";
  - I.V → "1.0 V", and 500 → 300.

## Limitations

- **Small hand-checked sample:** 13 images; counts, not reliable percentages. My readings of cursive lines can be wrong.
- **One source:** the images come from one dataset of simulated cases; real clinic photos may differ.
- **Few antibiotics:** only 6 antibiotic orders in the checked subset.
- **No rule pack or patient data:** indication, dose and duration checks couldn't be exercised.

## Before the demo

1. **Line parser (biggest fixable gain):**
   - Don't emit lines without a medicine marker (form word, strength, or Rx list item). That removes most of the 71 false orders.
   - Strip printed form labels ("Follow up:", "Date:", "Examination:", ...) from the start of a line instead of dropping it.
   - Group a numbered item with its following ingredient and direction lines.
   - Accept OCR variants: "Cp", "Cep", "Talc"/"Qb" for Tab, "1.0 V"/"i.v" for IV, "Bs" for BD, words like "ten days", and "x N months".
2. **Dose from concentrations:** never take `dose_mg` from a strength written per volume ("200 mg" on a suspension, "30 mg" per 5 ml). Leave it empty.
3. **Renal check with unknown route:** found during this test, and not changed. The renal check (R4) currently PASSes azithromycin with the route unknown, because the only renal row is for IV. It should return CANNOT_ASSESS when the route is missing and the source is route-specific. This is Person 2's `renal.py`; it needs a separate decision.
4. **Non-antibiotics:** add a non-antibiotic list (for example NLEM 2022), so ordinary drugs aren't each flagged HIGH by R0.
5. **Demo images:** demo with clearly written prescriptions, and show the "please confirm" path deliberately. Raw GLM-OCR on cursive handwriting won't read most names.

## Reproduce

```bash
# 1. Images (see data/ocr_test/mirage/README.md for the download command)
# 2. Pipeline (needs requirements-ocr.txt: torch, transformers, Pillow, accelerate)
python scripts/ocr_real_eval.py data/ocr_test/mirage/images --out data/ocr_test/mirage/results
# 3. Automatic pairing against ground truth (check the pairings by hand)
python scripts/ocr_score.py data/ocr_test/mirage
```
