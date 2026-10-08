import pytest

from backend.stewardship.drugs import Catalog
from backend.stewardship.episode import evaluate_episode
from backend.stewardship.renal import RenalDosing, creatinine_clearance, load_renal_bands
from backend.stewardship.schemas import (
    CultureStatus,
    EvaluationStatus,
    NormStatus,
    Outcome,
    Route,
    Severity,
    Sex,
    Trigger,
)

from .fakes import T0, FakeRulePack, episode, isolate, order, patient, specimen


@pytest.fixture(scope="module")
def renal() -> RenalDosing:
    return RenalDosing.load()


def kidney(crcl_target: float):
    """A 60-year-old 72 kg man whose Cockcroft-Gault clearance is crcl_target mL/min."""
    return patient(age_years=60, sex=Sex.M, weight_kg=72.0, serum_creatinine_mg_dl=80 / crcl_target)


def sources(finding) -> set[str]:
    return {e.source_id for e in finding.evidence}


def test_cockcroft_gault():
    man = patient(age_years=60, sex=Sex.M, weight_kg=70.0, serum_creatinine_mg_dl=1.0)
    assert creatinine_clearance(man) == pytest.approx(77.78, abs=0.01)
    woman = patient(age_years=60, sex=Sex.F, weight_kg=70.0, serum_creatinine_mg_dl=1.0)
    assert creatinine_clearance(woman) == pytest.approx(77.78 * 0.85, abs=0.01)
    assert creatinine_clearance(patient(serum_creatinine_mg_dl=None)) is None


# --- Indian sources ---


def test_icmr_dose_cap_within_limit_passes(renal):
    pip_taz = order("piperacillin/tazobactam", route=Route.IV, dose_mg=2250, freq_per_day=4)
    f = renal.check(pip_taz, kidney(30))
    assert f.outcome is Outcome.PASS
    assert "icmr-tg-2019" in sources(f)


def test_icmr_dose_above_renal_limit_is_flagged(renal):
    pip_taz = order("piperacillin/tazobactam", route=Route.IV, dose_mg=4500, freq_per_day=4)
    f = renal.check(pip_taz, kidney(30))
    assert (f.outcome, f.severity) == (Outcome.FLAG, Severity.MODERATE)
    assert f.suggestion.action == "adjust_dose"


def test_icmr_not_recommended_is_flagged_high(renal):
    f = renal.check(order("amikacin", route=Route.IV, dose_mg=750, freq_per_day=1), kidney(20))
    assert (f.outcome, f.severity) == (Outcome.FLAG, Severity.HIGH)
    assert f.evidence[0].quote == "<30- Not recommended"


def test_regimen_change_without_a_cap_quotes_the_source(renal):
    f = renal.check(order("meropenem", route=Route.IV, dose_mg=1000, freq_per_day=3), kidney(30))
    assert f.outcome is Outcome.FLAG
    assert "26-50, 12 hourly" in f.suggestion.detail


def test_indian_prescribing_information_for_oral_amoxicillin_clavulanate(renal):
    f = renal.check(order("amoxicillin/clavulanic acid", dose_mg=625, freq_per_day=3), kidney(20))
    assert f.outcome is Outcome.FLAG
    assert "gsk-india:AUG-TAB/PI/IN/2025/01" in sources(f)


def test_drug_needing_no_adjustment_passes_without_kidney_data(renal):
    f = renal.check(order("ceftriaxone", route=Route.IV), patient(serum_creatinine_mg_dl=None))
    assert f.outcome is Outcome.PASS


# --- US fallback and nitrofurantoin ---


def test_us_fallback_is_labelled_as_fallback(renal):
    f = renal.check(order("ciprofloxacin", dose_mg=500, freq_per_day=2), kidney(25))
    assert (f.outcome, f.severity) == (Outcome.FLAG, Severity.MODERATE)
    assert "fallback" in f.evidence[0].title


def test_nitrofurantoin_contraindicated_below_45(renal):
    f = renal.check(order("nitrofurantoin"), kidney(40))
    assert (f.outcome, f.severity) == (Outcome.FLAG, Severity.HIGH)
    assert f.suggestion.action == "switch"
    assert {"mhra-dsu-2014-09-nitrofurantoin"} < sources(f)


def test_nitrofurantoin_conflicting_sources_go_to_pharmacist(renal):
    f = renal.check(order("nitrofurantoin"), kidney(50))
    assert (f.outcome, f.severity) == (Outcome.FLAG, Severity.MODERATE)
    assert f.suggestion.action == "provide_input"
    assert len(sources(f) - {"cockcroft-gault-1976"}) == 2


def test_nitrofurantoin_normal_kidney_function_passes(renal):
    assert renal.check(order("nitrofurantoin"), kidney(80)).outcome is Outcome.PASS


