"""The real guideline rule pack (NCDC 2025) driving R1, R3 and R5, alone and end to end."""

from pathlib import Path

import pytest

from backend.stewardship import config
from backend.stewardship.drugs import Catalog
from backend.stewardship.episode import evaluate_episode
from backend.stewardship.renal import RenalDosing
from backend.stewardship.rulepack import RulePackError, YamlRulePack
from backend.stewardship.rules import RuleContext, check_dose, check_duration, check_indication
from backend.stewardship.schemas import EvaluationStatus, Outcome, Route, Trigger

from .fakes import T0, FakeCatalog, FakeRenal, episode, order, patient


@pytest.fixture(scope="module")
def pack() -> YamlRulePack:
    return YamlRulePack()


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.load()


def run(rule, pack, o, **ep):
    ctx = RuleContext.build(
        episode=episode(orders=(o,), **ep),
        rulepack=pack,
        catalog=FakeCatalog(),
        renal=FakeRenal(),
        now=T0,
    )
    return rule(ctx, o)


# --- R1 indication ---


def test_first_line_drug_passes(pack):
    f = run(check_indication, pack, order("nitrofurantoin"))
    assert f.outcome is Outcome.PASS


def test_alternative_drug_passes(pack):
    f = run(check_indication, pack, order("sulfamethoxazole/trimethoprim"))
    assert f.outcome is Outcome.PASS and "alternative" in f.message


def test_non_listed_drug_is_flagged_with_first_line_suggestion(pack):
    f = run(check_indication, pack, order("ciprofloxacin"))
    assert f.outcome is Outcome.FLAG
    assert f.suggestion.drug == "nitrofurantoin"


def test_unknown_syndrome_cannot_be_assessed(pack):
    f = run(check_indication, pack, order(), syndrome_code="otitis_externa")
    assert f.outcome is Outcome.CANNOT_ASSESS
    assert f.missing_inputs == ("syndrome",)


def test_antibiotic_for_no_antibiotic_syndrome_is_flagged_high(pack):
    f = run(check_indication, pack, order("amoxicillin"), syndrome_code="acute_bronchitis")
    assert f.outcome is Outcome.FLAG and f.severity == "HIGH"
    assert f.evidence[0].page == "p. 81"


# --- R3 dose ---


def test_correct_dose_passes(pack):
    assert run(check_dose, pack, order(dose_mg=100, freq_per_day=2)).outcome is Outcome.PASS


def test_excessive_dose_is_flagged(pack):
    f = run(check_dose, pack, order(dose_mg=200, freq_per_day=2))
    assert f.outcome is Outcome.FLAG and "exceeds" in f.message


def test_double_dose_beyond_factor_is_high(pack):
    f = run(check_dose, pack, order(dose_mg=300, freq_per_day=2))
    assert f.severity == "HIGH"


def test_insufficient_dose_is_flagged(pack):
    f = run(check_dose, pack, order(dose_mg=50, freq_per_day=2))
    assert f.outcome is Outcome.FLAG and "below" in f.message


def test_dose_range_uses_daily_total_not_single_dose(pack):
    ep = dict(syndrome_code="cap_opd_no_comorbidity")
    # amoxicillin 1 g q8h = 3000 mg/day
    assert run(
        check_dose, pack, order("amoxicillin", dose_mg=1000, freq_per_day=3), **ep
    ).outcome is (Outcome.PASS)
    assert run(
        check_dose, pack, order("amoxicillin", dose_mg=500, freq_per_day=3), **ep
    ).outcome is (Outcome.FLAG)


def test_weight_based_guideline_dose_cannot_be_assessed(pack):
    o = order("amikacin", route=Route.IV, dose_mg=1000, freq_per_day=1)
    f = run(check_dose, pack, o, syndrome_code="pyelonephritis")
    assert f.outcome is Outcome.CANNOT_ASSESS and "weight-based" in f.message


def test_child_dose_is_not_checked_against_adult_data(pack):
    f = run(check_dose, pack, order(), patient=patient(age_years=10))
    assert f.outcome is Outcome.CANNOT_ASSESS


# --- R5 duration ---


def test_correct_duration_passes(pack):
    assert run(check_duration, pack, order(duration_days=5)).outcome is Outcome.PASS


def test_excessive_duration_is_flagged(pack):
    f = run(check_duration, pack, order(duration_days=10))
    assert f.outcome is Outcome.FLAG and f.severity == "MODERATE"


def test_short_duration_is_flagged_low(pack):
    f = run(
        check_duration,
        pack,
        order("amoxicillin", duration_days=3),
        syndrome_code="cap_opd_no_comorbidity",
    )
    assert f.outcome is Outcome.FLAG and f.severity == "LOW"


def test_missing_duration_cannot_be_assessed(pack):
    assert run(check_duration, pack, order(duration_days=None)).outcome is Outcome.CANNOT_ASSESS


def test_guideline_without_duration_for_drug_cannot_be_assessed(pack):
    o = order("amikacin", route=Route.IV, duration_days=7)
    f = run(check_duration, pack, o, syndrome_code="pyelonephritis")
    assert f.outcome is Outcome.CANNOT_ASSESS


# --- Route, unsupported drug ---


@pytest.mark.parametrize("rule", [check_dose, check_duration])
def test_wrong_route_cannot_be_assessed(pack, rule):
    assert run(rule, pack, order(route=Route.IV)).outcome is Outcome.CANNOT_ASSESS


