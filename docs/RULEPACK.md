# Guideline rule pack (R1, R3, R5)

`backend/stewardship/rulepack.py` loads two files in one format and implements the `RulePack`
port:

- `rulepack/syndromes.yaml`: 13 syndromes read from the guideline PDF by hand.
- `rulepack/syndromes_ncdc.yaml`: 93 syndromes generated from the NCDC 2025 dataset by
  `scripts/import_ncdc.py` (see "Imported NCDC dataset" below). Never edited by hand.

A syndrome code may appear in only one file; loading fails otherwise, so an imported row can never
replace a hand-checked one. Every regimen carries the guideline section, the printed page and a
quote of the row it was read from. There is no model, retrieval or inference in this path: the
same episode and the same files always give the same findings. `version` is a hash of both files,
so each stored evaluation names the exact guideline data it ran against.

## Source

All rows come from one document: *NCDC National Treatment Guidelines for Antimicrobial Use in
Infectious Diseases, v2.0, November 2025* (https://ncdc.mohfw.gov.in/uploads/pdf/amr17.pdf).
The ICMR 2019 guideline is used elsewhere in the project (renal dosing) but contributes no
rule-pack rows.

## Syndromes covered (syndrome codes)

| Code | NCDC section, page | Antibiotic indicated |
|---|---|---|
| `cystitis` | 5.1, p. 39 | yes (culture before antibiotics) |
| `pyelonephritis` | 5.2, p. 39 | yes (culture before antibiotics) |
| `cellulitis_nonpurulent` | 9.3, p. 53 | yes |
| `cellulitis_moderate_severe` | 9.3, p. 53 | yes |
| `cap_opd_no_comorbidity` | 12.5, p. 83 | yes |
| `cap_opd_comorbidity` | 12.5, p. 83 | yes |
| `cap_ward` | 12.5, p. 83 | yes |
| `cap_icu` | 12.5, p. 83 | yes |
| `copd_exacerbation` | 12.3, p. 81 | yes |
| `acute_bronchitis` | 12.1, p. 81 | no |
| `bronchiolitis` | 12.2, p. 81 | no |
| `viral_uri` | 7.2, p. 47 | no |
| `acute_gastroenteritis_no_danger_signs` | 4.2, p. 33 | no |

## What each rule assesses

- **R1 indication**: the drug is first-line or an alternative for the syndrome (PASS), is not listed
  for it (FLAG, suggests the first first-line drug), or the syndrome says no antibiotic is needed
  (FLAG, HIGH). Unknown syndrome: CANNOT_ASSESS. Route is not used by R1.
- **R3 dose**: adult total daily dose (dose x frequency) against the mg/day range worked out from
  the dose and interval the guideline prints. Matched on drug **and route**.
- **R5 duration**: planned days against the days printed for that regimen. Matched on drug and route.

## Why a case returns CANNOT_ASSESS

The pack only contains what the guideline states. Anything else is left out, and the engine reports
the gap instead of treating it as safe:

- syndrome not in the table, or the episode has no syndrome code;
- drug not listed for the syndrome (R3/R5; R1 flags it);
- order has no route, or a route the guideline does not give for that drug (oral and IV are
  different regimens);
- dose or frequency, or duration, missing on the order;
- the guideline gives a weight-based dose (e.g. amikacin 15 mg/kg), or no duration for that drug;
- patient under 18 (all doses are adult doses).

## Reading conventions and limits

- **Route "inferred"**: NCDC prints "IV/IM/Inj" for parenteral drugs and prints nothing for oral
  ones. An unmarked drug is read as oral. Each such entry is marked `route_basis: inferred` and the
  evidence quote says so.
- **Combinations**: regimens like "amoxicillin-clavulanate + azithromycin" are stored one drug per
  entry. R1 cannot tell whether the partner drug is also prescribed. Doses of combination products
  use the combined strength the guideline prints (e.g. piperacillin-tazobactam 4.5 g, cotrimoxazole
  960 mg). An order that records only one component's strength will be flagged or not assessed.
- **Duration** is the range printed against the regimen or its row. In pyelonephritis only
  piperacillin-tazobactam and ertapenem carry "7-10 days"; amikacin has none stated, so R5 is
  CANNOT_ASSESS for it.
- **Fixed-point doses**: where the guideline gives one dose (e.g. nitrofurantoin 100 mg q12h) the
  range is a single value, so R3 flags a total daily dose either above or below it.
- `culture_required` is true only where the guideline says to collect cultures before antibiotics
  (cystitis, pyelonephritis). It is false elsewhere because the table is silent, not because
  cultures are unnecessary.

## Imported NCDC dataset

Source: `data/reference/ncdc/syndromes_ncdc_2025.yaml`, a machine-readable conversion of the
same NCDC 2025 guideline (87 sections, 496 regimens) contributed on branch
`complete-verification-incomplete` (commit 173e92c). Only its data is used; the engine is ours.

- **Grouping is by hand.** The dataset lists all regimens of a section together, tagged with the
  sub-group they apply to. `rulepack/ncdc_import.yaml` names, for each of our syndrome codes,
  exactly which dataset regimens belong to it. The dataset's structured `applies_when.predicate`
  is not used: it is wrong in places (rows labelled "uncomplicated" carry
  `severity: complicated`; "uncomplicated superficial folliculitis" carries `setting: ICU`).
- **Numbers convert only when exact.** mg/g/mcg dose x a fixed number of doses per day (or a
  range of doses per day), whole-day duration ranges, and only for regimens the dataset marks
  executable and checkable. Weight-based doses, units ("4 million units"), combination strengths
  ("800/160 mg"), route-dependent doses, loading schedules, single doses and phased durations are
  not converted: the drug stays (R1 sees it), R3/R5 return CANNOT_ASSESS.
- **Same drug and route twice** in one code: a dose or duration that differs between the copies
  is dropped rather than choosing one.
- **Culture before antibiotics** is set only where the section's own diagnostics text says so;
  the dataset's per-regimen culture flag is one general instruction applied to every row.
- **Overlap**: the 13 hand-checked sections are converted the same way and compared, not
  imported. All doses and durations agree; the remaining differences are listed in
  `docs/NCDC_IMPORT_REPORT.md` and pinned by a test. The hand-checked row is kept in every case.
- **Accounting**: every dataset regimen is either imported, compared, or listed in
  `docs/NCDC_IMPORT_REPORT.md` with the reason it was not imported. A test checks the generated
  files are up to date (`python scripts/import_ncdc.py --check`).

To change the import, edit `rulepack/ncdc_import.yaml` and run `python scripts/import_ncdc.py`.

## Not covered (all CANNOT_ASSESS)

Every syndrome not in either file. The sections deliberately left out of the import, with
reasons, are in `rulepack/ncdc_import.yaml` (`excluded`) and the import report: infective
endocarditis, CNS infections other than empiric meningitis, sepsis without a source, STI
syndromes (referred to the national STI guideline), surgical prophylaxis, eye infections,
toxic shock syndrome (the dataset reproduces a source dose error), transplant/BMT tables,
antifungal and antiviral treatment, and all neonatal and paediatric dosing.
Cefoperazone-sulbactam and benzathine penicillin are listed in the guideline but are not drugs in
the catalog, so they are omitted (R1 flags them as not listed).

## Adding a syndrome

Prefer the dataset: add an entry to `rulepack/ncdc_import.yaml` and re-run the import. For a
section the dataset gets wrong, add a hand-checked entry to `syndromes.yaml` copying the guideline row verbatim into `quote`, with section and
page. The loader rejects a duplicate drug+route, a missing `route_basis`, an invalid range, or
regimens on a "no antibiotic" syndrome. Run `pytest backend/tests/test_rulepack.py`.
