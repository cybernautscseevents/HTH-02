# SYNTHETIC / DEMO DATA

18 invented prescriptions for demonstrating the app. Fictional hospital, doctor and patients; no real
patient data. The engine and the tests do not read this folder. The one exception is `patients.json`, which
stands in for the hospital record system behind **Fetch record** (`GET /api/patients/{id}`).

Every case is a whole prescription as a doctor writes it: the diagnosis, the antibiotics and the other
medicines (paracetamol, pantoprazole, inhalers, diabetes and blood-pressure tablets), investigations and
culture results. Drugs are written by generic name, except Augmentin in case 11: the catalog only accepts
brands with a cited source (`data/brands_india.csv`).

## Files

| File | What it is |
|---|---|
| `build_cases.py` | The source of every case. Writes the three JSON files and prints what the engine returns |
| `cases.json` | Per case: `prescription_text` to paste, the `POST /api/episodes` body, and the expected findings |
| `prescriptions.json` | The exact text printed on each image |
| `patients.json` | Patient details and cultures, served by **Fetch record** |
| `make_images.py` | Checks every page parses to the intended orders and gives the expected findings, then draws `images/` |
| `images/` | One printed prescription per case (1240 x 1754 PNG) |

```
python data/demo_synthetic/build_cases.py    # after editing a case
python data/demo_synthetic/make_images.py    # check, then draw images/ (--ocr glm|qwen to also OCR them)
```

The expected findings are what the engine returned when `build_cases.py` last ran, so they are a record of
current behaviour, not an independent answer key. Read them before committing a change.

## Demo flow

1. **Prescription**: upload the case's image, or choose *Typed prescription* and paste its
   `prescription_text` from `cases.json` (the `Diagnosis:` line, then `Rx` and the medicines). The review
   screen shows the prescriber's diagnosis and the guideline syndrome it reads as.
2. **Clinical context**: type the case ID (e.g. `SYN-DEMO-06`) and press **Fetch record**. Age, sex,
   weight, creatinine, allergies and cultures fill in. The syndrome is already selected from the
   diagnosis; set the care setting from the table below.
3. **Run Evaluation**.

## Cases

"Medicines" counts every line, antibiotic or not. Findings list only the checks that did not pass.

