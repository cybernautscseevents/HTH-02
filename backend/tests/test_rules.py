from backend.stewardship.rules import (
    RuleContext,
    check_allergy,
    check_aware,
    check_dose,
    check_drug_disease,
    check_duration,
    check_identified,
    check_indication,
    check_pregnancy,
)
from backend.stewardship.schemas import (
    AllergyStatus,
    Comorbidity,
    NormStatus,
    Outcome,
    Route,
    Severity,
    Sex,
)

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


def test_penicillin_allergy_suggests_first_non_beta_lactam_option():
    ep = episode(
        syndrome_code="pyelonephritis",
        patient=patient(allergy_status=AllergyStatus.KNOWN, allergies=("penicillin",)),
    )
    f = check_allergy(ctx(ep), order("ampicillin", route=Route.IV))
    assert (f.suggestion.action, f.suggestion.drug) == ("switch", "amikacin")


def test_cephalosporin_allergy_skips_every_beta_lactam_option():
    ep = episode(
        syndrome_code="pyelonephritis",
        patient=patient(allergy_status=AllergyStatus.KNOWN, allergies=("cephalosporin",)),
    )
    f = check_allergy(ctx(ep), order("ceftriaxone", route=Route.IV))
    assert f.suggestion.drug == "amikacin"


def test_drug_avoided_in_pregnancy_is_flagged_with_safer_option():
    ep = episode(syndrome_code="pyelonephritis", patient=patient(pregnant=True))
    f = check_pregnancy(ctx(ep), order("amikacin", route=Route.IV))
    assert (f.outcome, f.severity) == (Outcome.FLAG, Severity.HIGH)
    assert f.suggestion.drug == "ceftriaxone"  # gentamicin is an aminoglycoside too


def test_unrecorded_pregnancy_blocks_avoided_drug_for_woman_of_childbearing_age():
    f = check_pregnancy(ctx(), order("gentamicin"))
    assert (f.outcome, f.missing_inputs) == (Outcome.CANNOT_ASSESS, ("pregnant",))


def test_pregnancy_check_passes_when_not_applicable_or_not_pregnant():
    for p in (patient(sex=Sex.M), patient(age_years=70), patient(pregnant=False)):
        assert check_pregnancy(ctx(episode(patient=p)), order("gentamicin")).outcome is Outcome.PASS
    assert check_pregnancy(ctx(episode(patient=patient(pregnant=True))), order()).outcome is (
        Outcome.PASS
    )


def test_boxed_warning_for_patient_condition_is_flagged_high_with_safer_option():
    ep = episode(patient=patient(comorbidities=(Comorbidity.MYASTHENIA_GRAVIS,)))
    f = check_drug_disease(ctx(ep), order("ciprofloxacin"))
    assert (f.outcome, f.severity) == (Outcome.FLAG, Severity.HIGH)
    assert "myasthenia gravis" in f.message
    assert any(e.page == "Boxed Warning" and "MYASTHENIA" in e.quote for e in f.evidence)
    assert f.suggestion.drug == "nitrofurantoin"


def test_label_warning_for_patient_condition_is_flagged_moderate_with_quote():
    ep = episode(patient=patient(comorbidities=(Comorbidity.DIABETES, Comorbidity.G6PD_DEFICIENCY)))
    f = check_drug_disease(ctx(ep), order("nitrofurantoin"))
    assert (f.outcome, f.severity, f.suggestion) == (Outcome.FLAG, Severity.MODERATE, None)
    assert "diabetes" in f.message and "G6PD deficiency" in f.message
    assert all(e.quote and e.title.startswith("US FDA label") for e in f.evidence)


def test_drug_disease_check_passes_without_a_matching_caution():
    assert check_drug_disease(ctx(), order("ciprofloxacin")).outcome is Outcome.PASS
    ep = episode(patient=patient(comorbidities=(Comorbidity.AORTIC_ANEURYSM,)))
    assert check_drug_disease(ctx(ep), order("nitrofurantoin")).outcome is Outcome.PASS
