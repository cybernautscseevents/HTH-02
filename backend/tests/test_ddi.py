"""Deterministic drug-drug interaction (DDI) checks: statuses, pair generation, provider
failures, the DrugBank index, and the real local DrugBank XML export.

Severity is never inferred from wording: the source states it or the result is "unknown",
and "no interaction reported" is worded so it can never be read as "guaranteed safe".
"""

import pytest
from fastapi.testclient import TestClient

from backend.stewardship import config
from backend.stewardship.advice import action_for
from backend.stewardship.api import create_app
from backend.stewardship.audit import JsonlAuditLog
from backend.stewardship.ddi import (
    DDIStatus,
    DrugBankDDIProvider,
    DDIResult,
    SourceUnavailable,
    build_index,
    check_pairs,
)
from backend.stewardship.drugs import Catalog
from backend.stewardship.evidence import Passage
from backend.stewardship.intake import EpisodeRequest
from backend.stewardship.renal import RenalDosing
from backend.stewardship.review import ReviewError
from backend.stewardship.rulepack import YamlRulePack
from backend.stewardship.schemas import (
    Finding,
    NormStatus,
    Outcome,
    ReviewAction,
    Severity,
    Setting,
)
from backend.stewardship.service import ReviewRequest, StewardshipService

from .fakes import T0, episode, order

# A two-drug cystitis course that evaluates clean (every R rule PASS, status OK) on the real
# rule pack: the baseline DDI findings must not perturb.
CLEAN_RX = (
    "Tab Nitrofurantoin 100 mg BD x 5 days\n"
    "Tab Sulfamethoxazole/Trimethoprim 960 mg BD x 5 days"
)
PAIR = ("nitrofurantoin", "sulfamethoxazole/trimethoprim")
PATIENT = dict(
    id="p1",
    age_years=45,
    sex="F",
    weight_kg=60.0,
    serum_creatinine_mg_dl=0.9,
    allergy_status="NONE_KNOWN",
)

requires_drugbank = pytest.mark.skipif(
    not config.DRUGBANK_XML_PATH.exists(),
    reason="local DrugBank XML export not present (licensed data, never committed)",
)


# --- test doubles -----------------------------------------------------------------------------


class FakeDDI:
    """DDIProvider test double: canned pair results, recorded calls, optional crash."""

    def __init__(self, results: dict[tuple[str, str], DDIResult] | None = None, crash=False):
        self.results = {tuple(sorted(k)): v for k, v in (results or {}).items()}
        self.crash = crash
        self.calls: list[tuple[str, str]] = []

    def lookup_pair(self, drug_a: str, drug_b: str) -> DDIResult:
        if self.crash:
            raise RuntimeError("DrugBank is down")
        self.calls.append((drug_a, drug_b))
        canned = self.results.get(tuple(sorted((drug_a, drug_b))))
        if canned is not None:
            return canned
        return DDIResult(
            drug_a=drug_a, drug_b=drug_b, status=DDIStatus.NO_INTERACTION_REPORTED_BY_SOURCE
        )


def found(a, b, description="Drug A may increase the effects of Drug B.", severity="unknown"):
    return DDIResult(
        drug_a=a,
        drug_b=b,
        status=DDIStatus.INTERACTION_FOUND,
        severity=severity,
        description=description,
        needs_review=True,
    )


def cannot_assess(a, b, reason="not in the source"):
    return DDIResult(
        drug_a=a, drug_b=b, status=DDIStatus.CANNOT_ASSESS, reason=reason, needs_review=True
    )


class StubRetriever:
    """Returns one guideline passage for any query, so passage handling can be observed."""

    def retrieve(self, query, syndrome_code=None, k=2):
        return [
            Passage(
                text="Nitrofurantoin 100 mg q12h for 5 days",
                document="NCDC test",
                section="5.1 Cystitis",
                page="p. 39",
                distance=0.1,
            )
        ]


# --- shared fixtures --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def catalog():
    return Catalog.load()


@pytest.fixture(scope="module")
def pack():
    return YamlRulePack()


@pytest.fixture(scope="module")
def renal():
    return RenalDosing.load()


def make_service(catalog, pack, renal, tmp_path, ddi=None, retriever=None):
    return StewardshipService(
        catalog=catalog,
        rulepack=pack,
        renal=renal,
        audit=JsonlAuditLog(tmp_path / "audit.jsonl"),
        retriever=retriever,
        ddi=ddi,
        clock=lambda: T0,
    )


