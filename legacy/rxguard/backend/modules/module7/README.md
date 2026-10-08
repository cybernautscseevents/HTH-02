# Module 7 — Dose Adjustment Checker

Rule-based dose adjustment checks using offline FDA label JSON data.

Overview
- Loads a local FDA label JSON DB (default: `data/fda_label_database.json`)
- Provides `check_dose_adjustment(drug_list, comorbidities)` to assess need for dose adjustments
- No LLMs — pure rule-based logic using label tables

Input
- `drug_list`: list of dicts produced by module 2 drug normalization. Example:

```py
[{"generic": "metformin", "original_dose": "500 mg BID"}]
```

- `comorbidities`: dict with keys like `ckd` (bool or {"egfr": value, "crcl": value}), `liver_disease` (bool), `age`

Output
- JSON: `{ "assessments": [...], "summary": {...} }`

Per-drug fields:
- `drug`, `adjustment_needed` (bool), `reason`, `recommended_dose`, `original_dose`, `severity`

Usage
```py
from backend.modules.module7.dose_adjustment import check_dose_adjustment

drugs = [{"generic": "metformin", "original_dose": "500 mg BID"}]
comorbidities = {"ckd": {"egfr": 25}}
res = check_dose_adjustment(drugs, comorbidities)
print(res)
```

CLI
```bash
python backend/modules/module7/dose_adjustment.py --drugs-json '[{"generic":"metformin"}]' --comorbidities-json '{"ckd": {"egfr": 25}}'
```

Customize DB
- Set `FDA_LABEL_DATABASE` env var to point to a different JSON file.

Notes
- Database schema: top-level `drugs` dict keyed by lower-case generic names. Each drug may include a `dose_adjustments` list with rules.
- The module uses simple substring matching for names and basic numeric threshold parsing (e.g., `egfr<30`).
