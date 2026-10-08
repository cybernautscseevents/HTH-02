"""NCDC dataset import: conversion rules, the merged rule pack, and safety end to end.

The engine (R0-R6, culture rules) is unchanged; these tests check that the imported data only adds
syndromes, never replaces or weakens a hand-checked one, and that intake + engine stay safe on
the inputs that broke the other branch's rule engine.
"""

import subprocess
import sys
from datetime import UTC, datetime

import pytest

from backend.stewardship import config
from backend.stewardship.drugs import Catalog
from backend.stewardship.episode import evaluate_episode
from backend.stewardship.intake import (
    EpisodeRequest,
    IntakeError,
    build_episode,
    resolve_syndrome,
    syndrome_from_text,
)
from backend.stewardship.ncdc_import import (
    ImportResult,
    ManifestError,
    convert,
    daily_dose_mg,
    duration_days,
    load_yaml,
)
from backend.stewardship.renal import RenalDosing
from backend.stewardship.rulepack import RulePackError, YamlRulePack
from backend.stewardship.schemas import EvaluationStatus, Outcome, Route, Severity, Trigger

from .fakes import episode, order, patient

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.load()


@pytest.fixture(scope="module")
def pack() -> YamlRulePack:
    return YamlRulePack()


@pytest.fixture(scope="module")
def hand_only() -> YamlRulePack:
    return YamlRulePack(imported=None)


@pytest.fixture(scope="module")
def source() -> dict:
    return load_yaml(config.NCDC_DATASET_YAML)


@pytest.fixture(scope="module")
def result(source, catalog) -> ImportResult:
    return convert(
        source,
        load_yaml(config.NCDC_MANIFEST_YAML),
        load_yaml(config.SYNDROMES_YAML),
        catalog,
    )


def run(pack, catalog, prescription: str, syndrome: str | None = "cystitis", **request):
    """Typed prescription -> intake -> evaluate_episode, exactly as the API does it."""
    req = EpisodeRequest(
        patient=patient(), syndrome_code=syndrome, prescription=prescription, **request
    )
    episode, readings, _, _ = build_episode(
        req, episode_id="e1", catalog=catalog, codes=pack.codes(), now=NOW
    )
    evaluation = evaluate_episode(
        episode,
        now=NOW,
        trigger=Trigger.NEW_PRESCRIPTION,
        rulepack=pack,
        catalog=catalog,
        renal=RenalDosing.load(),
    )
    findings = {(f.rule_id, f.order_id): f for f in evaluation.findings}
    return evaluation, findings, readings


# --- regressions: inputs the other branch's engine got wrong ------------------------------


def test_microgram_dose_is_not_read_as_milligrams(pack, catalog):
    _, f, readings = run(pack, catalog, "Tab Nitrofurantoin 100 mcg BD PO x 5 days")
    assert readings[0].order.dose_mg is None
    assert f[("R3_DOSE", "rx-1")].outcome is Outcome.CANNOT_ASSESS
    assert "dose_mg" in f[("R3_DOSE", "rx-1")].missing_inputs


def test_dose_without_unit_does_not_pass(pack, catalog):
    _, f, readings = run(pack, catalog, "Tab Nitrofurantoin 100 BD PO x 5 days")
    assert readings[0].order.dose_mg is None
    assert f[("R3_DOSE", "rx-1")].outcome is Outcome.CANNOT_ASSESS


def test_lower_case_bd_and_po_are_read_correctly(pack, catalog):
    _, f, readings = run(pack, catalog, "tab nitrofurantoin 100 mg bd po x 5 days")
    o = readings[0].order
    assert (o.dose_mg, o.freq_per_day, o.route) == (100.0, 2.0, Route.PO)
    for rule in ("R1_INDICATION", "R3_DOSE", "R5_DURATION"):
        assert f[(rule, "rx-1")].outcome is Outcome.PASS


def test_million_units_dose_is_kept_as_written_and_never_compared_as_mg(pack, catalog):
    regimen = next(
        r for r in pack.syndrome("tetanus").first_line if r.generic == "benzylpenicillin"
    )
    assert regimen.daily_dose_mg_min is None and regimen.daily_dose_mg_max is None
    assert "2-4 million units" in regimen.evidence.quote
    _, f, readings = run(
        pack, catalog, "Inj Penicillin G 4 million units IV q4h x 7 days", syndrome="tetanus"
    )
    assert readings[0].order.dose_mg is None
    assert f[("R1_INDICATION", "rx-1")].outcome is Outcome.PASS
    assert f[("R3_DOSE", "rx-1")].outcome is Outcome.CANNOT_ASSESS


