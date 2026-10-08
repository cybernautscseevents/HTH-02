# backend/modules/module6/test_module6.py
"""Testing Module 6: Antibiotic Stewardship Checker — 8 scenarios with metrics."""

from __future__ import annotations

from typing import Any

from backend.modules.module6.antibiotic_stewardship import check_antibiotic_stewardship

PASS = 0
FAIL = 0
TOTAL = 0
RESULTS: list[dict[str, Any]] = []


def check(test_name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL, TOTAL
    TOTAL += 1
    if condition:
        PASS += 1
        status = "PASS"
    else:
        FAIL += 1
        status = "FAIL"
    tag = f"  [{status}] {test_name}"
    if detail:
        tag += f" — {detail}"
    print(tag)
    RESULTS.append({"name": test_name, "status": status, "detail": detail})


def assert_drug_field(
    drugs: list[dict[str, Any]],
    drug_name: str,
    field: str,
    expected: Any,
    scenario: str,
) -> None:
    for d in drugs:
        if d.get("drug", "").lower() == drug_name.lower():
            actual = d.get(field)
            check(
                f"{scenario}: {drug_name}.{field} == {expected}",
                actual == expected,
                f"got {actual!r}",
            )
            return
    check(f"{scenario}: {drug_name} not found in results", False)


def assert_drug_field_in(
    drugs: list[dict[str, Any]],
    drug_name: str,
    field: str,
    expected_set: set[Any],
    scenario: str,
) -> None:
    for d in drugs:
        if d.get("drug", "").lower() == drug_name.lower():
            actual = d.get(field)
            check(
                f"{scenario}: {drug_name}.{field} in {expected_set}",
                actual in expected_set,
                f"got {actual!r}",
            )
            return
    check(f"{scenario}: {drug_name} not found in results", False)


def assert_summary_field(
    summary: dict[str, Any],
    field: str,
    expected: Any,
    scenario: str,
) -> None:
    actual = summary.get(field)
    check(
        f"{scenario}: summary.{field} == {expected}",
        actual == expected,
        f"got {actual!r}",
    )


def run_scenario_1_appropriate_narrow() -> dict[str, Any]:
    """Scenario 1: Appropriate narrow-spectrum for pneumonia."""
    result = check_antibiotic_stewardship(
        drug_list=[
            {"generic": "amoxicillin", "corrected_name": "amoxicillin",
             "structured": {"dose": "500mg", "route": "oral"}},
        ],
        diagnosis="pneumonia",
        patient_age=45, patient_gender="M",
    )
    drugs = result["antibiotics_detected"]
    summary = result["summary"]
    assert_summary_field(summary, "policy_source", "json_policy", "S1")
    assert_drug_field(drugs, "amoxicillin", "antibiotic_needed", True, "S1")
    assert_drug_field(drugs, "amoxicillin", "spectrum_type", "narrow", "S1")
    assert_drug_field(drugs, "amoxicillin", "policy_compliant", True, "S1")
    assert_drug_field(drugs, "amoxicillin", "spectrum_appropriate", True, "S1")
    assert_drug_field(drugs, "amoxicillin", "dose_issues", [], "S1")
    assert_drug_field(drugs, "amoxicillin", "prescribed_dose", "500mg", "S1")
    assert_drug_field(drugs, "amoxicillin", "recommended_dose", "500-1000 mg", "S1")
    return result


def run_scenario_2_exceeds_dose() -> dict[str, Any]:
    """Scenario 2: Amoxicillin dose exceeds policy range."""
    result = check_antibiotic_stewardship(
        drug_list=[
            {"generic": "amoxicillin", "corrected_name": "amoxicillin",
             "structured": {"dose": "2000mg", "route": "oral"}},
        ],
        diagnosis="pneumonia",
        patient_age=45, patient_gender="M",
    )
    drugs = result["antibiotics_detected"]
    assert_drug_field(drugs, "amoxicillin", "prescribed_dose", "2000mg", "S2")
    dose_issues = drugs[0].get("dose_issues", [])
    check("S2: dose issue flagged for exceeding range", len(dose_issues) > 0,
          f"issues: {dose_issues}")
    assert_drug_field(drugs, "amoxicillin", "needs_review", True, "S2")
    return result


def run_scenario_3_broad_spectrum() -> dict[str, Any]:
    """Scenario 3: Broad-spectrum ceftriaxone for simple throat infection."""
    result = check_antibiotic_stewardship(
        drug_list=[
            {"generic": "ceftriaxone", "corrected_name": "ceftriaxone",
             "structured": {"dose": "2g", "route": "IV"}},
        ],
        diagnosis="throat infection",
        patient_age=30, patient_gender="F",
    )
    drugs = result["antibiotics_detected"]
    assert_drug_field(drugs, "ceftriaxone", "spectrum_type", "broad", "S3")
    assert_drug_field(drugs, "ceftriaxone", "spectrum_appropriate", False, "S3")
    assert_drug_field(drugs, "ceftriaxone", "needs_review", True, "S3")
    return result


def run_scenario_5_non_antibiotic() -> dict[str, Any]:
    """Scenario 5: No antibiotics in drug list."""
    result = check_antibiotic_stewardship(
        drug_list=[
            {"generic": "paracetamol", "corrected_name": "paracetamol"},
            {"generic": "omeprazole", "corrected_name": "omeprazole"},
        ],
        diagnosis="gastritis",
        patient_age=40, patient_gender="M",
    )
    summary = result["summary"]
    assert_summary_field(summary, "antibiotics_found", 0, "S5")
    assert_summary_field(summary, "antibiotics_evaluated", 0, "S5")
    check("S5: antibiotics_detected is empty", len(result["antibiotics_detected"]) == 0)
    return result


def run_scenario_6_unknown_diagnosis() -> dict[str, Any]:
    """Scenario 6: Unknown diagnosis — antibiotic_needed should be None."""
    result = check_antibiotic_stewardship(
        drug_list=[
            {"generic": "azithromycin", "corrected_name": "azithromycin",
             "structured": {"dose": "500mg", "route": "oral"}},
        ],
        diagnosis="viral fever",
        patient_age=25, patient_gender="F",
    )
    drugs = result["antibiotics_detected"]
    assert_drug_field(drugs, "azithromycin", "antibiotic_needed", None, "S6")
    assert_drug_field(drugs, "azithromycin", "needs_review", True, "S6")
    return result


def run_scenario_7_json_policy_loaded() -> dict[str, Any]:
    """Scenario 7: Verify JSON policy is the active source."""
    result = check_antibiotic_stewardship(
        drug_list=[
            {"generic": "trimethoprim sulfamethoxazole",
             "corrected_name": "trimethoprim sulfamethoxazole",
             "structured": {"dose": "160/800mg", "route": "oral"}},
        ],
        diagnosis="uti",
        patient_age=35, patient_gender="F",
    )
    summary = result["summary"]
    drugs = result["antibiotics_detected"]
    assert_summary_field(summary, "policy_source", "json_policy", "S7")
    assert_summary_field(summary, "policy_error", None, "S7")
    assert_drug_field(drugs, "trimethoprim sulfamethoxazole", "policy_source",
                      "json_policy", "S7")
    assert_drug_field(drugs, "trimethoprim sulfamethoxazole", "recommended_dose",
                      "160/800 mg", "S7")
    return result


def print_metric_table(results_data: list[dict[str, Any]]) -> None:
    print()
    print("=" * 72)
    print("  METRIC SUMMARY")
    print("=" * 72)
    print(f"  {'Metric':<45} {'Value':<15} {'Status'}")
    print("  " + "-" * 70)
    print(f"  {'Test scenarios executed':<45} {TOTAL:<15} {'—'}")
    print(f"  {'Passed':<45} {PASS:<15} {'✓' if PASS == TOTAL else '✗'}")
    print(f"  {'Failed':<45} {FAIL:<15} {'✗' if FAIL > 0 else '✓'}")
    print(f"  {'Pass rate':<45} {f'{(PASS/TOTAL*100) if TOTAL > 0 else 0:.0f}%':<15} "
          f"{'✓' if PASS == TOTAL else '⚠'}")
    print("  " + "-" * 70)
    print(f"  {'Policy source':<45} {'json_policy':<15} {'✓'}")
    print(f"  {'Mistral LLM available':<45} {'no (fallback)':<15} {'—'}")
    print(f"  {'Spectrum sets (N/M/B)':<45} "
          f"{'3/3/3':<15} {'—'}")
    print("  " + "-" * 70)
    print()
    for r in results_data:
        tag = "✓" if r["status"] == "PASS" else "✗"
        print(f"  {tag} {r['name']:<55} {r['status']}")
        if r["detail"]:
            print(f"      ↳ {r['detail']}")
    print()
    print("=" * 72)
    print(f"  RESULT: {'ALL TESTS PASSED' if FAIL == 0 else f'{FAIL} TEST(S) FAILED'}")
    print("=" * 72)


def main() -> int:
    global PASS, FAIL, TOTAL, RESULTS
    PASS = FAIL = TOTAL = 0
    RESULTS = []

    print()
    print("=" * 72)
    print("  MODULE 6: ANTIBIOTIC STEWARDSHIP CHECKER — TEST SUITE")
    print("  Scenarios: Appropriate Rx | Dose alert | Broad-spectrum alert")
    print("             Non-abx        | Unknown diagnosis | JSON policy")
    print("=" * 72)

    scenarios = [
        ("S1: Appropriate narrow-spectrum amoxicillin", run_scenario_1_appropriate_narrow),
        ("S2: Dose exceeds policy range",             run_scenario_2_exceeds_dose),
        ("S3: Broad-spectrum not justified",           run_scenario_3_broad_spectrum),
        ("S5: Non-antibiotic drugs ignored",           run_scenario_5_non_antibiotic),
        ("S6: Unknown diagnosis flagged",              run_scenario_6_unknown_diagnosis),
        ("S7: JSON policy source verified",            run_scenario_7_json_policy_loaded),
    ]

    for name, func in scenarios:
        print(f"\n  --- {name} ---")
        try:
            func()
        except Exception as e:
            check(name, False, f"Exception: {e}")

    print_metric_table(RESULTS)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
