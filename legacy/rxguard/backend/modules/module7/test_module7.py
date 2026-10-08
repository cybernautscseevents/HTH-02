#!/usr/bin/env python3
import json
from backend.modules.module7.dose_adjustment import check_dose_adjustment, _FDA_LABELS


def test_simple_ckd_adjustment():
    drugs = [
        {"generic": "metformin", "original_dose": "500 mg BID"},
        {"generic": "amoxicillin", "original_dose": "500 mg TID"},
    ]
    comorbidities = {"ckd": {"egfr": 25}}
    res = check_dose_adjustment(drugs, comorbidities)
    print(json.dumps(res, indent=2))


def test_liver_adjustment():
    drugs = [{"generic": "acetaminophen", "original_dose": "1 g PRN"}]
    comorbidities = {"liver_disease": True}
    res = check_dose_adjustment(drugs, comorbidities)
    print(json.dumps(res, indent=2))


def test_unknown_drug():
    drugs = [{"generic": "unknown_med", "original_dose": "10 mg"}]
    comorbidities = {"ckd": True}
    res = check_dose_adjustment(drugs, comorbidities)
    print(json.dumps(res, indent=2))


def main():
    print("Loaded DB entries:", len(_FDA_LABELS))
    test_simple_ckd_adjustment()
    print("-"*60)
    test_liver_adjustment()
    print("-"*60)
    test_unknown_drug()


if __name__ == "__main__":
    main()