def evaluate_with(svc, prescription=CLEAN_RX, syndrome="cystitis"):
    return svc.evaluate_request(
        EpisodeRequest(
            patient=PATIENT, setting=Setting.OPD, syndrome_code=syndrome, prescription=prescription
        )
    )


def ddi_items(report):
    return [i for i in report.items if i.rule_id.startswith("DDI_")]


# --- pair generation and lookup semantics (no XML involved) -----------------------------------


def test_interaction_found_is_flagged_with_source_description():
    prov = FakeDDI({PAIR: found(*PAIR)})
    checks = check_pairs(episode(orders=(order(PAIR[0], id="o1"), order(PAIR[1], id="o2"))), prov)
    (item,) = checks.findings
    assert checks.crashed is False
    assert item.finding.outcome is Outcome.FLAG
    assert item.finding.rule_id == f"DDI_INTERACTION:{PAIR[0]}+{PAIR[1]}"
    assert item.finding.evidence[0].source_id == f"drugbank:{PAIR[0]}+{PAIR[1]}"
    assert item.finding.evidence[0].quote == "Drug A may increase the effects of Drug B."
    assert "DrugBank reports an interaction" in item.finding.message
    # no source severity stated: the finding is an attention-level MODERATE, never a guess
    assert item.finding.severity is Severity.MODERATE
    assert item.result.severity == "unknown" and item.result.needs_review is True


@pytest.mark.parametrize(
    ("severity", "expected"),
    [("major", Severity.HIGH), ("moderate", Severity.MODERATE), ("minor", Severity.LOW)],
)
def test_stated_source_severity_maps_to_finding_severity(severity, expected):
    prov = FakeDDI({PAIR: found(*PAIR, severity=severity)})
    checks = check_pairs(episode(orders=(order(PAIR[0], id="o1"), order(PAIR[1], id="o2"))), prov)
    (item,) = checks.findings
    assert item.finding.severity is expected
    assert item.result.severity == severity


def test_unstated_severity_is_unknown_never_inferred_from_wording():
    prov = FakeDDI({PAIR: found(*PAIR, description="This is a severe major interaction.")})
    checks = check_pairs(episode(orders=(order(PAIR[0], id="o1"), order(PAIR[1], id="o2"))), prov)
    (item,) = checks.findings
    assert item.result.severity == "unknown"
    assert item.finding.severity is Severity.MODERATE  # attention level, not a severity claim


def test_severity_outside_allowed_values_is_reported_as_unknown():
    result = found(*PAIR, severity="catastrophic")
    assert result.severity == "unknown"
    assert DDIResult(status=DDIStatus.INTERACTION_FOUND, severity="severe").severity == "unknown"


def test_no_interaction_is_a_pass_that_does_not_promise_safety():
    prov = FakeDDI()  # every pair: NO_INTERACTION_REPORTED_BY_SOURCE
    checks = check_pairs(episode(orders=(order(PAIR[0], id="o1"), order(PAIR[1], id="o2"))), prov)
    (item,) = checks.findings
    assert item.finding.outcome is Outcome.PASS and item.finding.severity is Severity.INFO
    assert "reports no interaction" in item.finding.message
    assert "not that the pair is guaranteed safe" in item.finding.message
    assert item.result.needs_review is False


def test_drug_the_source_cannot_answer_is_cannot_assess():
    prov = FakeDDI({PAIR: cannot_assess(*PAIR, reason="'unlisted' was not found in the index.")})
    checks = check_pairs(episode(orders=(order(PAIR[0], id="o1"), order(PAIR[1], id="o2"))), prov)
    (item,) = checks.findings
    assert item.finding.outcome is Outcome.CANNOT_ASSESS
    assert item.finding.severity is Severity.HIGH
    assert item.finding.evidence == ()
    assert "could not assess" in item.finding.message
    assert item.result.needs_review is True


def test_pair_is_order_independent_and_canonical():
    prov = FakeDDI()
    forward = episode(orders=(order(PAIR[0], id="o1"), order(PAIR[1], id="o2")))
    reverse = episode(orders=(order(PAIR[1], id="o1"), order(PAIR[0], id="o2")))
    ids_a = [d.finding.rule_id for d in check_pairs(forward, prov).findings]
    ids_b = [d.finding.rule_id for d in check_pairs(reverse, prov).findings]
    assert ids_a == ids_b == [f"DDI_NO_INTERACTION:{PAIR[0]}+{PAIR[1]}"]
    assert all(call == tuple(sorted(call)) for call in prov.calls)  # lookup args canonical


