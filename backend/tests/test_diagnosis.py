"""The syndrome comes from the prescriber's diagnosis; the reviewer confirms or changes it.

A diagnosis is read from the prescription ("Diagnosis: ..."), mapped only when it names one
rule-pack syndrome exactly, and a missing diagnosis is reported, never guessed.
"""

import pytest

from backend.stewardship.intake import diagnosis_line, medicine_text

from .test_app_flow import (  # noqa: F401 - fixtures
    NITRO,
    catalog,
    client,
    clock,
    evaluate,
    finding,
    pack,
    renal,
    service,
    store,
)

CAP = "Community-acquired pneumonia, OPD, without comorbidities"
AMOX = "Tab Amoxicillin 1 g PO TDS x 5 days"


@pytest.mark.parametrize(
    ("text", "diagnosis"),
    [
        ("Diagnosis: Uncomplicated cystitis\nRx\nTab X", "Uncomplicated cystitis"),
        ("Dx: Acute pyelonephritis", "Acute pyelonephritis"),
        ("Provisional diagnosis: CAP", "CAP"),
        ("Diagnosis:\nAcute bronchitis\n\nRx", "Acute bronchitis"),
        ("Diagnosis:\nRx\nTab X", None),
        ("Age: 40\nRx\nTab Amoxicillin 500 mg", None),
    ],
)
def test_diagnosis_line(text, diagnosis):
    assert diagnosis_line(text) == diagnosis


def test_diagnosis_lines_are_not_read_as_medicines():
    assert medicine_text("Dx: Acute pyelonephritis\n" + NITRO).strip() == NITRO


def test_prescriber_diagnosis_sets_the_syndrome(client):  # noqa: F811
    report = evaluate(client, f"Diagnosis: {CAP}\nRx\n{AMOX}", syndrome=None)
    assert report["syndrome"] == {
        "code": "cap_opd_no_comorbidity",
        "name": CAP,
        "resolution": "mapped_from_text",
    }
    assert finding(report, "R1_INDICATION", "rx-1")["outcome"] == "PASS"


def test_reviewer_confirming_the_diagnosis_is_recorded(client):  # noqa: F811
    report = evaluate(client, AMOX, syndrome="cap_opd_no_comorbidity", diagnosis_text=CAP)
    assert report["syndrome"]["resolution"] == "confirmed_from_diagnosis"


def test_reviewer_overriding_the_diagnosis_is_recorded(client):  # noqa: F811
    report = evaluate(client, NITRO, syndrome="cystitis", diagnosis_text="Acute pyelonephritis")
    assert report["syndrome"]["resolution"] == "selected"
    assert any("reads as 'Acute pyelonephritis'" in w for w in report["warnings"])


def test_missing_indication_is_a_finding(client):  # noqa: F811
    report = evaluate(client, AMOX, syndrome=None)
    assert report["syndrome"]["resolution"] == "unresolved"
    item = finding(report, "R1_INDICATION", "rx-1")
    assert item["outcome"] == "CANNOT_ASSESS"
    assert "No indication documented" in item["message"]
    assert "Ask the prescriber" in item["action"]
    assert any("No diagnosis (indication)" in w for w in report["warnings"])


def test_parse_endpoint_returns_the_diagnosis(client):  # noqa: F811
    text = "Diagnosis: Uncomplicated cystitis\nRx\nTab Paracetamol 500 mg PO TDS\n" + NITRO
    body = client.post("/api/parse-prescription", json={"text": text}).json()
    assert body["diagnosis"] == {
        "text": "Uncomplicated cystitis",
        "syndrome_code": "cystitis",
        "syndrome_name": "Uncomplicated cystitis",
        "note": None,
    }
    assert [o["generic"] for o in body["orders"]] == ["paracetamol", "nitrofurantoin"]


def test_parse_endpoint_says_why_no_syndrome(client):  # noqa: F811
    body = client.post("/api/parse-prescription", json={"text": NITRO}).json()
    assert body["diagnosis"]["syndrome_code"] is None
    assert "No diagnosis" in body["diagnosis"]["note"]
    body = client.post("/api/parse-prescription", json={"text": "Dx: UTI?\n" + NITRO}).json()
    assert body["diagnosis"]["text"] == "UTI?"
    assert body["diagnosis"]["syndrome_code"] is None


def test_non_antibiotic_is_identified_and_not_checked(client):  # noqa: F811
    report = evaluate(client, "Tab Paracetamol 650 mg PO TDS x 3 days\n" + NITRO)
    para = [i for i in report["items"] if i["order_id"] == "rx-1"]
    assert [(i["rule_id"], i["outcome"]) for i in para] == [("R0_IDENTIFIED", "PASS")]