# --- CANNOT_ASSESS paths ---


def test_missing_creatinine_cannot_be_assessed(renal):
    f = renal.check(order("ciprofloxacin"), patient(serum_creatinine_mg_dl=None))
    assert f.outcome is Outcome.CANNOT_ASSESS
    assert f.missing_inputs == ("serum_creatinine_mg_dl",)


def test_unsupported_drug_cannot_be_assessed(renal):
    f = renal.check(order("linezolid"), kidney(25))
    assert (f.outcome, f.severity) == (Outcome.CANNOT_ASSESS, Severity.LOW)


def test_missing_route_cannot_be_assessed_when_dosing_differs_by_route(renal):
    f = renal.check(order("ciprofloxacin", route=None), kidney(25))
    assert f.outcome is Outcome.CANNOT_ASSESS
    assert f.missing_inputs == ("route",)


def test_clearance_outside_source_bands_cannot_be_assessed(renal):
    assert renal.check(order("ciprofloxacin"), kidney(3)).outcome is Outcome.CANNOT_ASSESS


def test_child_cannot_be_assessed(renal):
    f = renal.check(order("ciprofloxacin"), patient(age_years=12))
    assert f.outcome is Outcome.CANNOT_ASSESS


# --- Table integrity ---


def test_every_band_is_sourced_and_bands_do_not_overlap():
    for generic, bands in load_renal_bands().items():
        for routes in {b.routes for b in bands}:
            same_route = [b for b in bands if b.routes == routes]
            assert all(e.quote and e.source_id for b in same_route for e in b.evidence), generic
            ranges = sorted((b.crcl_low, b.crcl_high) for b in same_route)
            assert all(a[1] < b[0] for a, b in zip(ranges, ranges[1:], strict=False)), generic


def test_sources_are_not_mixed_except_documented_nitrofurantoin_conflict():
    for generic, bands in load_renal_bands().items():
        for routes in {b.routes for b in bands}:
            ids = {e.source_id for b in bands if b.routes == routes for e in b.evidence}
            assert len(ids) == 1 or generic == "nitrofurantoin", (generic, ids)


# --- End to end with the real Person 2 implementation ---


def test_evaluate_episode_with_real_catalog_and_renal_checker(renal):
    catalog = Catalog.load()
    norm = catalog.normalize("Tab Ciprofloxacin 500 mg BD x 3 days")
    assert norm.status is NormStatus.ACCEPTED
    cipro = order(
        norm.generic,
        raw_text="Tab Ciprofloxacin 500 mg BD x 3 days",
        norm_status=norm.status,
        dose_mg=500,
        freq_per_day=2,
        duration_days=3,
    )
    urine = specimen(status=CultureStatus.FINAL, isolates=(isolate("E. coli", ciprofloxacin="R"),))
    ep = episode(orders=(cipro,), specimens=(urine,), patient=kidney(25))

    result = evaluate_episode(
        ep,
        now=T0,
        trigger=Trigger.CULTURE_RESULT,
        rulepack=FakeRulePack(),
        catalog=catalog,
        renal=renal,
    )

    assert result.status is EvaluationStatus.FLAGGED
    by_rule = {f.rule_id: f.outcome for f in result.findings}
    assert by_rule["R0_IDENTIFIED"] is Outcome.PASS
    assert by_rule["R2_AWARE"] is Outcome.FLAG  # Watch drug, Access first-line exists
    assert by_rule["R4_RENAL"] is Outcome.FLAG
    assert by_rule["C3_BUG_DRUG_MISMATCH"] is Outcome.FLAG
    assert by_rule["C9_ORGANISM_UNKNOWN"] is Outcome.CANNOT_ASSESS  # "E. coli" abbreviated


def test_unreadable_brand_stops_at_identification(renal):
    catalog = Catalog.load()
    norm = catalog.normalize("Augmentn 625")
    unsure = order(
        None, raw_text="Augmentn 625", norm_status=norm.status, norm_candidates=norm.candidates
    )
    result = evaluate_episode(
        episode(orders=(unsure,)),
        now=T0,
        trigger=Trigger.NEW_PRESCRIPTION,
        rulepack=FakeRulePack(),
        catalog=catalog,
        renal=renal,
    )
    order_findings = [f for f in result.findings if f.order_id == unsure.id]
    assert [(f.rule_id, f.outcome) for f in order_findings] == [
        ("R0_IDENTIFIED", Outcome.CANNOT_ASSESS)
    ]


def test_child_cannot_be_assessed_even_for_drugs_without_adjustment(renal):
    f = renal.check(order("ceftriaxone", route=Route.IV), patient(age_years=5, weight_kg=18))
    assert f.outcome is Outcome.CANNOT_ASSESS
