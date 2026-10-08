# Typed prescription test set (PhysioNet demo databases)

Real, de-identified, typed antibiotic orders run through the existing pipeline
(`intake` → `Catalog.normalize` → `DrugOrder` → `Episode` → `evaluate_episode`) by
`scripts/typed_rx_eval.py`. Nothing in the engine, parser or catalog was changed for this test.

| | MIMIC-IV Clinical Database Demo 2.2 | eICU Collaborative Research Database Demo 2.0.1 |
|---|---|---|
| URL | https://physionet.org/content/mimic-iv-demo/2.2/ | https://physionet.org/content/eicu-crd-demo/2.0.1/ |
| Licence | Open Data Commons ODbL v1.0, open access, no credentialing | same |
| Patients | 100 (Beth Israel Deaconess, Boston) | ~2,500 ICU stays, 20 US hospitals |
| De-identified | yes (HIPAA safe harbour, dates shifted) | yes |
| Used here | prescriptions + pharmacy (orders), diagnoses_icd, microbiologyevents (AST), labevents (creatinine), patients | medication (orders) |

The raw tables (`mimic/`, `eicu/`, about 7 MB) and `results/` are git-ignored: the per-case report holds
row-level patient data. Download only these tables:

```
cd data/typed_rx_test
mkdir -p mimic eicu
for f in prescriptions pharmacy diagnoses_icd d_icd_diagnoses microbiologyevents labevents patients; do
  curl -fL -o mimic/$f.csv.gz https://physionet.org/files/mimic-iv-demo/2.2/hosp/$f.csv.gz; done
curl -fL -o eicu/medication.csv.gz https://physionet.org/files/eicu-crd-demo/2.0.1/medication.csv.gz
cd ../.. && python scripts/typed_rx_eval.py --mimic data/typed_rx_test/mimic \
  --eicu data/typed_rx_test/eicu --out data/typed_rx_test/results/report.md
```

## How a typed line is built

One antibiotic order row becomes one line: the row's own text fields joined by spaces, not rewritten.

- MIMIC: `drug dose_val_rx dose_unit_rx route frequency` → `CefePIME 2 g IV Q12H`, `Ciprofloxacin HCl 500 mg PO/NG Q12H`
- eICU: `drugname dosage routeadmin frequency` → `ZOSYN 3.375 GRAM INJ 3.375 Gm IVPB Q8H`

A case is one MIMIC admission with an infection ICD title (UTI, pneumonia, cellulitis, COPD exacerbation,
bronchitis, gastroenteritis). Its prescription is the antibiotic orders started in the first 24 h; patient age
and sex from `patients`; latest creatinine before the first order; cultures (screens excluded) collected
within ±48 h; evaluation time is 48 h after the first order. Allergy status is UNKNOWN (no allergy table).
Run A gives only the ICD titles as `diagnosis_text`. Run B adds a syndrome code picked from the first ICD
title, standing in for the clinician's choice. It is **not** from the dataset, and treating an inpatient
"UTI, site not specified" as cystitis is a simplification.

## Result (2026-10-08, commit e6399fd)

Parser and catalog, every distinct antibiotic line. MIMIC is scored against its own structured fields:

| | MIMIC (181 lines) | eICU (653 lines) |
|---|---|---|
| orders built | 161 (89%) | 558 (85%) |
| drug identified | 125/161 (78%) | 103/558 (18%) |
| dose read / wrong | 161 / **0 wrong** of 154 | 456 |
| doses per day read / wrong | 107 / **0 wrong**, 40 missed of 146 | 145 |
| route read / wrong | 160 / **0 wrong** of 159 | 400 |
| duration read | 0 (not written in inpatient orders) | 0 |

End to end, 12 admissions, 22 runs, 0 errors. Rules fired: R0 PASS 29 / CANNOT_ASSESS 10, R1 FLAG 13,
R2 FLAG 13, R3 FLAG 2, C3 FLAG 11 (e.g. vancomycin vs *E. coli*), C4 FLAG 2, C5 FLAG 24, C8 and C9
CANNOT_ASSESS. No unidentified order received any check other than R0.

Gaps found, and what was done (see "After the MVP fixes"):

1. **Fixed.** `transcript._PREFIX` read `amp` (ampoule) inside a name with no form word in front: "Ampicillin" →
   "icillin", "Amphotericin" → "hotericin". A form word must now end at a non-letter.
2. **Fixed.** A dose of `0 mg` (pharmacy-dosed vancomycin) or `1,000 mg` gave `dose_mg=0`, `DrugOrder` validation
   failed, and `/api/evaluate` returned HTTP 500. eICU "vancomycin 1,250 mg" was also silently read as 250 mg. A
   zero or comma-written dose is now left unread (R3 CANNOT_ASSESS); any remaining validation error is a 422.
3. Open. Salt and formulation words are not matched: "Ciprofloxacin HCl", "Doxycycline Hyclate", "Tobramycin
   Sulfate", "Ampicillin Sodium", "Vancomycin Oral Liquid", "Levofloxacin in D5W", "IVPB". No source in the project
   supports a salt-name rule, so these still need confirmation (R0).
4. Open. Parenthesised brands and US brands: "MetRONIDAZOLE (FLagyl)", Zosyn, Ancef, Rocephin, Levaquin (catalog is
   Indian; brands are added only from cited Indian prescribing information).
5. **Fixed in part.** Bare `DAILY`, `q8hr`, `q 8 hour` are read. `every8hr`, `1xDaily`, `4x Daily` are not.
   `ONCE` and `HD PROTOCOL` correctly give none.
6. Open. Not read as medicine lines: `Sulfameth/Trimethoprim DS 1 TAB`, eye/ear/topical lines, eICU lines that start
   with a container volume (`100 ML - METRONIDAZOLE …`).
7. **Fixed.** Free-text syndrome mapping ignored unmapped co-diagnoses and negation: "Pneumonia with acute
   bronchitis" → `acute_bronchitis`, so R1 said antibiotics are not indicated; "Complicated UTI, not cystitis" →
   `cystitis`. Text now maps only when it is a phrase of the table and nothing else but "acute".
8. **Fixed in part.** `RIFAMPIN` is now an alias of rifampicin (AMRIE and WHO share ATC J04AB02).
   `TRIMETHOPRIM/SULFA` and `PIPERACILLIN/TAZO` are lab abbreviations with no source and stay out of panels.

## After the MVP fixes

| | MIMIC before | MIMIC after | eICU before | eICU after |
|---|---|---|---|---|
| orders built | 161/181 | 162/181 | 558/653 | 625/653 |
| drug identified | 125 | 129 | 103 | 111 |
| dose read / wrong | 161 / 0 | 161 / 0 | 456 (7 wrong: "1,250" → 250) | 449 |
| doses per day read / wrong / missed | 107 / 0 / 40 | 112 / 0 / 35 | 145 | 262 |
| route read / wrong | 160 / 0 | 161 / 0 | 400 | 459 |
| lines rejected by a validation error | 1 | 0 | 64 | 0 |

End to end: 22 runs, 0 errors before and after. Run A (ICD titles only) mapped 1 of 12 diagnoses before
("Pneumonia, organism unspecified" → `acute_bronchitis`, wrong) and 0 after; all 12 are reported unresolved
with the reason.