def test_drug_name_alone_never_passes(pack, catalog):
    evaluation, f, _ = run(pack, catalog, "Nitrofurantoin")
    assert evaluation.status is not EvaluationStatus.OK
    for rule in ("R3_DOSE", "R5_DURATION"):
        assert f[(rule, "rx-1")].outcome is Outcome.CANNOT_ASSESS


@pytest.mark.parametrize("text", ["uti", "catheter associated uti", "cauti", "pneumonia"])
def test_free_text_never_substring_matches_a_syndrome(text):
    assert syndrome_from_text(text) is None


def test_imported_syndromes_need_an_exact_code(pack):
    assert resolve_syndrome("cauti_severely_ill", None, pack.codes()) == (
        "cauti_severely_ill",
        "selected",
    )
    with pytest.raises(IntakeError):
        resolve_syndrome("cauti", None, pack.codes())


# --- the hand-checked pack is untouched ---------------------------------------------------


def test_hand_checked_syndromes_are_identical_with_and_without_import(pack, hand_only):
    assert len(hand_only.codes()) == 13
    for code in hand_only.codes():
        assert pack.syndrome(code) == hand_only.syndrome(code), code


def test_import_only_adds_codes(pack, hand_only, result):
    imported = {s["code"] for s in result.syndromes}
    assert not imported & set(hand_only.codes())
    assert set(pack.codes()) == set(hand_only.codes()) | imported


def test_a_code_in_both_files_is_rejected(tmp_path):
    text = config.NCDC_SYNDROMES_YAML.read_text().replace(
        "code: meningitis_empiric", "code: cystitis", 1
    )
    path = tmp_path / "clash.yaml"
    path.write_text(text)
    with pytest.raises(RulePackError, match="duplicate"):
        YamlRulePack(imported=path)


def test_overlapping_sections_were_all_compared(result):
    assert sorted(result.compared) == sorted(YamlRulePack(imported=None).codes())


def test_every_difference_from_the_hand_checked_pack_is_known(result):
    """Doses and durations of every overlapping row agree. The differences below are the
    complete list; the hand-checked row is kept for each. A new difference fails this test."""
    found = {(c.code, c.generic, c.route, c.field) for c in result.conflicts}
    assert found == {
        # Hand-checked pack leaves amikacin's duration out on purpose (see syndromes.yaml).
        ("pyelonephritis", "amikacin", "IV", "duration_days"),
        # Roles read differently from the same table.
        ("cellulitis_moderate_severe", "amoxicillin/clavulanic acid", "IV", "role"),
        ("cap_ward", "doxycycline", "PO", "role"),
        # Dataset reads the partner as "PO/IV"; the hand-checked pack encodes the oral route only.
        ("cap_ward", "azithromycin", "IV", "listed"),
        ("cap_ward", "doxycycline", "IV", "listed"),
        ("cap_icu", "azithromycin", "IV", "listed"),
        ("cap_icu", "doxycycline", "IV", "listed"),
        # Dataset places piperacillin-tazobactam in the ICU Pseudomonas-risk sub-group (imported as
        # cap_icu_pseudomonas_risk); the hand-checked cap_icu keeps it. Needs a check of p. 83.
        ("cap_icu", "piperacillin/tazobactam", "IV", "listed"),
    }
    assert not any(c.field == "daily_dose_mg" for c in result.conflicts)


def test_hand_checked_row_wins_on_conflict(pack):
    cap_icu = pack.syndrome("cap_icu")
    assert any(r.generic == "piperacillin/tazobactam" for r in cap_icu.alternatives)
    assert not any(r.route is Route.IV and r.generic == "azithromycin" for r in cap_icu.first_line)
    assert pack.syndrome("pyelonephritis").evidence.source_id == "ncdc-ntg-2025"


# --- conversion rules ----------------------------------------------------------------------


def _agent(dose: dict, freq: dict | None = None, dur: dict | None = None) -> dict:
    return {
        "dose_structured": {"per_kg": False, "per_day": False, "max_dose": None} | dose,
        "frequency_structured": freq or {"parse_status": "scalar", "doses_per_day": 2},
        "duration_structured": dur or {"parse_status": "scalar", "min_days": 5, "max_days": 5},
    }


REGIMEN = {
    "executable": True,
    "dose_checkable": True,
    "frequency_checkable": True,
    "duration_checkable": True,
}


@pytest.mark.parametrize(
    ("dose", "freq", "expected"),
    [
        ({"parse_status": "scalar", "min": 100, "max": 100, "unit": "mg"}, None, [200, 200]),
        ({"parse_status": "scalar", "min": 2, "max": 2, "unit": "g"}, None, [4000, 4000]),
        ({"parse_status": "scalar", "min": 500, "max": 500, "unit": "mcg"}, None, [1, 1]),
        (
            {"parse_status": "range", "min": 1, "max": 2, "unit": "g"},
            {"parse_status": "range", "doses_per_day": {"min": 3, "max": 4}},
            [3000, 8000],
        ),
        (
            {"parse_status": "scalar", "min": 3, "max": 3, "unit": "g"},
            {"parse_status": "single", "doses_per_day": 1},
            [3000, 3000],
        ),
    ],
)
def test_exact_doses_convert_to_mg_per_day(dose, freq, expected):
    assert daily_dose_mg(_agent(dose, freq), REGIMEN) == (expected, None)