def test_duplicate_orders_are_deduplicated_so_n_drugs_give_n_pairs():
    prov = FakeDDI()
    repeated = episode(
        orders=(
            order("nitrofurantoin", id="o1"),
            order("nitrofurantoin", id="o2"),
            order("sulfamethoxazole/trimethoprim", id="o3"),
        )
    )
    checks = check_pairs(repeated, prov)
    assert len(checks.findings) == 1 and len(prov.calls) == 1

    three = episode(
        orders=(order("nitrofurantoin", id="o1"), order("ceftriaxone", id="o2"), order("amikacin", id="o3"))
    )
    prov3 = FakeDDI()
    assert len(check_pairs(three, prov3).findings) == 3  # 3 unique drugs -> 3 pairs
    assert len({tuple(sorted(c)) for c in prov3.calls}) == 3


def test_empty_drug_list_yields_no_pairs():
    prov = FakeDDI()
    checks = check_pairs(episode(orders=()), prov)
    assert checks.findings == () and checks.crashed is False and prov.calls == []


def test_one_drug_yields_no_pairs():
    prov = FakeDDI()
    checks = check_pairs(episode(orders=(order("nitrofurantoin", id="o1"),)), prov)
    assert checks.findings == () and checks.crashed is False and prov.calls == []


def test_unidentified_order_is_cannot_assess_and_carries_its_order_id():
    prov = FakeDDI()
    ep = episode(
        orders=(
            order("nitrofurantoin", id="o1"),
            order(None, id="o2", raw_text="Zorblaxin 500 mg", norm_status=NormStatus.NO_MATCH),
        )
    )
    checks = check_pairs(ep, prov)
    (item,) = checks.findings
    assert item.finding.outcome is Outcome.CANNOT_ASSESS
    assert item.finding.order_id == "o2"
    assert "interactions with the other medication(s)" in item.finding.message
    assert "matches no known drug" in item.result.reason
    assert prov.calls == []  # an unreadable drug is not silently dropped: no pair is guessed


def test_crashing_provider_is_cannot_assess_and_marks_the_check_crashed():
    checks = check_pairs(
        episode(orders=(order(PAIR[0], id="o1"), order(PAIR[1], id="o2"))), FakeDDI(crash=True)
    )
    assert checks.crashed is True
    (item,) = checks.findings
    assert item.finding.outcome is Outcome.CANNOT_ASSESS
    assert "Check failed (RuntimeError)" in item.finding.message


# --- service integration: DDI is additive and can never break R0-R6 / cultures ----------------


def test_service_without_a_ddi_provider_runs_no_ddi_checks(catalog, pack, renal, tmp_path):
    report = evaluate_with(make_service(catalog, pack, renal, tmp_path))
    assert ddi_items(report) == []
    assert report.status.value == "OK"  # baseline for the clean two-drug course


def test_ddi_pass_findings_do_not_change_the_evaluation_status(catalog, pack, renal, tmp_path):
    without = evaluate_with(make_service(catalog, pack, renal, tmp_path))
    with_passes = evaluate_with(make_service(catalog, pack, renal, tmp_path, ddi=FakeDDI()))
    assert with_passes.status == without.status
    assert [i.rule_id for i in with_passes.findings if not i.rule_id.startswith("DDI_")] == [
        i.rule_id for i in without.findings
    ]
    (ddi,) = ddi_items(with_passes)
    assert ddi.outcome.value == "PASS" and ddi.severity == "INFO"


def test_ddi_interaction_flag_marks_the_evaluation_flagged(catalog, pack, renal, tmp_path):
    svc = make_service(catalog, pack, renal, tmp_path, ddi=FakeDDI({PAIR: found(*PAIR)}))
    report = evaluate_with(svc)
    assert report.status.value == "FLAGGED"
    non_pass = [i for i in report.findings if i.outcome is not Outcome.PASS]
    assert [f.rule_id for f in non_pass] == [f"DDI_INTERACTION:{PAIR[0]}+{PAIR[1]}"]


