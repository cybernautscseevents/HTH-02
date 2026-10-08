# Reference data

## `amrie/` — WHONET AMR Interpretation Engine tables

- Source: https://github.com/AClark-WHONET/AMRIE, `Interpretation Engine/Resources/`,
  commit `c19f3901ea44e9713cb7058e4e9df3cc07af871f` (2026-09-30).
- Files: `Antibiotics.txt` (antibiotic codes, ATC, class, WHO AWaRe tier),
  `ExpectedResistancePhenotypes.txt` (intrinsic resistance, CLSI and EUCAST),
  `Organisms.txt` (WHONET organism codes and names).
- License: MGB Open Access License 1.0 (`amrie/LICENSE.md`). **Non-commercial, academic use
  only.** Fine for the hackathon with attribution; a commercial product needs another source.

## `../aware.csv` — derived from `amrie/Antibiotics.txt`

Human antibiotics with ATC code `J01*`, one row per generic (123 rows).
Columns: `generic, atc_code, drug_class, subclass, aware_tier, whonet_codes`.

Caveats:
- The AWaRe edition used by AMRIE is not stated. Verify the drugs used in the rule pack against
  the WHO AWaRe 2025 classification before the demo.
- One tier per molecule. Route-specific tiers (for example, oral vs IV fosfomycin) are not
  represented; handle them in the rule pack if needed.
- Combination names use AMRIE spelling (`amoxicillin/clavulanic acid`); drug normalization must
  map to these names.

## `../intrinsic_resistance.csv` — derived from `amrie/ExpectedResistancePhenotypes.txt`

Built by `scripts/build_intrinsic_resistance.py`: every **CLSI** expected-resistance rule
expanded to one row per organism name and generic in `aware.csv` (7,466 rows). CLSI is used
because ICMR AMRSN reports against CLSI breakpoints. Organism names are AMRIE scientific names
in lower case; a lab report written as "E. coli" will not match.

## `../renal_dosing.csv` — US FDA label renal dosing tables

One row per creatinine clearance band (mL/min, inclusive integers) for 13 antibiotics, each
quoting the label text word for word, with DailyMed set id, effective date and section.
Labels were fetched through the openFDA drug label API on 2026-10-08.
`action`: `none` (no change), `adjust` (modified regimen; `max_daily_mg` set only where the
label gives an absolute single-agent dose), `avoid` (contraindicated or not recommended).
Drugs not listed (for example vancomycin, aminoglycosides, linezolid) get CANNOT_ASSESS.
These are US labels; verify against Indian prescribing information before clinical use.