@pytest.mark.parametrize(
    "dose",
    [
        {
            "parse_status": "scalar",
            "min": 4e6,
            "max": 4e6,
            "unit": "units",
            "raw": "4 million units",
        },
        {"parse_status": "scalar_weight_based", "min": 15, "max": 15, "unit": "mg", "per_kg": True},
        {"parse_status": "scalar", "min": 15, "max": 15, "unit": "mg", "per_kg": True},
        {"parse_status": "ratio", "min": None, "max": None, "unit": "mg", "raw": "800/160 mg"},
        {"parse_status": "composite", "min": None, "max": None, "unit": None},
        {"parse_status": "route_dependent", "min": None, "max": None, "unit": None},
        {"parse_status": "scalar", "min": None, "max": None, "unit": None},
    ],
)
def test_inexact_doses_are_not_converted(dose):
    value, reason = daily_dose_mg(_agent(dose), REGIMEN)
    assert value is None and reason


def test_unfixed_frequency_or_non_executable_regimen_gives_no_dose():
    dose = {"parse_status": "scalar", "min": 1, "max": 1, "unit": "g"}
    assert daily_dose_mg(_agent(dose, {"parse_status": "sequence"}), REGIMEN)[0] is None
    assert daily_dose_mg(_agent(dose), REGIMEN | {"executable": False})[0] is None


@pytest.mark.parametrize(
    ("dur", "expected"),
    [
        ({"parse_status": "range", "min_days": 7, "max_days": 10}, [7, 10]),
        ({"parse_status": "single", "min_days": 0, "max_days": 0}, None),
        ({"parse_status": "phase", "min_days": 14, "max_days": 14}, None),
        ({"parse_status": "scalar", "min_days": 1.5, "max_days": 1.5}, None),
        ({"parse_status": "missing"}, None),
    ],
)
def test_duration_converts_only_whole_day_ranges(dur, expected):
    dose = {"parse_status": "scalar", "min": 1, "max": 1, "unit": "g"}
    assert duration_days(_agent(dose, dur=dur), REGIMEN)[0] == expected


def test_weight_based_rows_keep_the_drug_but_no_dose(pack):
    amikacin = next(r for r in pack.syndrome("cauti_not_severely_ill").alternatives)
    assert amikacin.generic == "amikacin"
    assert amikacin.daily_dose_mg_min is None and "15 mg/kg" in amikacin.evidence.quote


def test_same_drug_twice_with_different_values_is_not_checked(result):
    unstable = next(s for s in result.syndromes if s["code"] == "deep_neck_abscess_unstable")
    meropenem = next(r for r in unstable["regimens"] if r["generic"] == "meropenem")
    assert meropenem["daily_dose_mg"] is None
    assert any(n.drug == "meropenem" and n.ref == "7.6" for n in result.merged)


def test_manifest_cannot_import_a_non_treatment_row(source, catalog):
    manifest = {"syndromes": [{"code": "x", "name": "x", "ncdc": "2.3", "regimens": ["LISTERIA"]}]}
    with pytest.raises(ManifestError, match="add_on"):
        convert(source, manifest, {"syndromes": []}, catalog)


def test_manifest_cannot_invent_a_culture_requirement(source, catalog):
    manifest = {
        "syndromes": [
            {
                "code": "x",
                "name": "x",
                "ncdc": "2.3",
                "regimens": ["FL-1"],
                "culture_basis": "Do it.",
            }
        ]
    }
    with pytest.raises(ManifestError, match="culture_basis"):
        convert(source, manifest, {"syndromes": []}, catalog)


# --- provenance and accounting -------------------------------------------------------------


def test_every_imported_row_names_its_guideline_section_page_and_dataset_row(pack, result):
    for s in result.syndromes:
        rule = pack.syndrome(s["code"])
        assert rule.evidence.source_id == "ncdc-ntg-2025"
        assert s["source"]["section"] in rule.evidence.title and rule.evidence.page
        for r in (*rule.first_line, *rule.alternatives):
            assert r.evidence.page == rule.evidence.page
            assert r.evidence.quote.startswith(f"NCDC dataset {s['ncdc']}/")