def test_crashing_ddi_provider_marks_the_evaluation_incomplete(catalog, pack, renal, tmp_path):
    svc = make_service(catalog, pack, renal, tmp_path, ddi=FakeDDI(crash=True))
    report = evaluate_with(svc)  # must not raise
    assert report.status.value == "INCOMPLETE"
    # every prescription and culture rule still ran and is intact
    assert not [i for i in report.findings if i.rule_id.startswith("R") and i.outcome.value != "PASS"]
    (ddi,) = ddi_items(report)
    assert ddi.outcome == "CANNOT_ASSESS" and ddi.order_id is None


def test_r_and_c_findings_are_identical_with_and_without_ddi(catalog, pack, renal, tmp_path):
    prescription = CLEAN_RX + "\nTab Ciprofloxacin 500 mg BD x 3 days"
    without = evaluate_with(make_service(catalog, pack, renal, tmp_path), prescription)
    with_ddi = evaluate_with(
        make_service(catalog, pack, renal, tmp_path, ddi=FakeDDI({PAIR: found(*PAIR)})),
        prescription,
    )

    def engine_findings(report):
        return [
            (i.rule_id, i.order_id, i.outcome, i.message, i.severity)
            for i in report.items
            if not i.rule_id.startswith("DDI_")
        ]

    assert engine_findings(with_ddi) == engine_findings(without)
    assert any(i.rule_id.startswith("DDI_") for i in with_ddi.items)


def test_culture_findings_are_identical_with_and_without_ddi(catalog, pack, renal, tmp_path):
    culture_input = [
        {
            "specimen_type": "urine",
            "status": "FINAL",
            "isolates": [{"organism": "Escherichia coli", "susceptibilities": {"nitrofurantoin": "S"}}],
        }
    ]
    req_without = EpisodeRequest(
        patient=PATIENT,
        setting=Setting.OPD,
        syndrome_code="cystitis",
        prescription=CLEAN_RX,
        cultures=culture_input,
    )
    svc_without = make_service(catalog, pack, renal, tmp_path)
    svc_with = make_service(catalog, pack, renal, tmp_path, ddi=FakeDDI({PAIR: found(*PAIR)}))
    without = svc_without.evaluate_request(req_without)
    with_ddi = svc_with.evaluate_request(req_without)

    culture_findings_without = [i for i in without.items if i.rule_id.startswith("C")]
    culture_findings_with = [i for i in with_ddi.items if i.rule_id.startswith("C")]
    assert len(culture_findings_without) > 0
    assert [(f.rule_id, f.outcome, f.message) for f in culture_findings_with] == [
        (f.rule_id, f.outcome, f.message) for f in culture_findings_without
    ]
    assert without.culture.state == with_ddi.culture.state


def test_existing_normalization_is_reused(catalog, pack, renal, tmp_path):
    prov = FakeDDI()
    svc = make_service(catalog, pack, renal, tmp_path, ddi=prov)
    # "Augmentin" is a brand name normalized by Catalog to "amoxicillin/clavulanic acid"
    rx = "Tab Augmentin 625 mg BD x 5 days\nTab Ciprofloxacin 500 mg BD x 3 days"
    report = evaluate_with(svc, rx)
    assert len(prov.calls) == 1
    pair = tuple(sorted(prov.calls[0]))
    assert pair == ("amoxicillin/clavulanic acid", "ciprofloxacin")


def test_finding_view_carries_the_structured_ddi_block(catalog, pack, renal, tmp_path):
    svc = make_service(catalog, pack, renal, tmp_path, ddi=FakeDDI({PAIR: found(*PAIR)}))
    report = evaluate_with(svc)
    (item,) = ddi_items(report)
    assert item.ddi is not None
    assert item.ddi.type == "DDI"
    assert item.ddi.status is DDIStatus.INTERACTION_FOUND
    assert item.ddi.drug_a == PAIR[0] and item.ddi.drug_b == PAIR[1]
    assert item.ddi.source == "DrugBank" and item.ddi.needs_review is True
    assert item.ddi.severity == "unknown"
    assert item.ddi.action is not None and "pharmacist" in item.ddi.action
    assert item.ddi.mechanism == "Drug A may increase the effects of Drug B."
    assert item.ddi.explanation == "Drug A may increase the effects of Drug B."
    assert "pharmacist" in item.action  # from the advice table, not invented per finding
    assert item.drug == f"{PAIR[0]} + {PAIR[1]}"
    assert item.guideline_passages == ()


