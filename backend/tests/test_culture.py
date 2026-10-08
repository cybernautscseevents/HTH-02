from datetime import timedelta

from backend.stewardship.culture import (
    check_bug_drug_mismatch,
    check_contaminants,
    check_culture_sent,
    check_de_escalation,
    check_intermediate,
    check_no_growth,
    check_not_tested,
)
from backend.stewardship.rules import RuleContext
from backend.stewardship.schemas import CultureStatus, Outcome, Route, Setting, Severity

from .fakes import T0, FakeCatalog, FakeRenal, FakeRulePack, episode, isolate, order, specimen


def pyelo(*specimens, drug="ceftriaxone") -> object:
    return episode(
        syndrome_code="pyelonephritis",
        setting=Setting.WARD,
        orders=(order(drug, route=Route.IV, dose_mg=1000, freq_per_day=1),),
        specimens=specimens,
    )


def ctx(ep, now=T0, catalog=None) -> RuleContext:
    return RuleContext.build(
        episode=ep,
        rulepack=FakeRulePack(),
        catalog=catalog or FakeCatalog(),
        renal=FakeRenal(),
        now=now,
    )


def test_watch_drug_without_culture_is_flagged_when_culture_required():
    (f,) = check_culture_sent(ctx(pyelo()))
    assert (f.outcome, f.suggestion.action) == (Outcome.FLAG, "send_culture")


def test_pending_culture_satisfies_culture_rule():
    assert check_culture_sent(ctx(pyelo(specimen(status=CultureStatus.PENDING)))) == ()


def test_resistant_result_is_flagged_high():
    ep = pyelo(specimen(isolates=(isolate(ceftriaxone="R"),)))
    (f,) = check_bug_drug_mismatch(ctx(ep))
    assert (f.outcome, f.severity) == (Outcome.FLAG, Severity.HIGH)


def test_intrinsic_resistance_is_flagged_without_a_lab_result():
    catalog = FakeCatalog(intrinsic={("klebsiella pneumoniae", "ceftriaxone")})
    ep = pyelo(specimen(isolates=(isolate("klebsiella pneumoniae"),)))
    (f,) = check_bug_drug_mismatch(ctx(ep, catalog=catalog))
    assert f.severity is Severity.HIGH
    assert check_not_tested(ctx(ep, catalog=catalog)) == ()


def test_de_escalation_suggests_narrowest_access_option():
    ep = pyelo(specimen(isolates=(isolate(ceftriaxone="S", amikacin="S", gentamicin="S"),)))
    (f,) = check_de_escalation(ctx(ep))
    assert (f.suggestion.action, f.suggestion.drug) == ("switch", "amikacin")


def test_de_escalation_skips_options_the_organism_resists():
    ep = pyelo(specimen(isolates=(isolate(ceftriaxone="S", amikacin="R", gentamicin="S"),)))
    (f,) = check_de_escalation(ctx(ep))
    assert f.suggestion.drug == "gentamicin"


def test_contaminant_is_flagged_and_ignored_for_de_escalation():
    contaminant = isolate("staphylococcus epidermidis", contaminant=True, amikacin="R")
    ep = pyelo(specimen(isolates=(isolate(amikacin="S"), contaminant)))
    (f,) = check_contaminants(ctx(ep))
    assert f.severity is Severity.LOW
    assert check_de_escalation(ctx(ep))[0].suggestion.drug == "amikacin"


def test_no_growth_after_timeout_asks_clinician_and_never_stops():
    ep = pyelo(specimen(status=CultureStatus.NO_GROWTH))
    (f,) = check_no_growth(ctx(ep, now=T0 + timedelta(hours=49)))
    assert f.suggestion.action == "provide_input"


def test_no_growth_before_timeout_is_silent():
    ep = pyelo(specimen(status=CultureStatus.NO_GROWTH))
    assert check_no_growth(ctx(ep, now=T0 + timedelta(hours=24))) == ()


def test_intermediate_result_is_flagged():
    ep = pyelo(specimen(isolates=(isolate(ceftriaxone="I"),)))
    (f,) = check_intermediate(ctx(ep))
    assert (f.outcome, f.severity) == (Outcome.FLAG, Severity.MODERATE)


def test_untested_drug_cannot_be_assessed():
    ep = pyelo(specimen(isolates=(isolate(amikacin="S"),)))
    (f,) = check_not_tested(ctx(ep))
    assert f.outcome is Outcome.CANNOT_ASSESS


def test_pending_culture_produces_no_susceptibility_findings():
    ep = pyelo(specimen(status=CultureStatus.PENDING))
    assert check_bug_drug_mismatch(ctx(ep)) == check_not_tested(ctx(ep)) == ()