def test_every_dataset_row_is_imported_compared_or_reported(source, result):
    manifest = load_yaml(config.NCDC_MANIFEST_YAML)["syndromes"]
    used = {
        f"{e['ncdc']}/{i}"
        for e in manifest
        for i in [*e.get("regimens", []), *([e["no_antibiotic"]] if "no_antibiotic" in e else [])]
    }
    reported = {n.ref for n in result.unassigned}
    for section in source["syndromes"]:
        for regimen in section["regimens"]:
            assert (regimen["key"] in used) != (regimen["key"] in reported), regimen["key"]


def test_unmappable_drugs_are_reported(result):
    skipped = {(n.ref, n.drug) for n in result.skipped_agents}
    assert ("4.5/COMP-2", "cefoperazone-sulbactam") in skipped
    assert ("1.4/FL-1", "benzathine penicillin G") in skipped
    reasons = {n.ref: n.reason for n in result.unassigned}
    assert "source error" in reasons["13.4/ALT-1"]


def test_generated_files_are_up_to_date():
    done = subprocess.run(
        [sys.executable, "scripts/import_ncdc.py", "--check"],
        cwd=config.REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stdout + done.stderr


# --- imported syndromes through the real engine -------------------------------------------


def test_imported_syndrome_concordant_prescription_passes(pack, catalog):
    _, f, _ = run(
        pack, catalog, "Inj Ceftriaxone 2 g IV BD x 10 days", syndrome="meningitis_empiric"
    )
    for rule in ("R1_INDICATION", "R3_DOSE", "R5_DURATION"):
        assert f[(rule, "rx-1")].outcome is Outcome.PASS, f[(rule, "rx-1")].message
        assert f[(rule, "rx-1")].evidence[0].page == "p. 20"


def test_imported_syndrome_underdose_is_flagged(pack, catalog):
    _, f, _ = run(
        pack, catalog, "Inj Ceftriaxone 1 g IV OD x 10 days", syndrome="meningitis_empiric"
    )
    assert f[("R3_DOSE", "rx-1")].outcome is Outcome.FLAG
    assert "below" in f[("R3_DOSE", "rx-1")].message


def test_imported_no_antibiotic_syndrome_flags_any_antibiotic(pack, catalog):
    _, f, _ = run(
        pack, catalog, "Cap Amoxicillin 500 mg TDS PO x 5 days", syndrome="viral_rhinitis"
    )
    indication = f[("R1_INDICATION", "rx-1")]
    assert indication.outcome is Outcome.FLAG and indication.severity is Severity.HIGH


def test_imported_drug_not_in_table_is_flagged(pack, catalog):
    _, f, _ = run(
        pack, catalog, "Inj Meropenem 1 g IV TDS x 7 days", syndrome="cholecystitis_no_sepsis"
    )
    assert f[("R1_INDICATION", "rx-1")].outcome is Outcome.FLAG
    assert f[("R1_INDICATION", "rx-1")].suggestion.drug == "amoxicillin/clavulanic acid"


def test_imported_culture_requirement_drives_the_culture_rule(pack, catalog):
    assert pack.syndrome("clabsi_stable").culture_required
    assert not pack.syndrome("meningitis_empiric").culture_required
    _, f, _ = run(pack, catalog, "Inj Meropenem 1 g IV TDS x 7 days", syndrome="clabsi_stable")
    culture = [x for (rule, _), x in f.items() if rule.startswith("C1")]
    assert culture and culture[0].outcome is Outcome.FLAG


def test_every_imported_regimen_passes_its_own_guideline_values(pack, catalog, result):
    """An order exactly at each imported regimen's minimum daily dose and duration passes R1, R3
    and R5 for that syndrome: the converted numbers are the ones the rules compare."""
    checked = 0
    for s in result.syndromes:
        for r in s["regimens"]:
            if r["daily_dose_mg"] is None and r["duration_days"] is None:
                continue
            o = order(
                r["generic"],
                id="o",
                route=Route(r["route"]),
                dose_mg=r["daily_dose_mg"][0] if r["daily_dose_mg"] else None,
                freq_per_day=1.0,
                duration_days=r["duration_days"][0] if r["duration_days"] else None,
            )
            evaluation = evaluate_episode(
                episode(orders=(o,), syndrome_code=s["code"]),
                now=NOW,
                trigger=Trigger.NEW_PRESCRIPTION,
                rulepack=pack,
                catalog=catalog,
                renal=RenalDosing.load(),
            )
            f = {x.rule_id: x for x in evaluation.findings if x.order_id == "o"}
            assert f["R1_INDICATION"].outcome is Outcome.PASS, (s["code"], r["generic"])
            if r["daily_dose_mg"]:
                assert f["R3_DOSE"].outcome is Outcome.PASS, (s["code"], r["generic"])
            if r["duration_days"]:
                assert f["R5_DURATION"].outcome is Outcome.PASS, (s["code"], r["generic"])
            checked += 1
    assert checked > 150