@pytest.mark.parametrize("rule", [check_dose, check_duration])
def test_missing_route_cannot_be_assessed(pack, rule):
    f = run(rule, pack, order(route=None))
    assert f.outcome is Outcome.CANNOT_ASSESS and f.missing_inputs == ("route",)


@pytest.mark.parametrize("rule", [check_dose, check_duration])
def test_unsupported_drug_cannot_be_assessed(pack, rule):
    assert run(rule, pack, order("ciprofloxacin")).outcome is Outcome.CANNOT_ASSESS


def test_route_selects_the_regimen(pack):
    """Ertapenem is listed for IV and IM; an oral order matches neither."""
    ep = dict(syndrome_code="pyelonephritis")
    kw = dict(dose_mg=1000, freq_per_day=1, duration_days=7)
    for route in (Route.IV, Route.IM):
        assert run(check_dose, pack, order("ertapenem", route=route, **kw), **ep).outcome is (
            Outcome.PASS
        )
    assert run(check_dose, pack, order("ertapenem", route=Route.PO, **kw), **ep).outcome is (
        Outcome.CANNOT_ASSESS
    )


# --- Source traceability ---


def test_findings_carry_guideline_source_and_page(pack):
    for rule in (check_indication, check_dose, check_duration):
        (ev,) = run(rule, pack, order()).evidence
        assert ev.source_id == "ncdc-ntg-2025"
        assert "5.1 Cystitis" in ev.title
        assert ev.page == "p. 39"
        assert "Nitrofurantoin 100 mg q12h for 5 days" in ev.quote


def test_inferred_route_is_disclosed_in_evidence(pack):
    (ev,) = run(check_dose, pack, order()).evidence
    assert "route not printed" in ev.quote


# --- Pack integrity ---


def test_every_regimen_has_source_and_known_antibiotic(pack, catalog):
    for code in pack.codes():
        syndrome = pack.syndrome(code)
        assert syndrome.evidence.page
        for r in (*syndrome.first_line, *syndrome.alternatives):
            assert catalog.is_antibiotic(r.generic), f"{code}: {r.generic}"
            assert r.evidence.page and r.evidence.quote


def test_version_is_stable_and_names_the_guideline(pack):
    assert YamlRulePack().version == pack.version
    assert pack.version.startswith("ncdc-ntg-2025:")


def test_duplicate_drug_route_is_rejected(tmp_path: Path):
    text = config.SYNDROMES_YAML.read_text()
    marker = "      - {role: alternative, generic: sulfamethoxazole/trimethoprim, route: PO"
    assert marker in text
    bad = text.replace(marker, marker.replace("sulfamethoxazole/trimethoprim", "nitrofurantoin"), 1)
    path = tmp_path / "bad.yaml"
    path.write_text(bad)
    with pytest.raises(RulePackError, match="twice"):
        YamlRulePack(path)


# --- End to end through evaluate_episode with the real pack ---


def evaluate(pack, catalog, orders, **ep):
    return evaluate_episode(
        episode(orders=orders, **ep),
        now=T0,
        trigger=Trigger.NEW_PRESCRIPTION,
        rulepack=pack,
        catalog=catalog,
        renal=RenalDosing.load(),
    )


def by_rule(result):
    return {(f.rule_id, f.order_id): f for f in result.findings}


def test_end_to_end_guideline_concordant_cystitis(pack, catalog):
    result = evaluate(pack, catalog, (order("nitrofurantoin", id="n"),))
    f = by_rule(result)
    for rule in ("R1_INDICATION", "R3_DOSE", "R5_DURATION"):
        assert f[(rule, "n")].outcome is Outcome.PASS
        assert f[(rule, "n")].evidence[0].source_id == "ncdc-ntg-2025"
    assert result.ruleset_version == pack.version


def test_end_to_end_discordant_cystitis_is_flagged(pack, catalog):
    cipro = order("ciprofloxacin", id="c", dose_mg=500, freq_per_day=2, duration_days=3)
    result = evaluate(pack, catalog, (cipro,))
    f = by_rule(result)
    assert f[("R1_INDICATION", "c")].outcome is Outcome.FLAG
    assert f[("R1_INDICATION", "c")].suggestion.drug == "nitrofurantoin"
    assert f[("R3_DOSE", "c")].outcome is Outcome.CANNOT_ASSESS
    assert f[("R5_DURATION", "c")].outcome is Outcome.CANNOT_ASSESS
    assert result.status is EvaluationStatus.FLAGGED


def test_end_to_end_pneumonia_overlong_duration(pack, catalog):
    amox = order("amoxicillin", id="a", dose_mg=1000, freq_per_day=3, duration_days=10)
    result = evaluate(pack, catalog, (amox,), syndrome_code="cap_opd_no_comorbidity")
    f = by_rule(result)
    assert f[("R1_INDICATION", "a")].outcome is Outcome.PASS
    assert f[("R3_DOSE", "a")].outcome is Outcome.PASS
    duration = f[("R5_DURATION", "a")]
    assert duration.outcome is Outcome.FLAG
    assert duration.evidence[0].page == "p. 83"


def test_end_to_end_unknown_syndrome_never_passes(pack, catalog):
    result = evaluate(pack, catalog, (order("nitrofurantoin", id="n"),), syndrome_code="gout")
    f = by_rule(result)
    for rule in ("R1_INDICATION", "R3_DOSE", "R5_DURATION"):
        assert f[(rule, "n")].outcome is Outcome.CANNOT_ASSESS