| ID | Demonstrates | Setting | Diagnosis as written | Medicines | Status | Findings |
|---|---|---|---|---|---|---|
| `SYN-DEMO-01` | Guideline-concordant: first-line drug, dose and duration | OPD | Community-acquired pneumonia, OPD, without comorbidities | 2 | OK | all PASS |
| `SYN-DEMO-02` | Drug not listed for the syndrome (R1) and a Watch drug where Access exists (R2) | OPD | Community-acquired pneumonia, OPD, without comorbidities | 3 | FLAGGED | R1 FLAG (ciprofloxacin); R2 FLAG (ciprofloxacin); R3 CANNOT_ASSESS (ciprofloxacin); R5 CANNOT_ASSESS (ciprofloxacin) |
| `SYN-DEMO-03` | Dose below the guideline (R3) and course too long (R5) | OPD | Community-acquired pneumonia, OPD, without comorbidities | 2 | FLAGGED | R3 FLAG (amoxicillin); R5 FLAG (amoxicillin) |
| `SYN-DEMO-04` | Culture shows the organism is resistant (C3) | OPD | Uncomplicated cystitis | 2 | FLAGGED | C3 FLAG (nitrofurantoin) |
| `SYN-DEMO-05` | Missing frequency, duration, weight, creatinine and allergy status | OPD | Community-acquired pneumonia, OPD, without comorbidities | 1 | FLAGGED | R3 CANNOT_ASSESS (amoxicillin); R4 CANNOT_ASSESS (amoxicillin); R6 CANNOT_ASSESS (amoxicillin); R5 CANNOT_ASSESS (amoxicillin) |
| `SYN-DEMO-06` | Dose too high for the kidney function (R4) | WARD | Acute pyelonephritis | 4 | FLAGGED | R4 FLAG (piperacillin/tazobactam) |
| `SYN-DEMO-07` | Penicillin given to a patient with a penicillin allergy (R6) | OPD | Cellulitis, non-purulent | 2 | FLAGGED | R6 FLAG (amoxicillin) |
| `SYN-DEMO-08` | Antibiotic for a viral infection (R1) | OPD | Viral URTI | 3 | FLAGGED | R1 FLAG (azithromycin); R3 CANNOT_ASSESS (azithromycin); R4 CANNOT_ASSESS (azithromycin); R5 CANNOT_ASSESS (azithromycin) |
| `SYN-DEMO-09` | Inpatient pneumonia on the guideline regimen; both drugs are Watch tier, so R2 asks for a stewardship look | WARD | Community-acquired pneumonia, inpatient ward | 4 | FLAGGED | R2 FLAG (ceftriaxone); R2 FLAG (azithromycin); R4 CANNOT_ASSESS (azithromycin) |
| `SYN-DEMO-10` | Carbapenem and vancomycin where the guideline gives ceftriaxone + azithromycin | ICU | Community-acquired pneumonia, inpatient ICU | 4 | FLAGGED | R1 FLAG (meropenem); R1 FLAG (vancomycin); R2 FLAG (meropenem); R2 FLAG (vancomycin); R3 CANNOT_ASSESS (meropenem); R3 CANNOT_ASSESS (vancomycin); R4 CANNOT_ASSESS (vancomycin); R5 CANNOT_ASSESS (meropenem); R5 CANNOT_ASSESS (vancomycin) |
| `SYN-DEMO-11` | Brand name read (Augmentin); daily dose below guideline (R3) | OPD | Infective exacerbation of COPD | 4 | FLAGGED | R3 FLAG (amoxicillin/clavulanic acid) |
| `SYN-DEMO-12` | Culture back: step down from piperacillin-tazobactam to a narrower drug (C4) | WARD | Acute pyelonephritis | 2 | FLAGGED | C4 FLAG (piperacillin/tazobactam) |
| `SYN-DEMO-13` | Two antibiotics for gastroenteritis that needs none (R1) | OPD | Acute gastroenteritis without danger signs | 4 | FLAGGED | R1 FLAG (ciprofloxacin); R1 FLAG (metronidazole); R3 CANNOT_ASSESS (ciprofloxacin); R3 CANNOT_ASSESS (metronidazole); R4 CANNOT_ASSESS (metronidazole); R5 CANNOT_ASSESS (ciprofloxacin); R5 CANNOT_ASSESS (metronidazole) |
| `SYN-DEMO-14` | Diabetic foot infection treated as the guideline says | OPD | Diabetic foot infection, moderate | 4 | OK | all PASS |
| `SYN-DEMO-15` | No diagnosis written: the indication is undocumented | OPD | *(none written)* | 3 | FLAGGED | R1 CANNOT_ASSESS (azithromycin); R3 CANNOT_ASSESS (azithromycin); R5 CANNOT_ASSESS (azithromycin); R4 CANNOT_ASSESS (azithromycin) |
| `SYN-DEMO-16` | Uncertain diagnosis ('UTI?'): not mapped, the reviewer must choose | OPD | UTI? | 1 | FLAGGED | R1 CANNOT_ASSESS (cefixime); R3 CANNOT_ASSESS (cefixime); R5 CANNOT_ASSESS (cefixime); R4 CANNOT_ASSESS (cefixime) |
| `SYN-DEMO-17` | Nitrofurantoin in an older patient with poor kidney function (R4) | OPD | Uncomplicated cystitis | 3 | FLAGGED | R4 FLAG (nitrofurantoin) |
| `SYN-DEMO-18` | Child: adult dose rules do not apply, so the dose is not judged | OPD | Acute pharyngitis, Centor score 3 or more | 2 | FLAGGED | R3 CANNOT_ASSESS (amoxicillin); R4 CANNOT_ASSESS (amoxicillin) |

Case 15 has no diagnosis, so the indication is reported as undocumented. In case 16 the doctor wrote
"UTI?"; an uncertain diagnosis is never mapped, so the reviewer has to choose the syndrome. In case 18 the
patient is a child: the dose rules are written for adults, so the dose is reported as not assessable
rather than judged.
