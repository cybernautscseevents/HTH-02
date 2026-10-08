# Reference data

Source precedence for every Person 2 table: Indian national guideline → Indian prescribing
information → WHO → other regulators, used only where no Indian source exists and labelled as
fallback in every row they supply. Values are never inferred: a drug, route, organism or
kidney-function range a table does not cover returns CANNOT_ASSESS.

## `who/B09489-eng.xlsx` — WHO AWaRe classification 2025

- Source: WHO, "The selection and use of essential medicines, 2025: WHO AWaRe (Access, Watch,
  Reserve) classification of antibiotics for evaluation and monitoring of use",
  https://iris.who.int/items/4fa2de82-388c-46d9-a6cb-41ffbd10677d (downloaded 2026-10-08,
  sha256 `2a885c92306f9865b16b6242ab51ac01bf8ee8b1f2470aa95f05c3fe4ea2907c`).
- License: CC BY-NC-SA 3.0 IGO.

## `amrie/` — WHONET AMR Interpretation Engine tables

- Source: https://github.com/AClark-WHONET/AMRIE, `Interpretation Engine/Resources/`,
  commit `c19f3901ea44e9713cb7058e4e9df3cc07af871f` (2026-09-30).
- Files: `Antibiotics.txt` (antibiotic codes, ATC, class), `ExpectedResistancePhenotypes.txt`
  (intrinsic resistance, CLSI and EUCAST), `Organisms.txt` (WHONET organism codes and names).
- License: MGB Open Access License 1.0 (`amrie/LICENSE.md`). **Non-commercial, academic use
  only.** Fine for the hackathon with attribution; a commercial product needs another source.
- AMRIE's own AWaRe column is **not** used: its edition is unstated and it disagreed with WHO
  2025 (for example cefpodoxime "Not classified" in AMRIE, Watch in WHO 2025).

## `../aware.csv` and `../drug_aliases.csv` — built by `scripts/build_aware.py`

- `aware.csv`: all 268 entries of the WHO AWaRe 2025 sheet "AWaRe classification 2025", plus 6
  human ATC J01 agents from AMRIE that WHO does not classify (tier "Not classified", `source`
  column says so). Generic names follow WHO spelling (`cefalexin`, `sulfamethoxazole/trimethoprim`,
  `cefpodoxime proxetil`). WHO's route-specific entries keep a `route` column (IV/PO); fosfomycin
  and minocycline are the two whose tier differs by route.
- `drug_aliases.csv`: other spellings mapped to the WHO name, each with its basis: AMRIE/USAN
  names matched on identical ATC code and a similar name (4 reviewed by hand), and spellings used
  in Indian documents (Indian Pharmacopoeia "amoxycillin", NCDC 2025 "Cotrimoxazole", ICMR 2019
  "Co-trimoxazole").

## `../brands_india.csv` — Indian brand names

