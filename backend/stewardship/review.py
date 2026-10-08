"""Pharmacist decisions on findings, validated before they reach the audit log.

The engine only suggests; a person decides. These checks keep decisions meaningful: an
override needs a reason, and a finding the engine could not assess cannot simply be accepted,
because there is nothing to accept until the missing input is supplied.
"""

from .schemas import AuditEntry, Evaluation, Outcome, Review, ReviewAction
from .timeout import TIMEOUT_DONE

REASON_CODES = frozenset(
    {
        "CLINICAL_JUDGEMENT",
        "CULTURE_PENDING",
        "PATIENT_FACTOR",
        "GUIDELINE_EXCEPTION",
        TIMEOUT_DONE,
    }
)


class ReviewError(ValueError):
    """A review that cannot be applied to the evaluation it references."""


def apply_review(evaluation: Evaluation, review: Review) -> AuditEntry:
    """Validate a review against its evaluation and return the audit entry to record."""
    if review.evaluation_id != evaluation.id:
        raise ReviewError(
            f"Review references evaluation {review.evaluation_id}, not {evaluation.id}."
        )
    if review.reason_code is not None and review.reason_code not in REASON_CODES:
        raise ReviewError(f"Unknown reason code '{review.reason_code}'.")

    if review.finding_rule_id is None:
        if review.reason_code is None:
            raise ReviewError("An episode-level review needs a reason code.")
        entity, entity_id = "episode", review.episode_id
    else:
        finding = next(
            (
                f
                for f in evaluation.findings
                if f.rule_id == review.finding_rule_id and f.order_id == review.order_id
            ),
            None,
        )
        if finding is None:
            raise ReviewError(
                f"Finding {review.finding_rule_id} for order {review.order_id} "
                "is not in evaluation."
            )
        if review.action in {ReviewAction.MODIFY, ReviewAction.REMOVE, ReviewAction.OVERRIDE}:
            if review.reason_code is None:
                raise ReviewError(f"A {review.action.value.lower()} decision needs a reason code.")
        if review.action is ReviewAction.ACCEPT and finding.outcome is Outcome.CANNOT_ASSESS:
            raise ReviewError(
                "A CANNOT_ASSESS finding cannot be accepted; supply the missing "
                "input (MODIFY) or OVERRIDE with a reason."
            )
        entity = "finding"
        entity_id = f"{evaluation.id}:{review.finding_rule_id}:{review.order_id}"

    return AuditEntry(
        at=review.at,
        actor=review.reviewer,
        action=f"review.{review.action}",
        entity=entity,
        entity_id=entity_id,
        payload=review.model_dump(mode="json"),
    )
