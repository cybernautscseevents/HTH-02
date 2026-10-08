import pytest

from backend.stewardship.drugs import Catalog
from backend.stewardship.episode import evaluate_episode
from backend.stewardship.renal import RenalDosing, creatinine_clearance, load_renal_bands
from backend.stewardship.schemas import EvaluationStatus, Outcome, Route, Severity, Sex, Trigger

from .fakes import T0, FakeRulePack, episode, order, patient


@pytest.fixture(scope="module")
def renal() -> RenalDosing:
    return RenalDosing.load()


def kidney(crcl_target: float):
    """A 60-year-old 72 kg man whose Cockcroft-Gault clearance is crcl_target mL/min."""
    return patient(age_years=60, sex=Sex.M, weight_kg=72.0, serum_creatinine_mg_dl=80 / crcl_target)


def test_cockcroft_gault():
    man = patient(age_years=60, sex=Sex.M, weight_kg=70.0, serum_creatinine_mg_dl=1.0)
    assert creatinine_clearance(man) == pytest.approx(77.78, abs=0.01)
    woman = patient(age_years=60, sex=Sex.F, weight_kg=70.0, serum_creatinine_mg_dl=1.0)
    assert creatinine_clearance(woman) == pytest.approx(77.78 * 0.85, abs=0.01)
    assert creatinine_clearance(patient(serum_creatinine_mg_dl=None)) is None


def test_contraindicated_drug_is_flagged_high(renal):
    f = renal.check(order("nitrofurantoin"), kidney(40))
    assert (f.outcome, f.severity) == (Outcome.FLAG, Severity.HIGH)
    assert f.suggestion.action == "switch"
    assert f.evidence[0].quote


def test_dose_above_renal_limit_is_flagged(renal):
    f = renal.check(order("ciprofloxacin", dose_mg=500, freq_per_day=2), kidney(25))
    assert (f.outcome, f.severity) == (Outcome.FLAG, Severity.MODERATE)
    assert f.suggestion.action == "adjust_dose"


def test_reduced_dose_within_renal_limit_passes(renal):
    f = renal.check(order("ciprofloxacin", dose_mg=250, freq_per_day=2), kidney(25))
    assert f.outcome is Outcome.PASS


def test_normal_kidney_function_passes(renal):
    f = renal.check(order("ciprofloxacin", dose_mg=500, freq_per_day=2), kidney(90))
    assert f.outcome is Outcome.PASS


def test_regimen_change_without_a_cap_is_flagged_with_label_text(renal):
    f = renal.check(order("meropenem", route=Route.IV, dose_mg=1000, freq_per_day=3), kidney(30))
    assert f.outcome is Outcome.FLAG
    assert "Every 12 hours" in f.suggestion.detail


def test_drug_needing_no_adjustment_passes_without_kidney_data(renal):
    f = renal.check(order("ceftriaxone", route=Route.IV), patient(serum_creatinine_mg_dl=None))
    assert f.outcome is Outcome.PASS


def test_missing_creatinine_cannot_be_assessed(renal):
    f = renal.check(order("ciprofloxacin"), patient(serum_creatinine_mg_dl=None))
    assert f.outcome is Outcome.CANNOT_ASSESS
    assert f.missing_inputs == ("serum_creatinine_mg_dl",)


def test_drug_without_renal_data_cannot_be_assessed(renal):
    f = renal.check(order("linezolid"), kidney(25))
    assert (f.outcome, f.severity) == (Outcome.CANNOT_ASSESS, Severity.LOW)


def test_route_without_renal_data_cannot_be_assessed(renal):
    f = renal.check(order("ciprofloxacin", route=Route.IV), kidney(25))
    assert f.outcome is Outcome.CANNOT_ASSESS


def test_clearance_outside_label_bands_cannot_be_assessed(renal):
    f = renal.check(order("ciprofloxacin"), kidney(3))
    assert f.outcome is Outcome.CANNOT_ASSESS


def test_child_cannot_be_assessed(renal):
    f = renal.check(order("ciprofloxacin"), patient(age_years=12))
    assert f.outcome is Outcome.CANNOT_ASSESS


def test_every_band_is_sourced_and_bands_do_not_overlap():
    for generic, bands in load_renal_bands().items():
        assert all(b.evidence.quote and b.evidence.source_id for b in bands), generic
        assert all(b.action in {"none", "adjust", "avoid"} for b in bands), generic
        ranges = sorted((b.crcl_low, b.crcl_high) for b in bands)
        assert all(a[1] < b[0] for a, b in zip(ranges, ranges[1:], strict=False)), generic


def test_real_catalog_and_renal_checker_plug_into_the_engine(renal):
    ep = episode(
        orders=(order("ciprofloxacin", dose_mg=500, freq_per_day=2, duration_days=3),),
        patient=kidney(25),
    )
    result = evaluate_episode(
        ep,
        now=T0,
        trigger=Trigger.NEW_PRESCRIPTION,
        rulepack=FakeRulePack(),
        catalog=Catalog.load(),
        renal=renal,
    )
    assert result.status is EvaluationStatus.FLAGGED
    by_rule = {f.rule_id: f.outcome for f in result.findings}
    assert by_rule["R4_RENAL"] is Outcome.FLAG
    assert by_rule["R2_AWARE"] is Outcome.FLAG
