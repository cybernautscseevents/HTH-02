from backend.stewardship.rules import (
    RuleContext,
    check_allergy,
    check_aware,
    check_dose,
    check_duration,
    check_identified,
    check_indication,
)
from backend.stewardship.schemas import AllergyStatus, NormStatus, Outcome, Route, Severity

from .fakes import T0, FakeCatalog, FakeRenal, FakeRulePack, episode, order, patient


def ctx(ep=None) -> RuleContext:
    return RuleContext.build(
        episode=ep or episode(),
        rulepack=FakeRulePack(),
        catalog=FakeCatalog(),
        renal=FakeRenal(),
        now=T0,
    )


def test_identified_drug_passes():
    assert check_identified(ctx(), order()).outcome is Outcome.PASS


def test_ambiguous_drug_cannot_be_assessed_and_lists_candidates():
    o = order(generic=None, norm_status=NormStatus.AMBIGUOUS, norm_candidates=("a", "b"))
    f = check_identified(ctx(), o)
    assert (f.outcome, f.severity) == (Outcome.CANNOT_ASSESS, Severity.HIGH)
    assert f.suggestion.action == "confirm_drug"
    assert "a, b" in f.suggestion.detail


def test_first_line_drug_passes_indication():
    assert check_indication(ctx(), order()).outcome is Outcome.PASS


def test_alternative_drug_passes_with_note():
    f = check_indication(ctx(), order("ciprofloxacin"))
    assert (f.outcome, f.severity) == (Outcome.PASS, Severity.INFO)
    assert "nitrofurantoin" in f.message


def test_unlisted_drug_is_flagged_with_first_line_suggestion():
    f = check_indication(ctx(), order("meropenem"))
    assert f.outcome is Outcome.FLAG
    assert f.suggestion.drug == "nitrofurantoin"


def test_antibiotic_for_viral_syndrome_is_flagged_high():
    f = check_indication(ctx(episode(syndrome_code="viral_uri")), order("amoxicillin"))
    assert (f.outcome, f.severity) == (Outcome.FLAG, Severity.HIGH)
    assert f.suggestion.action == "stop"


def test_missing_syndrome_cannot_be_assessed():
    f = check_indication(ctx(episode(syndrome_code=None)), order())
    assert f.outcome is Outcome.CANNOT_ASSESS
    assert f.missing_inputs == ("syndrome",)


def test_reserve_drug_is_flagged_high():
    f = check_aware(ctx(), order("colistin"))
    assert (f.outcome, f.severity) == (Outcome.FLAG, Severity.HIGH)


def test_watch_drug_with_access_first_line_is_flagged():
    f = check_aware(ctx(), order("ciprofloxacin"))
    assert (f.outcome, f.severity) == (Outcome.FLAG, Severity.MODERATE)
    assert f.suggestion.drug == "nitrofurantoin"


def test_unclassified_drug_cannot_be_assessed():
    assert check_aware(ctx(), order("mystery-mycin")).outcome is Outcome.CANNOT_ASSESS


def test_dose_in_range_passes():
    assert check_dose(ctx(), order(dose_mg=100, freq_per_day=2)).outcome is Outcome.PASS


def test_missing_dose_cannot_be_assessed():
    f = check_dose(ctx(), order(dose_mg=None))
    assert f.outcome is Outcome.CANNOT_ASSESS
    assert "dose_mg" in f.missing_inputs


def test_child_dose_cannot_be_assessed():
    ep = episode(patient=patient(age_years=12))
    assert check_dose(ctx(ep), order()).outcome is Outcome.CANNOT_ASSESS


def test_dose_far_above_maximum_is_flagged_high():
    f = check_dose(ctx(), order(dose_mg=400, freq_per_day=2))  # 800 mg/day vs max 400
    assert (f.outcome, f.severity) == (Outcome.FLAG, Severity.HIGH)


def test_dose_below_minimum_is_flagged():
    f = check_dose(ctx(), order(dose_mg=50, freq_per_day=2))
    assert (f.outcome, f.severity) == (Outcome.FLAG, Severity.MODERATE)


def test_dose_for_route_without_regimen_cannot_be_assessed():
    assert check_dose(ctx(), order(route=Route.IV)).outcome is Outcome.CANNOT_ASSESS


def test_duration_too_long_is_flagged():
    f = check_duration(ctx(), order(duration_days=10))
    assert (f.outcome, f.suggestion.action) == (Outcome.FLAG, "adjust_duration")


def test_missing_duration_cannot_be_assessed():
    assert check_duration(ctx(), order(duration_days=None)).outcome is Outcome.CANNOT_ASSESS


def test_unknown_allergy_status_blocks_beta_lactam():
    ep = episode(patient=patient(allergy_status=AllergyStatus.UNKNOWN))
    f = check_allergy(ctx(ep), order("amoxicillin"))
    assert (f.outcome, f.severity) == (Outcome.CANNOT_ASSESS, Severity.MODERATE)


def test_penicillin_allergy_flags_amoxicillin():
    ep = episode(patient=patient(allergy_status=AllergyStatus.KNOWN, allergies=("penicillin",)))
    f = check_allergy(ctx(ep), order("amoxicillin"))
    assert (f.outcome, f.severity) == (Outcome.FLAG, Severity.HIGH)


def test_unrelated_allergy_passes():
    ep = episode(patient=patient(allergy_status=AllergyStatus.KNOWN, allergies=("sulfa",)))
    assert check_allergy(ctx(ep), order("amoxicillin")).outcome is Outcome.PASS
