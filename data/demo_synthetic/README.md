# SYNTHETIC / DEMO DATA

Five invented prescription cases for **manual entry through the frontend** (Prescription → Audit → Action).
No real patient data. Nothing loads, seeds or reads this folder: it is not used by the engine, the
tests or the database.

Every syndrome code, drug, route and dose range comes from the current rule pack
(`backend/stewardship/rulepack/syndromes.yaml`, NCDC NTG 2025). The cases do not add or change any guideline
recommendation or rule. The expected findings below are what the engine actually returned
when the cases were run through the API on 2026-10-08 (`typed-rx-mvp`). `cases.json` holds each case as the
exact `POST /api/episodes` body.

| Case | Demonstrates | Expected findings | Status |
|---|---|---|---|
| SYN-DEMO-01 | Guideline-concordant | R0-R6 all PASS | OK |
| SYN-DEMO-02 | Drug not listed for the syndrome | R1 FLAG, R2 FLAG (Watch; Access option amoxicillin), R3/R5 CANNOT_ASSESS | FLAGGED |
| SYN-DEMO-03 | Dose and duration | R3 FLAG (1500 mg/day < 3000), R5 FLAG (10 d > 5-7) | FLAGGED |
| SYN-DEMO-04 | Culture resistance | C3 FLAG (E. coli resistant to nitrofurantoin); R0-R6 PASS | FLAGGED |
| SYN-DEMO-05 | Missing information | R3, R4, R5, R6 CANNOT_ASSESS, each naming the missing input | FLAGGED |

"INCOMPLETE" is only used when a check crashes. Missing inputs give CANNOT_ASSESS findings and a FLAGGED
evaluation.

## What to type

Leave any field not listed blank. "Culture: Not sent" means leave the culture section at its default.

### SYN-DEMO-01: concordant
- Patient ID `SYN-DEMO-01` · Age 42 · Sex F · Weight 62 · Creatinine 0.8 · Allergy: None known
- Setting OPD · Syndrome `cap_opd_no_comorbidity` (Community-acquired pneumonia, OPD, without comorbidities)
- Prescription: `Tab Amoxicillin 1 g PO TDS x 5 days`
- Culture: Not sent

### SYN-DEMO-02: wrong antibiotic
- Patient ID `SYN-DEMO-02` · Age 35 · Sex M · Weight 74 · Creatinine 0.9 · Allergy: None known
- Setting OPD · Syndrome `cap_opd_no_comorbidity`
- Prescription: `Tab Ciprofloxacin 500 mg PO BD x 5 days`
- Culture: Not sent

### SYN-DEMO-03: dose and duration
- Patient ID `SYN-DEMO-03` · Age 58 · Sex M · Weight 80 · Creatinine 1.0 · Allergy: None known
- Setting OPD · Syndrome `cap_opd_no_comorbidity`
- Prescription: `Tab Amoxicillin 500 mg PO TDS x 10 days`
- Culture: Not sent

### SYN-DEMO-04: culture resistance
- Patient ID `SYN-DEMO-04` · Age 29 · Sex F · Weight 55 · Creatinine 0.7 · Allergy: None known
- Setting OPD · Syndrome `cystitis` (Uncomplicated cystitis)
- Prescription: `Tab Nitrofurantoin 100 mg PO BD x 5 days`
- Culture: specimen `urine` · status Positive (FINAL) · organism `Escherichia coli`
  - Susceptibility: `Nitrofurantoin` = R, `Cotrimoxazole` = S

### SYN-DEMO-05: missing information
- Patient ID `SYN-DEMO-05` · Age 67 · Sex M · Weight blank · Creatinine blank · Allergy: Unknown
- Setting OPD · Syndrome `cap_opd_no_comorbidity`
- Prescription: `Amoxicillin 1 g` (no frequency, route or duration)
- Culture: Not sent
- Expected: R3 missing `freq_per_day`, R4 missing `weight_kg` and `serum_creatinine_mg_dl`, R5 missing
  `duration_days`, R6 missing `allergy_status` (beta-lactam). R0, R1 and R2 still PASS.

## Prescription images

`images/` holds one typed, printed prescription per case (1240 x 1754 PNG, fictional hospital and doctor, footer
"SYNTHETIC DEMO DATA"). The exact text of every image is in `prescriptions.json`. `make_images.py` draws them, but
only after the text passes two checks:

1. The whole page text goes through `read_orders` (transcript → parser → Catalog). It must give exactly one
   identified order with the DrugOrder fields below, whether the two-column rows are read as one line or two.
2. The order text, with the patient, syndrome and culture from `cases.json`, goes through `POST /api/evaluate`. It
   must give the findings and status listed above.

```
python data/demo_synthetic/make_images.py             # check the text, then draw images/
python data/demo_synthetic/make_images.py --ocr glm   # also OCR the images (glm | qwen; needs requirements-ocr.txt)
```

The first drafts failed check 1. The parser read the hospital name, "Serum creatinine: 0.8 mg/dL", "Setting: OPD"
and "Weight: not recorded" as medicine lines. Only the synthetic wording was changed: the creatinine went under
"Investigations:", the setting became "Patient setting:", and the hospital name and missing-weight text were
lengthened.

| Image | Demonstrates | Syndrome (select in form) | Rx line exactly as printed | DrugOrder read | Expected findings | Expected action | Culture |
|---|---|---|---|---|---|---|---|
| `images/SYN-DEMO-01_concordant.png` | Concordant | `cap_opd_no_comorbidity` | `1. Tab Amoxicillin 1 g PO TDS x 5 days` | amoxicillin 1000 mg, 3/day, PO, 5 d | R0-R6 PASS; status OK | None | No |
| `images/SYN-DEMO-02_wrong_antibiotic.png` | Drug not listed (R1) | `cap_opd_no_comorbidity` | `1. Tab Ciprofloxacin 500 mg PO BD x 5 days` | ciprofloxacin 500 mg, 2/day, PO, 5 d | R1 FLAG, R2 FLAG, R3/R5 CANNOT_ASSESS | Review selection; guideline option amoxicillin | No |
| `images/SYN-DEMO-03_dose_duration.png` | Dose and duration (R3/R5) | `cap_opd_no_comorbidity` | `1. Tab Amoxicillin 500 mg PO TDS x 10 days` | amoxicillin 500 mg, 3/day, PO, 10 d | R3 FLAG (1500 < 3000 mg/day), R5 FLAG (10 > 7 d) | Review dose; review duration | No |
| `images/SYN-DEMO-04_culture_resistance.png` | Culture resistance (C3) | `cystitis` | `1. Tab Nitrofurantoin 100 mg PO BD x 5 days` | nitrofurantoin 100 mg, 2/day, PO, 5 d | C3 FLAG; R0-R6 PASS | Choose an agent the organism is susceptible to | Yes: printed, and entered in the form |
| `images/SYN-DEMO-05_missing_info.png` | Missing information | `cap_opd_no_comorbidity` | `1. Amoxicillin 1 g` | amoxicillin 1000 mg; freq, route, duration empty | R3, R4, R5, R6 CANNOT_ASSESS | Supply frequency, duration, weight/creatinine, allergy status | No |

The OCR path reads only the medicine lines. Patient details, syndrome, allergy status, creatinine and the culture
are printed so the page looks real, but they still have to be entered in the episode form ("What to type" above).
Case 4's culture is read from the form, not from the image.
