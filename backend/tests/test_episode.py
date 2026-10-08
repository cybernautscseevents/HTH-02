from datetime import timedelta

from backend.stewardship.episode import evaluate_episode
from backend.stewardship.schemas import (
    EvaluationStatus,
    NormStatus,
    Outcome,
    Severity,
    Trigger,
)

from .fakes import (
    T0,
    CrashingRenal,
    FakeCatalog,
    FakeCoverage,
    FakeRenal,
    FakeRulePack,
    episode,
    isolate,
    order,
    specimen,
)


def evaluate(ep, now=T0, renal=None, coverage=None):
    return evaluate_episode(
        ep,
        now=now,
        trigger=Trigger.NEW_PRESCRIPTION,
        rulepack=FakeRulePack(),
        catalog=FakeCatalog(),
        renal=renal or FakeRenal(),
        coverage=coverage,
    )


def outcomes(evaluation):
    return {(f.rule_id, f.order_id): f.outcome for f in evaluation.findings}


def test_guideline_compliant_prescription_is_ok():
    result = evaluate(episode())
    assert result.status is EvaluationStatus.OK
    assert all(f.outcome is Outcome.PASS for f in result.findings)


def test_watch_drug_with_long_duration_is_flagged():
    ep = episode(orders=(order("ciprofloxacin", dose_mg=500, freq_per_day=2, duration_days=7),))
    result = evaluate(ep)
    found = outcomes(result)
    assert result.status is EvaluationStatus.FLAGGED
    assert found[("R2_AWARE", "o1")] is Outcome.FLAG
    assert found[("R5_DURATION", "o1")] is Outcome.FLAG


def test_unidentified_order_gets_only_the_identification_finding():
    ep = episode(
        orders=(order(generic=None, norm_status=NormStatus.AMBIGUOUS, norm_candidates=("x", "y")),)
    )
    result = evaluate(ep)
    assert [f.rule_id for f in result.findings] == ["R0_IDENTIFIED"]
    assert result.status is EvaluationStatus.FLAGGED


def test_non_antibiotic_orders_are_not_checked_further():
    result = evaluate(episode(orders=(order("paracetamol"),)))
    assert [f.rule_id for f in result.findings] == ["R0_IDENTIFIED"]


def test_crashing_check_marks_evaluation_incomplete_but_keeps_other_findings():
    result = evaluate(episode(), renal=CrashingRenal())
    renal = next(f for f in result.findings if f.rule_id == "R4_RENAL")
    assert result.status is EvaluationStatus.INCOMPLETE
    assert (renal.outcome, renal.severity) == (Outcome.CANNOT_ASSESS, Severity.HIGH)
    assert ("R3_DOSE", "o1") in outcomes(result)


def test_findings_are_sorted_most_severe_first():
    ep = episode(orders=(order("ciprofloxacin", dose_mg=2000, freq_per_day=2),))
    severities = [f.severity for f in evaluate(ep).findings]
    assert severities[0] is Severity.HIGH
    assert severities[-1] is Severity.INFO


def test_evaluation_is_deterministic():
    first, second = evaluate(episode()), evaluate(episode())
    assert first.inputs_hash == second.inputs_hash
    assert first.findings == second.findings
    assert evaluate(episode(), now=T0 + timedelta(hours=1)).inputs_hash != first.inputs_hash


def test_coverage_requested_for_prescribed_and_first_line_drugs():
    coverage = FakeCoverage()
    result = evaluate(episode(orders=(order("ciprofloxacin"),)), coverage=coverage)
    assert coverage.calls[0][2] == ("ciprofloxacin", "nitrofurantoin")
    assert len(result.coverage) == 2


def test_coverage_skipped_once_culture_is_final():
    coverage = FakeCoverage()
    ep = episode(specimens=(specimen(isolates=(isolate(nitrofurantoin="S"),)),))
    assert evaluate(ep, coverage=coverage).coverage == ()
    assert coverage.calls == []