def test_ddi_finding_cites_drugbank_and_not_retrieved_guideline_passages(
    catalog, pack, renal, tmp_path
):
    svc = make_service(
        catalog,
        pack,
        renal,
        tmp_path,
        ddi=FakeDDI({PAIR: found(*PAIR)}),
        retriever=StubRetriever(),
    )
    report = evaluate_with(svc, CLEAN_RX + "\nTab Ciprofloxacin 500 mg BD x 3 days")
    flagged_rule = next(
        i.rule_id
        for i in report.items
        if i.rule_id.startswith("R") and i.outcome.value == "FLAG"
    )
    r_flag = next(i for i in report.items if i.rule_id == flagged_rule)
    assert r_flag.guideline_passages, "existing rules still retrieve guideline passages"
    item = next(i for i in ddi_items(report) if i.outcome.value == "FLAG")
    assert item.guideline_passages == ()
    assert "DrugBank" in item.explanation and "NCDC" not in item.explanation
    assert item.evidence[0].quote == "Drug A may increase the effects of Drug B."


def test_actions_from_the_fixed_table(catalog, pack, renal, tmp_path):
    flagged = Finding(
        rule_id=f"DDI_INTERACTION:{PAIR[0]}+{PAIR[1]}",
        outcome=Outcome.FLAG,
        severity=Severity.MODERATE,
        message="x",
    )
    unknown = Finding(
        rule_id="DDI_CANNOT_ASSESS:order:rx-2",
        outcome=Outcome.CANNOT_ASSESS,
        severity=Severity.HIGH,
        message="x",
    )
    passed = Finding(rule_id=f"DDI_NO_INTERACTION:{PAIR[0]}+{PAIR[1]}", outcome=Outcome.PASS, severity=Severity.INFO, message="x")
    assert "pharmacist" in action_for(flagged)
    assert "Confirm the drug identity" in action_for(unknown)
    assert action_for(passed) is None


def test_ddi_findings_flow_through_the_review_workflow(catalog, pack, renal, tmp_path):
    svc = make_service(catalog, pack, renal, tmp_path, ddi=FakeDDI({PAIR: found(*PAIR)}))
    report = evaluate_with(svc)
    (ddi,) = ddi_items(report)
    entry = svc.review(
        ReviewRequest(
            episode_id=report.episode_id,
            evaluation_id=report.id,
            finding_rule_id=ddi.rule_id,
            reviewer="pharmacist-1",
            action=ReviewAction.ACCEPT,
        )
    )
    assert entry.action == "review.ACCEPT" and len(svc.audit.list()) == 1

    # a CANNOT_ASSESS DDI finding cannot simply be accepted: there is nothing to accept
    svc2 = make_service(catalog, pack, renal, tmp_path, ddi=FakeDDI({PAIR: cannot_assess(*PAIR)}))
    report2 = evaluate_with(svc2)
    (unknown,) = ddi_items(report2)
    with pytest.raises(ReviewError):
        svc2.review(
            ReviewRequest(
                episode_id=report2.episode_id,
                evaluation_id=report2.id,
                finding_rule_id=unknown.rule_id,
                reviewer="pharmacist-1",
                action=ReviewAction.ACCEPT,
            )
        )


def test_unreadable_second_drug_blocks_its_interactions_in_the_report(
    catalog, pack, renal, tmp_path
):
    svc = make_service(catalog, pack, renal, tmp_path, ddi=FakeDDI())
    report = evaluate_with(svc, CLEAN_RX + "\nTab Zorblaxin 500 mg OD")
    (blocked,) = [i for i in ddi_items(report) if i.outcome == "CANNOT_ASSESS"]
    assert blocked.order_id == "rx-3" and blocked.ddi.status is DDIStatus.CANNOT_ASSESS
    # the identified pair is still checked and reported
    assert any(i.outcome == "PASS" and i.rule_id.startswith("DDI_NO_INTERACTION") for i in ddi_items(report))


# --- the index built from the local DrugBank XML ------------------------------------------------

