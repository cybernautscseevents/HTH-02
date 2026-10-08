"""Typed prescription -> Episode -> evaluate_episode -> actions -> review -> audit log.

Everything here runs on the real stack: Person 2's Catalog and renal table, the NCDC rule pack,
the Chroma evidence index and the JSONL audit log. Only the clock is controlled.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.stewardship.api import create_app
from backend.stewardship.audit import JsonlAuditLog
from backend.stewardship.drugs import Catalog
from backend.stewardship.evidence import (
    ChromaEvidenceStore,
    LlmExplainer,
    TemplateExplainer,
    build_store,
    chunks_from_pages,
)
from backend.stewardship.intake import syndrome_from_text
from backend.stewardship.renal import RenalDosing
from backend.stewardship.rulepack import YamlRulePack
from backend.stewardship.service import StewardshipService

from .fakes import T0, FakeRulePack

PATIENT = {
    "id": "p1",
    "age_years": 65,
    "sex": "M",
    "weight_kg": 70,
    "serum_creatinine_mg_dl": 1.0,
    "allergy_status": "NONE_KNOWN",
}
NITRO = "Tab Nitrofurantoin 100 mg BD x 5 days"
CEFTRIAXONE = "Inj Ceftriaxone 2 g IV OD x 7 days"


@pytest.fixture(scope="module")
def catalog():
    return Catalog.load()


@pytest.fixture(scope="module")
def pack():
    return YamlRulePack()


@pytest.fixture(scope="module")
def renal():
    return RenalDosing.load()


@pytest.fixture(scope="module")
def store(pack):
    """Read-only guideline index, built once: indexing the whole pack per test is slow."""
    return build_store(pack, name="app-flow")


@pytest.fixture
def clock():
    state = {"now": T0}
    state["tick"] = lambda: state["now"]
    return state


@pytest.fixture
def service(catalog, pack, renal, store, clock, tmp_path):
    return StewardshipService(
        catalog=catalog,
        rulepack=pack,
        renal=renal,
        audit=JsonlAuditLog(tmp_path / "audit.jsonl"),
        retriever=store,
        clock=clock["tick"],
    )


@pytest.fixture
def client(service):
    return TestClient(create_app(service))


def evaluate(client, prescription, syndrome="cystitis", patient=None, cultures=(), **extra):
    body = {
        "patient": PATIENT | (patient or {}),
        "syndrome_code": syndrome,
        "prescription": prescription,
        "cultures": list(cultures),
    } | extra
    response = client.post("/api/evaluate", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def finding(report, rule_id, order_id=None):
    matches = [i for i in report["items"] if i["rule_id"] == rule_id and i["order_id"] == order_id]
    assert len(matches) == 1, f"{rule_id}/{order_id}: {[i['rule_id'] for i in report['items']]}"
    return matches[0]


def culture(organism, status="FINAL", **susceptibilities):
    return {
        "specimen_type": "urine",
        "status": status,
        "isolates": [{"organism": organism, "susceptibilities": susceptibilities}],
    }


# --- the real rule pack is what runs ---


def test_production_wiring_uses_real_rule_pack(service, client):
    assert isinstance(service.rulepack, YamlRulePack)
    assert not isinstance(service.rulepack, FakeRulePack)
    report = evaluate(client, NITRO)
    assert report["ruleset_version"] == service.rulepack.version
    assert report["ruleset_version"].startswith("ncdc-ntg-2025:")


def test_guideline_matching_prescription_passes_with_ncdc_evidence(client):
    report = evaluate(client, NITRO)
    for rule in ("R1_INDICATION", "R3_DOSE", "R5_DURATION"):
        item = finding(report, rule, "rx-1")
        assert item["outcome"] == "PASS"
        assert item["evidence"][0]["source_id"] == "ncdc-ntg-2025"
        assert item["evidence"][0]["page"] == "p. 39"
        assert item["action"] is None
    # nothing is flagged for a concordant prescription, and no culture is not a finding here
    assert report["status"] == "OK"
    assert all(i["outcome"] == "PASS" for i in report["items"])


def test_typed_prescription_with_header_block(client):
    text = (
        "Patient:\nAge: 65\nWeight: 70 kg\nSex: M\n\nDiagnosis:\npyelonephritis\n\n"
        "Prescription:\nCeftriaxone 2 g IV OD for 7 days"
    )
    report = evaluate(client, text, syndrome=None, diagnosis_text="pyelonephritis")
    assert report["syndrome"] == {
        "code": "pyelonephritis",
        "name": "Acute pyelonephritis",
        "resolution": "mapped_from_text",
    }
    assert [o["generic"] for o in report["orders"]] == ["ceftriaxone"]
    assert report["orders"][0]["dose_mg"] == 2000 and report["orders"][0]["route"] == "IV"
    # ceftriaxone is not an NCDC pyelonephritis regimen: flagged, never passed
    assert finding(report, "R1_INDICATION", "rx-1")["outcome"] == "FLAG"


# --- R1 / R3 / R5 / R2 / R4 / R6 ---


def test_wrong_indication_gives_guideline_action(client):
    report = evaluate(client, "Tab Ciprofloxacin 500 mg BD x 3 days")
    item = finding(report, "R1_INDICATION", "rx-1")
    assert item["outcome"] == "FLAG"
    assert "Review antibiotic selection against the NCDC guideline" in item["action"]
    assert "nitrofurantoin" in item["action"]  # named only because the guideline lists it


def test_wrong_dose(client):
    item = finding(evaluate(client, "Tab Nitrofurantoin 200 mg BD x 5 days"), "R3_DOSE", "rx-1")
    assert item["outcome"] == "FLAG"
    assert item["action"].startswith("Review dose before administration")


def test_wrong_duration(client):
    item = finding(
        evaluate(client, "Tab Nitrofurantoin 100 mg BD x 10 days"), "R5_DURATION", "rx-1"
    )
    assert item["outcome"] == "FLAG"
    assert "duration" in item["action"]


def test_renal_problem(client):
    report = evaluate(
        client, NITRO, patient={"age_years": 80, "weight_kg": 50, "serum_creatinine_mg_dl": 3.0}
    )
    item = finding(report, "R4_RENAL", "rx-1")
    assert (item["outcome"], item["severity"]) == ("FLAG", "HIGH")
    assert "kidney" in item["action"]


def test_missing_renal_inputs_are_not_safe(client):
    report = evaluate(client, NITRO, patient={"weight_kg": None, "serum_creatinine_mg_dl": None})
    assert finding(report, "R4_RENAL", "rx-1")["outcome"] == "CANNOT_ASSESS"


def test_allergy(client):
    report = evaluate(
        client,
        "Tab Amoxicillin 1 g TDS x 5 days",
        syndrome="cap_opd_no_comorbidity",
        patient={"allergy_status": "KNOWN", "allergies": ["penicillin"]},
    )
    item = finding(report, "R6_ALLERGY", "rx-1")
    assert (item["outcome"], item["severity"]) == ("FLAG", "HIGH")


def test_aware_watch_drug_when_access_first_line_exists(client):
    item = finding(evaluate(client, CEFTRIAXONE), "R2_AWARE", "rx-1")
    assert item["outcome"] == "FLAG" and "Access" in item["action"]


def test_cannot_assess_when_inputs_missing(client):
    report = evaluate(client, "Tab Nitrofurantoin 100 mg x 5 days")  # no frequency
    item = finding(report, "R3_DOSE", "rx-1")
    assert item["outcome"] == "CANNOT_ASSESS"
    assert "freq_per_day" in item["action"]


def test_misspelt_drug_is_not_accepted(client):
    report = evaluate(client, "Cefriaxone 1 g IV OD x 7 days")
    item = finding(report, "R0_IDENTIFIED", "rx-1")
    assert item["outcome"] == "CANNOT_ASSESS" and item["severity"] == "HIGH"
    assert [i["rule_id"] for i in report["items"] if i["order_id"] == "rx-1"] == ["R0_IDENTIFIED"]


def test_unresolved_syndrome_cannot_assess_guideline_rules(client):
    report = evaluate(client, NITRO, syndrome=None, diagnosis_text="pneumonia")
    assert report["syndrome"]["resolution"] == "unresolved"
    for rule in ("R1_INDICATION", "R3_DOSE", "R5_DURATION"):
        assert finding(report, rule, "rx-1")["outcome"] == "CANNOT_ASSESS"
    assert any("No supported syndrome" in w for w in report["warnings"])


def test_multiple_antibiotics_are_each_checked(client):
    report = evaluate(client, NITRO + "\nTab Ciprofloxacin 500 mg BD x 3 days")
    assert finding(report, "R1_INDICATION", "rx-1")["outcome"] == "PASS"
    assert finding(report, "R1_INDICATION", "rx-2")["outcome"] == "FLAG"
    assert finding(report, "C1_CULTURE_BEFORE_WATCH")["outcome"] == "FLAG"


# --- cultures ---


def test_no_culture_is_unknown_not_negative_or_susceptible(client):
    report = evaluate(client, CEFTRIAXONE, syndrome="cap_ward")
    assert report["culture"]["state"] == "NOT_AVAILABLE"
    assert "unavailable" in report["culture"]["message"]
    assert "Obtain/review culture" in report["culture"]["action"]
    assert not [
        i for i in report["items"] if i["rule_id"] in ("C3_BUG_DRUG_MISMATCH", "C5_NO_GROWTH")
    ]


def test_not_sent_culture_is_the_same_as_no_culture(client):
    cultures = [{"specimen_type": "urine", "status": "NOT_SENT"}]
    assert evaluate(client, NITRO, cultures=cultures)["culture"]["state"] == "NOT_AVAILABLE"


def test_negative_culture_is_distinct_from_no_culture(client, clock):
    cultures = [{"specimen_type": "urine", "status": "NO_GROWTH"}]
    report = evaluate(client, NITRO, cultures=cultures)
    assert report["culture"]["state"] == "NO_GROWTH"


def test_negative_culture_after_threshold_raises_c5(client, service, clock):
    cultures = [{"specimen_type": "urine", "status": "NO_GROWTH"}]
    body = {
        "patient": PATIENT,
        "syndrome_code": "cystitis",
        "prescription": NITRO,
        "cultures": cultures,
    }
    episode = client.post("/api/episodes", json=body).json()
    clock["now"] = T0 + timedelta(hours=49)
    report = client.post(f"/api/episodes/{episode['id']}/evaluate").json()
    item = finding(report, "C5_NO_GROWTH")
    assert item["outcome"] == "FLAG" and item["suggestion_action"] == "provide_input"


def test_resistant_organism_flags_drug_with_action(client):
    cultures = [culture("Escherichia coli", ceftriaxone="R", ciprofloxacin="S", amikacin="S")]
    report = evaluate(client, CEFTRIAXONE, syndrome="cap_ward", cultures=cultures)
    item = finding(report, "C3_BUG_DRUG_MISMATCH", "rx-1")
    assert (item["outcome"], item["severity"]) == ("FLAG", "HIGH")
    assert "consider an alternative the organism is susceptible to" in item["action"]
    assert report["culture"]["state"] == "FINAL"


def test_intrinsic_resistance_from_catalog_is_used(client):
    cultures = [culture("Pseudomonas aeruginosa")]  # no panel at all
    report = evaluate(client, CEFTRIAXONE, syndrome="cap_ward", cultures=cultures)
    item = finding(report, "C3_BUG_DRUG_MISMATCH", "rx-1")
    assert "intrinsically resistant" in item["message"]
    assert any(e["source_id"] == "amrie-expected-resistance" for e in item["evidence"])


def test_susceptible_organism_is_not_flagged_resistant(client):
    cultures = [culture("Escherichia coli", nitrofurantoin="S")]
    report = evaluate(client, NITRO, cultures=cultures)
    assert not [
        i for i in report["items"] if i["rule_id"] in ("C3_BUG_DRUG_MISMATCH", "C8_NOT_TESTED")
    ]


def test_susceptible_to_access_guideline_drug_suggests_step_down(client):
    cultures = [culture("Escherichia coli", ceftriaxone="S", cefazolin="S")]
    report = evaluate(client, CEFTRIAXONE, syndrome="cellulitis_moderate_severe", cultures=cultures)
    item = finding(report, "C4_DE_ESCALATE", "rx-1")
    assert item["suggestion_action"] == "switch" and "cefazolin" in item["action"]


def test_unknown_organism_cannot_be_assessed(client):
    report = evaluate(client, NITRO, cultures=[culture("Klingonella", nitrofurantoin="S")])
    assert finding(report, "C9_ORGANISM_UNKNOWN")["outcome"] == "CANNOT_ASSESS"


def test_missing_susceptibility_cannot_be_assessed(client):
    report = evaluate(
        client,
        CEFTRIAXONE,
        syndrome="cap_ward",
        cultures=[culture("Escherichia coli", amikacin="S")],
    )
    item = finding(report, "C8_NOT_TESTED", "rx-1")
    assert item["outcome"] == "CANNOT_ASSESS" and item["missing_inputs"] == ["susceptibility"]


@pytest.mark.parametrize(
    "cultures",
    [
        [{"specimen_type": "urine", "status": "FINAL"}],  # positive with no organism
        [
            {
                "specimen_type": "urine",
                "status": "NO_GROWTH",
                "isolates": [{"organism": "Escherichia coli"}],
            }
        ],  # negative but isolate listed
        [culture("Escherichia coli", gentamycinn="R")],  # unrecognised agent
    ],
)
def test_inconsistent_culture_is_rejected(client, cultures):
    body = {
        "patient": PATIENT,
        "syndrome_code": "cystitis",
        "prescription": NITRO,
        "cultures": cultures,
    }
    assert client.post("/api/evaluate", json=body).status_code == 422


def test_unknown_syndrome_code_is_rejected(client):
    body = {"patient": PATIENT, "syndrome_code": "CAP", "prescription": NITRO}
    assert client.post("/api/evaluate", json=body).status_code == 422


# --- review -> audit, time-out ---


def review(client, report, rule_id, order_id, action, **extra):
    return client.post(
        "/api/reviews",
        json={
            "episode_id": report["episode_id"],
            "evaluation_id": report["id"],
            "finding_rule_id": rule_id,
            "order_id": order_id,
            "reviewer": "pharmacist-1",
            "action": action,
        }
        | extra,
    )


def test_review_is_validated_and_appended_to_audit_log(client, service):
    report = evaluate(client, "Tab Ciprofloxacin 500 mg BD x 3 days")
    # CANNOT_ASSESS cannot be accepted
    assert review(client, report, "R3_DOSE", "rx-1", "ACCEPT").status_code == 422
    # an override needs a reason
    assert review(client, report, "R1_INDICATION", "rx-1", "OVERRIDE").status_code == 422
    # a finding not in the evaluation is refused
    assert review(client, report, "R1_INDICATION", "rx-9", "ACCEPT").status_code == 422
    assert service.audit.list() == []

    ok = review(client, report, "R1_INDICATION", "rx-1", "OVERRIDE", reason_code="PATIENT_FACTOR")
    assert ok.status_code == 200
    entries = client.get("/api/audit").json()
    assert len(entries) == 1
    assert entries[0]["action"] == "review.OVERRIDE" and entries[0]["actor"] == "pharmacist-1"
    assert entries[0]["entity_id"] == f"{report['id']}:R1_INDICATION:rx-1"
    assert client.get("/api/audit", params={"entity_id": "nope"}).json() == []


def test_timeout_flow(client, clock):
    report = evaluate(client, NITRO)
    assert client.get("/api/timeout-due").json() == []
    clock["now"] = T0 + timedelta(hours=50)
    (due,) = client.get("/api/timeout-due").json()
    assert due["episode_id"] == report["episode_id"] and due["hours_elapsed"] == 50.0
    done = client.post(
        "/api/reviews",
        json={
            "episode_id": report["episode_id"],
            "evaluation_id": report["id"],
            "reviewer": "pharmacist-1",
            "action": "ACCEPT",
            "reason_code": "TIMEOUT_DONE",
        },
    )
    assert done.status_code == 200
    assert client.get("/api/timeout-due").json() == []


def test_unknown_ids_are_404(client):
    assert client.post("/api/episodes/nope/evaluate").status_code == 404
    assert client.get("/api/evaluations/nope").status_code == 404


# --- API surface and determinism ---


def test_syndromes_endpoint_lists_exactly_the_rule_pack(client, pack):
    codes = [s["code"] for s in client.get("/api/syndromes").json()]
    hand_checked = YamlRulePack(imported=None).codes()
    assert codes == list(pack.codes()) and len(codes) == len(set(codes))
    assert len(hand_checked) == 13 and tuple(codes[:13]) == hand_checked


def test_same_episode_gives_same_findings(client):
    first, second = (evaluate(client, NITRO + "\n" + CEFTRIAXONE) for _ in range(2))
    strip = lambda r: [(i["rule_id"], i["outcome"], i["message"]) for i in r["items"]]  # noqa: E731
    assert strip(first) == strip(second)


def test_parse_endpoint_does_not_accept_unknown_drugs(client):
    body = client.post("/api/parse-prescription", json={"text": "Tab Zorblax 5 mg OD"}).json()
    assert body["orders"][0]["generic"] is None
    assert body["orders"][0]["norm_status"] == "NO_MATCH"


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("Acute pyelonephritis", "pyelonephritis"),
        ("uncomplicated UTI", "cystitis"),
        ("COPD exacerbation", "copd_exacerbation"),
        ("pneumonia", None),  # several CAP codes: a person must choose
        ("complicated UTI", None),
        ("cellulitis", None),
        ("", None),
    ],
)
def test_free_text_diagnosis_mapping_is_explicit(text, code):
    assert syndrome_from_text(text) == code


# --- evidence retrieval and explanation (never decides) ---


def test_retrieval_returns_sourced_passages_for_the_syndrome(pack):
    store = build_store(pack, name="retrieval-test")
    passages = store.retrieve("nitrofurantoin dose duration", syndrome_code="cystitis", k=2)
    assert passages and "Nitrofurantoin" in passages[0].text
    assert all(p.document.startswith("NCDC") and p.page == "p. 39" for p in passages)
    assert "5.1 Cystitis" in passages[0].citation


def test_findings_carry_retrieved_guideline_passages(client):
    item = finding(
        evaluate(client, "Tab Ciprofloxacin 500 mg BD x 3 days"), "R1_INDICATION", "rx-1"
    )
    assert item["guideline_passages"]
    assert "NCDC" in item["explanation"] and "p. 39" in item["explanation"]


def test_chunking_keeps_section_and_page():
    pages = ["5.1 Cystitis\nNitrofurantoin 100 mg q12h\n", "5.2 Pyelonephritis\nPip-taz 4.5 g\n"]
    chunks = chunks_from_pages(pages, document="NCDC test", prefix="t")
    assert [(c.section, c.page) for c in chunks] == [
        ("5.1 Cystitis", "pdf p. 1"),
        ("5.2 Pyelonephritis", "pdf p. 2"),
    ]
    store = ChromaEvidenceStore("chunk-test")
    store.add(chunks)
    assert store.retrieve("cystitis nitrofurantoin", k=1)[0].section == "5.1 Cystitis"


def test_llm_explainer_cannot_change_the_finding(service, client):
    report = evaluate(client, "Tab Ciprofloxacin 500 mg BD x 3 days")
    flagged = next(
        i for i in service.get_evaluation(report["id"]).findings if i.rule_id == "R1_INDICATION"
    )
    seen = []

    def complete(prompt):
        seen.append(prompt)
        return "Safe to give."  # a bad model answer

    text = LlmExplainer(complete).explain(flagged, [])
    assert text == "Safe to give."
    assert "do not change it" in seen[0] and "FLAG" in seen[0]
    # the engine's result is a separate object the explanation cannot touch
    assert flagged.outcome.value == "FLAG"


def test_llm_failure_falls_back_to_template():
    from backend.stewardship.schemas import Finding, Outcome, Severity

    f = Finding(
        rule_id="R1_INDICATION",
        outcome=Outcome.FLAG,
        severity=Severity.MODERATE,
        message="x is not listed.",
    )

    def broken(prompt):
        raise RuntimeError("down")

    assert LlmExplainer(broken).explain(f, []) == TemplateExplainer().explain(f, [])
