"""Evaluate a therapy episode: the single entry point the API calls.

Every trigger (new prescription, culture result, lab update, time-out) re-runs the same
deterministic evaluation over the episode's current state. A check that crashes does not take
the evaluation down and is never silently skipped: it becomes a CANNOT_ASSESS finding and the
evaluation is marked INCOMPLETE, so nobody mistakes a partial check for a clean one.
"""

import hashlib
import logging
import uuid
from collections.abc import Callable
from datetime import datetime

from .culture import CULTURE_RULES
from .ports import CoverageEstimator, DrugCatalog, RenalChecker, RulePack
from .rules import ORDER_RULES, RuleContext, check_identified, is_identified
from .schemas import (
    CoverageEstimate,
    CultureStatus,
    Episode,
    Evaluation,
    EvaluationStatus,
    Finding,
    Outcome,
    Severity,
    Trigger,
)

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {Severity.HIGH: 0, Severity.MODERATE: 1, Severity.LOW: 2, Severity.INFO: 3}
_OUTCOME_RANK = {Outcome.CANNOT_ASSESS: 0, Outcome.FLAG: 1, Outcome.PASS: 2}


def _failed(rule_id: str, order_id: str | None, exc: Exception) -> Finding:
    return Finding(
        rule_id=rule_id,
        outcome=Outcome.CANNOT_ASSESS,
        severity=Severity.HIGH,
        order_id=order_id,
        message=f"Check failed ({type(exc).__name__}); result not available.",
    )


def _coverage(ctx: RuleContext, coverage: CoverageEstimator) -> tuple[CoverageEstimate, ...]:
    """Empiric coverage for prescribed antibiotics and the syndrome's first-line options."""
    prescribed = [
        o.generic
        for o in ctx.episode.orders
        if is_identified(o) and ctx.catalog.is_antibiotic(o.generic)
    ]
    first_line = [r.generic for r in ctx.syndrome.first_line]
    regimens = list(dict.fromkeys(prescribed + first_line))
    return coverage.estimate(ctx.episode.syndrome_code, ctx.episode.setting, regimens)


def _sort_key(f: Finding) -> tuple:
    return (_SEVERITY_RANK[f.severity], _OUTCOME_RANK[f.outcome], f.rule_id, f.order_id or "")


def evaluate_episode(
    episode: Episode,
    *,
    now: datetime,
    trigger: Trigger,
    rulepack: RulePack,
    catalog: DrugCatalog,
    renal: RenalChecker,
    coverage: CoverageEstimator | None = None,
) -> Evaluation:
    """Run all prescription and culture checks over the episode and return one evaluation."""
    ctx = RuleContext.build(
        episode=episode, rulepack=rulepack, catalog=catalog, renal=renal, now=now
    )
    findings: list[Finding] = []
    crashed = False

    def collect(
        rule_id: str, order_id: str | None, check: Callable[[], Finding | tuple[Finding, ...]]
    ) -> None:
        nonlocal crashed
        try:
            result = check()
        except Exception as exc:
            logger.exception("Check %s failed for order %s", rule_id, order_id)
            findings.append(_failed(rule_id, order_id, exc))
            crashed = True
            return
        findings.extend(result if isinstance(result, tuple) else (result,))

    for order in episode.orders:
        collect("R0_IDENTIFIED", order.id, lambda o=order: check_identified(ctx, o))
        if not is_identified(order) or not catalog.is_antibiotic(order.generic):
            continue
        for rule_id, rule in ORDER_RULES:
            collect(rule_id, order.id, lambda r=rule, o=order: r(ctx, o))

    for rule_id, rule in CULTURE_RULES:
        collect(rule_id, None, lambda r=rule: r(ctx))

    estimates: tuple[CoverageEstimate, ...] = ()
    culture_final = any(s.status is CultureStatus.FINAL for s in episode.specimens)
    if coverage is not None and ctx.syndrome is not None and not culture_final:
        try:
            estimates = _coverage(ctx, coverage)
        except Exception as exc:
            logger.exception("Coverage estimate failed for episode %s", episode.id)
            findings.append(_failed("COVERAGE", None, exc))
            crashed = True

    if crashed:
        status = EvaluationStatus.INCOMPLETE
    elif any(f.outcome is not Outcome.PASS for f in findings):
        status = EvaluationStatus.FLAGGED
    else:
        status = EvaluationStatus.OK

    digest = hashlib.sha256(
        "|".join((episode.model_dump_json(), rulepack.version, now.isoformat())).encode()
    ).hexdigest()

    return Evaluation(
        id=uuid.uuid4().hex,
        episode_id=episode.id,
        evaluated_at=now,
        trigger=trigger,
        ruleset_version=rulepack.version,
        inputs_hash=digest,
        status=status,
        findings=tuple(sorted(findings, key=_sort_key)),
        coverage=estimates,
    )
