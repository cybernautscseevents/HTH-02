from datetime import timedelta

import pytest

from backend.stewardship.audit import JsonlAuditLog
from backend.stewardship.review import ReviewError, apply_review
from backend.stewardship.schemas import (
    Evaluation,
    EvaluationStatus,
    Finding,
    Outcome,
    Review,
    ReviewAction,
    Severity,
    Trigger,
)
from backend.stewardship.timeout import TIMEOUT_DONE, is_timeout_due

from .fakes import T0, FakeCatalog, episode


def evaluation(*findings: Finding) -> Evaluation:
    return Evaluation(
        id="ev1",
        episode_id="e1",
        evaluated_at=T0,
        trigger=Trigger.MANUAL,
        ruleset_version="test-1",
        inputs_hash="h",
        status=EvaluationStatus.FLAGGED,
        findings=findings,
    )


FLAG = Finding(
    rule_id="R2_AWARE",
    outcome=Outcome.FLAG,
    severity=Severity.MODERATE,
    order_id="o1",
    message="watch",
)
GAP = Finding(
    rule_id="R3_DOSE",
    outcome=Outcome.CANNOT_ASSESS,
    severity=Severity.MODERATE,
    order_id="o1",
    message="dose missing",
)


def review(**overrides) -> Review:
    values = dict(
        id="r1",
        episode_id="e1",
        evaluation_id="ev1",
        finding_rule_id="R2_AWARE",
        order_id="o1",
        reviewer="pharmacist-1",
        action=ReviewAction.ACCEPT,
        at=T0,
    )
    return Review(**(values | overrides))


def test_accepting_a_flag_produces_an_audit_entry():
    entry = apply_review(evaluation(FLAG), review())
    assert (entry.actor, entry.action, entry.entity_id) == (
        "pharmacist-1",
        "review.ACCEPT",
        "ev1:R2_AWARE:o1",
    )


def test_override_requires_a_reason():
    with pytest.raises(ReviewError, match="reason"):
        apply_review(evaluation(FLAG), review(action=ReviewAction.OVERRIDE))


def test_unknown_reason_code_is_rejected():
    with pytest.raises(ReviewError, match="reason code"):
        apply_review(evaluation(FLAG), review(action=ReviewAction.OVERRIDE, reason_code="BUSY"))


def test_cannot_accept_a_finding_that_could_not_be_assessed():
    with pytest.raises(ReviewError, match="CANNOT_ASSESS"):
        apply_review(evaluation(GAP), review(finding_rule_id="R3_DOSE"))


def test_review_must_reference_an_existing_finding():
    with pytest.raises(ReviewError, match="not in evaluation"):
        apply_review(evaluation(FLAG), review(finding_rule_id="R9_MISSING"))


def test_review_must_reference_the_same_evaluation():
    with pytest.raises(ReviewError, match="evaluation"):
        apply_review(evaluation(FLAG), review(evaluation_id="other"))


def test_episode_level_timeout_review_needs_reason_code():
    with pytest.raises(ReviewError):
        apply_review(evaluation(FLAG), review(finding_rule_id=None, order_id=None))
    entry = apply_review(
        evaluation(FLAG), review(finding_rule_id=None, order_id=None, reason_code=TIMEOUT_DONE)
    )
    assert entry.entity == "episode"


def test_audit_log_is_append_only_and_filterable(tmp_path):
    log = JsonlAuditLog(tmp_path / "audit.jsonl")
    log.append(apply_review(evaluation(FLAG), review()))
    log.append(
        apply_review(
            evaluation(FLAG), review(finding_rule_id=None, order_id=None, reason_code=TIMEOUT_DONE)
        )
    )
    assert len(log.list()) == 2
    assert [e.entity for e in log.list(entity_id="ev1:R2_AWARE:o1")] == ["finding"]


def test_timeout_is_due_after_threshold_until_reviewed():
    ep, catalog = episode(), FakeCatalog()
    assert not is_timeout_due(ep, T0 + timedelta(hours=47), [], catalog)
    assert is_timeout_due(ep, T0 + timedelta(hours=48), [], catalog)
    done = review(finding_rule_id=None, order_id=None, reason_code=TIMEOUT_DONE)
    assert not is_timeout_due(ep, T0 + timedelta(hours=72), [done], catalog)


def test_timeout_never_due_without_antibiotics():
    ep = episode(orders=())
    assert not is_timeout_due(ep, T0 + timedelta(days=5), [], FakeCatalog())