FIXTURE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<drugbank xmlns="http://www.drugbank.ca" version="5.1" exported-on="2026-04-07">
  <drug type="small molecule">
    <drugbank-id primary="true">DB00001</drugbank-id>
    <name>Drug A</name>
    <synonyms><synonym language="english">Alpha Mab</synonym></synonyms>
    <drug-interactions>
      <drug-interaction>
        <drugbank-id>DB00002</drugbank-id>
        <name>Drug B</name>
        <severity>moderate</severity>
        <description>Drug A may increase the effects of Drug B.</description>
      </drug-interaction>
    </drug-interactions>
  </drug>
  <drug type="small molecule">
    <drugbank-id primary="true">DB00002</drugbank-id>
    <name>Drug B</name>
    <drug-interactions>
      <drug-interaction>
        <drugbank-id>DB00001</drugbank-id>
        <name>Drug A</name>
        <description>Reverse direction, must not override the forward entry.</description>
      </drug-interaction>
    </drug-interactions>
  </drug>
  <drug type="small molecule">
    <drugbank-id primary="true">DB00003</drugbank-id>
    <name>Drug C</name>
  </drug>
</drugbank>
"""


@pytest.fixture
def fixture_source(tmp_path):
    xml = tmp_path / "fixture.xml"
    xml.write_text(FIXTURE_XML, encoding="utf-8")
    return xml, tmp_path / "index.sqlite"


def test_index_builds_from_the_xml_with_meta_aliases_and_deduplicated_pairs(fixture_source):
    xml, index = fixture_source
    meta = build_index(xml, index)
    assert meta["version"] == "5.1" and meta["exported_on"] == "2026-04-07"
    assert meta["drugs"] == "3" and meta["aliases"] == "4"  # A, Alpha Mab, B, C
    assert meta["pairs"] == "1"  # A+B and B+A are one unordered pair


def test_lookup_against_the_built_index(fixture_source):
    xml, index = fixture_source
    provider = DrugBankDDIProvider(xml_path=xml, index_path=index)

    interaction = provider.lookup_pair("Drug A", "Drug B")
    assert interaction.status is DDIStatus.INTERACTION_FOUND
    assert interaction.severity == "moderate"  # stated by the source
    assert interaction.description == "Drug A may increase the effects of Drug B."
    assert interaction.source_version and "5.1" in interaction.source_version
    assert provider.lookup_pair("Drug B", "Drug A").description == interaction.description

    assert provider.lookup_pair("Drug A", "Drug C").status is DDIStatus.NO_INTERACTION_REPORTED_BY_SOURCE
    unknown = provider.lookup_pair("Drug A", "Nowherezole")
    assert unknown.status is DDIStatus.CANNOT_ASSESS and "Nowherezole" in unknown.reason
    same = provider.lookup_pair("Drug A", "Alpha Mab")  # both resolve to DB00001
    assert same.status is DDIStatus.CANNOT_ASSESS and "same drug" in same.reason


def test_lookup_keys_are_case_and_separator_insensitive(fixture_source):
    xml, index = fixture_source
    provider = DrugBankDDIProvider(xml_path=xml, index_path=index)
    assert provider.lookup_pair("DRUG-A", "drug b").status is DDIStatus.INTERACTION_FOUND
    assert provider.lookup_pair("alpha mab", "Drug B").status is DDIStatus.INTERACTION_FOUND


def test_missing_source_degrades_to_cannot_assess_and_never_raises(tmp_path):
    provider = DrugBankDDIProvider(xml_path=tmp_path / "no.xml", index_path=tmp_path / "no.sqlite")
    with pytest.raises(SourceUnavailable):
        provider.ensure_index()
    result = provider.lookup_pair("Drug A", "Drug B")
    assert result.status is DDIStatus.CANNOT_ASSESS
    assert result.needs_review is True and "SourceUnavailable" in result.reason


def test_corrupt_index_with_missing_xml_degrades_to_cannot_assess(tmp_path):
    index = tmp_path / "index.sqlite"
    index.write_bytes(b"this is not a database")
    provider = DrugBankDDIProvider(xml_path=tmp_path / "no.xml", index_path=index)
    result = provider.lookup_pair("Drug A", "Drug B")
    assert result.status is DDIStatus.CANNOT_ASSESS


def test_index_is_reused_until_the_source_changes(fixture_source):
    xml, index = fixture_source
    first = DrugBankDDIProvider(xml_path=xml, index_path=index)
    first.ensure_index()
    built_at = first.meta()["built_at"]
    first.close()

    again = DrugBankDDIProvider(xml_path=xml, index_path=index)
    again.ensure_index()
    assert again.meta()["built_at"] == built_at  # reused, not rebuilt
    again.close()

    xml.write_text(FIXTURE_XML + " ", encoding="utf-8")  # the source file changed
    stale = DrugBankDDIProvider(xml_path=xml, index_path=index)
    stale.ensure_index()
    assert stale.meta()["built_at"] != built_at  # rebuilt from the new source
    stale.close()


# --- the real local DrugBank export ------------------------------------------------------------


@pytest.fixture(scope="session")
def drugbank():
    return DrugBankDDIProvider()


@requires_drugbank
def test_real_interaction_pair_is_reported_by_the_source(drugbank):
    result = drugbank.lookup_pair("ciprofloxacin", "metronidazole")
    assert result.status is DDIStatus.INTERACTION_FOUND
    assert "Metronidazole" in result.description
    # this export carries no structured severity: unknown, needs review, never guessed
    assert result.severity == "unknown" and result.needs_review is True
    assert result.source == "DrugBank" and result.source_version.startswith("5.1")


@requires_drugbank
def test_real_pair_the_source_does_not_report_is_not_called_safe(drugbank):
    result = drugbank.lookup_pair("metronidazole", "nitrofurantoin")
    assert result.status is DDIStatus.NO_INTERACTION_REPORTED_BY_SOURCE
    assert result.needs_review is False and result.severity == "unknown"


@requires_drugbank
def test_real_lookup_of_an_unknown_drug_is_cannot_assess(drugbank):
    result = drugbank.lookup_pair("ciprofloxacin", "notarealdrugindeed")
    assert result.status is DDIStatus.CANNOT_ASSESS
    assert "notarealdrugindeed" in result.reason


@requires_drugbank
def test_real_lookup_is_symmetric_and_deterministic(drugbank):
    forward = drugbank.lookup_pair("ciprofloxacin", "metronidazole")
    reverse = drugbank.lookup_pair("metronidazole", "ciprofloxacin")
    again = drugbank.lookup_pair("ciprofloxacin", "metronidazole")
    assert (forward.status, forward.description) == (reverse.status, reverse.description)
    assert forward == again


@requires_drugbank
def test_real_interaction_reaches_the_evaluation_report(catalog, pack, renal, tmp_path, drugbank):
    svc = make_service(catalog, pack, renal, tmp_path, ddi=drugbank)
    report = evaluate_with(svc, "Tab Ciprofloxacin 500 mg BD x 3 days\nTab Metronidazole 400 mg TDS x 5 days")
    (item,) = [i for i in ddi_items(report) if i.outcome == "FLAG"]
    assert item.rule_id.startswith("DDI_INTERACTION:")
    assert item.evidence[0].source_id.startswith("drugbank:")
    assert "DrugBank reports an interaction" in item.message
    assert item.ddi.status is DDIStatus.INTERACTION_FOUND and item.ddi.severity == "unknown"
    # the engine's own rules still ran alongside the DDI check
    assert [i for i in report.items if i.rule_id.startswith("R")]
    assert report.status.value == "FLAGGED"


@requires_drugbank
def test_api_evaluate_reports_the_real_drugbank_interaction(catalog, pack, renal, tmp_path_factory):
    service = StewardshipService(
        catalog=catalog,
        rulepack=pack,
        renal=renal,
        audit=JsonlAuditLog(tmp_path_factory.mktemp("audit") / "audit.jsonl"),
        ddi=DrugBankDDIProvider(),
        clock=lambda: T0,
    )
    client = TestClient(create_app(service))
    response = client.post(
        "/api/evaluate",
        json={
            "patient": PATIENT,
            "setting": "OPD",
            "syndrome_code": "cystitis",
            "prescription": "Tab Ciprofloxacin 500 mg BD x 3 days\nTab Metronidazole 400 mg TDS x 5 days",
            "cultures": [],
        },
    )
    assert response.status_code == 200, response.text
    report = response.json()
    (item,) = [i for i in report["items"] if i["rule_id"].startswith("DDI_INTERACTION:")]
    assert item["outcome"] == "FLAG" and item["severity"] == "MODERATE"
    assert "pharmacist" in item["action"]
    assert item["evidence"][0]["source_id"].startswith("drugbank:")
    assert item["guideline_passages"] == []
    assert item["ddi"]["status"] == "INTERACTION_FOUND"
    assert item["ddi"]["source"] == "DrugBank" and item["ddi"]["severity"] == "unknown"
    assert report["status"] == "FLAGGED"