Rows come only from Indian prescribing information published by the manufacturer, with URL,
revision date, PI version and the generic-name line quoted from the PI. Currently GSK India
(https://india-pharma.gsk.com): Augmentin (625 Duo, 1g Duo, 375, DDS, Duo suspension, I.V.),
Ceftum, Supacef, Fortum. No openly published, authoritative Indian brand-to-generic dataset
was found (CDSCO and NPPA lists are by generic; commercial compendia such as CIMS/MIMS are not
open), so other brands are not listed and come back NO_MATCH or AMBIGUOUS for confirmation.
A hospital formulary export is the expected way to extend this file.

`legacy/rxguard/data/indian_drug_lexicon.csv` (moved out of `data/` with the RxGuard pipeline) is
**not** Indian data and is not used by the stewardship engine.
It has no recorded provenance; its brands (Napa, Nexcital, Apeelo, ...) match the Bangladeshi
RxHandBD dataset. It is kept only because the legacy OCR normalization module and benchmarks read it.

## `../intrinsic_resistance.csv` — built by `scripts/build_intrinsic_resistance.py`

Every **CLSI** expected-resistance rule in `amrie/ExpectedResistancePhenotypes.txt` expanded to
one row per organism name and generic in `aware.csv` (7,225 rows). CLSI is used because ICMR
AMRSN reports against CLSI breakpoints. Organism names are AMRIE scientific names in lower
case. An organism not in `amrie/Organisms.txt` (for example a lab report written "E. coli")
produces a C9_ORGANISM_UNKNOWN CANNOT_ASSESS finding instead of being read as non-resistant.

## `../renal_dosing.csv` — kidney dosing bands

One row per drug, route and creatinine clearance band (mL/min, inclusive integers), each
quoting its source word for word. Rows for the same band from several sources are merged into
one band citing all of them; they must agree on the action.

| Source | Jurisdiction | Drugs |
|---|---|---|
| ICMR Treatment Guidelines for Antimicrobial Use in Common Syndromes, 2nd ed. (2019), Table 14.1 (pp. 164-177) | India | IV/IM: ampicillin, amoxicillin/clavulanic acid, piperacillin/tazobactam, cefazolin, cefuroxime, cefotaxime, ceftriaxone, ceftazidime, cefepime, imipenem/cilastatin, meropenem, clindamycin, azithromycin, ciprofloxacin, levofloxacin, metronidazole, amikacin, gentamicin |
| GSK India PI: AUGMENTIN 625 / 1g DUO (AUG-TAB/PI/IN/2025/01), CEFTUM (CEF-CL/PI/IN/2026/01) | India | Oral amoxicillin/clavulanic acid, oral cefuroxime |
| US FDA labels via openFDA/DailyMed (fetched 2026-10-08) | US, fallback | Oral amoxicillin, cefalexin, ciprofloxacin, levofloxacin, sulfamethoxazole/trimethoprim, doxycycline, nitrofurantoin |
| UK MHRA Drug Safety Update, September 2014 | UK | Nitrofurantoin (with the FDA label; see below) |

Reading conventions: ICMR's "NC" is not defined in the table and is read as no change. Above
the highest clearance listed for a drug, no modification is assumed (the table lists only
modifications). Where an ICMR range boundary is ambiguous ("< 50 -30", "< 10-20") the stricter
band takes the boundary value. `max_daily_mg` is set only where the source gives an absolute
dose; relative instructions ("half the usual dose") flag with the source text instead.

**Nitrofurantoin.** No Indian source gives a kidney threshold: NCDC NTG 2025 recommends it
first line for cystitis without one, and ICMR 2019 Table 9.2 says only "Dosage adjustment as per
eGFR". The US label contraindicates it below CrCl 60 mL/min; the MHRA (2014) contraindicates it
below eGFR 45 and allows a 3-7 day course with caution at 30-44. The table therefore uses
`none` at CrCl ≥ 60, `review` (sources disagree; pharmacist decides) at 45-59, and `avoid` below
45, citing both sources. Change the bands in the CSV to adopt a hospital policy. Note the MHRA
threshold is eGFR while the engine estimates CrCl (Cockcroft-Gault).

Not covered (CANNOT_ASSESS): vancomycin, teicoplanin, colistin, polymyxin B and other
level-guided or mg/kg-only regimens, linezolid, fosfomycin, cefixime, cefpodoxime, and any oral
drug not listed above.

## `ncdc/` — NCDC 2025 guideline dataset and ICMR AMRSN 2023 surveillance

Both files were contributed on branch `complete-verification-incomplete` (commit `173e92c`,
`data-1/`) and are copied here byte for byte. Only the data is used; that branch's rule engine is
not.

- `syndromes_ncdc_2025.yaml` (was `syndromes_updated.yaml`, sha256
  `7a279538a4247182605311e1019415ad44bdc0a1ac30520205ae66b38a0786c6`): NCDC/ICMR National
  Treatment Guidelines for Antimicrobial Use in Infectious Disease Syndromes v2.0 (November 2025),
  87 sections and 496 regimens with page and section of each, raw source text and parsed
  dose/frequency/route/duration. Consumed only by `scripts/import_ncdc.py`; see
  `docs/RULEPACK.md` and `docs/NCDC_IMPORT_REPORT.md`.
- `antibiogram_icmr_amrsn_2023.csv` (was `antibiogram.csv`, sha256
  `233f8ce377031051a723c2af875e7367b5212ba706d92dbc37f2dd66220d1bff`): 1,414 susceptibility rows
  from the ICMR AMR Research & Surveillance Network annual report 2023, with susceptible and
  tested counts, table and page. Network data from tertiary-care hospitals: not this hospital's
  antibiogram and not community-representative. Loaded by `backend/stewardship/surveillance.py`
  as advisory context only; it is not an input to any rule. Rows whose drug name does not match
  the catalog exactly (antifungals, truncated names, "Gentamicin HL"), rows without counts, and
  3 rows whose printed percentage disagrees with their own counts are not loaded.
