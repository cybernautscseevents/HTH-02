"""Validation and canonicalization for pharmacist-signed antibiotic plans."""

from datetime import timedelta

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .drugs import Catalog
from .schemas import (
    Episode,
    Evaluation,
    MedicationDisposition,
    MedicationPlanItem,
    NormStatus,
    Outcome,
    RegimenSnapshot,
    Review,
    ReviewPhase,
    Route,
    TreatmentPlanStatus,
)


class PlanError(ValueError):
    """A treatment plan is incomplete, inconsistent, or stale."""


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegimenRequest(_Request):
    generic: str = Field(min_length=1)
    dose_mg: float = Field(gt=0)
    freq_per_day: float = Field(gt=0)
    route: Route
    total_duration_days: int = Field(gt=0)
    course_started_at: AwareDatetime


class PlanItemRequest(_Request):
    source_order_id: str = Field(min_length=1)
    disposition: MedicationDisposition
    final_regimen: RegimenRequest | None = None
    reason_code: str | None = None
    rationale: str | None = None
    linked_findings: tuple[str, ...] = ()
    requested_inputs: tuple[str, ...] = ()
    requested_from: str | None = None
    due_at: AwareDatetime | None = None
    escalation_destination: str | None = None
    escalation_urgency: str | None = None


class TreatmentPlanRequest(_Request):
    phase: ReviewPhase = ReviewPhase.INITIAL
    items: tuple[PlanItemRequest, ...] = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    reviewer_role: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=8)
    supersedes_id: str | None = None


def validate_plan(
    request: TreatmentPlanRequest,
    episode: Episode,
    evaluation: Evaluation,
    reviews: tuple[Review, ...],
    catalog: Catalog,
) -> tuple[tuple[MedicationPlanItem, ...], TreatmentPlanStatus]:
    if evaluation.episode_id != episode.id:
        raise PlanError("Evaluation does not belong to the episode.")
    missing_reviews = {
        (finding.rule_id, finding.order_id)
        for finding in evaluation.findings
        if finding.outcome is not Outcome.PASS
    } - {
        (review.finding_rule_id, review.order_id)
        for review in reviews
        if review.finding_rule_id is not None
    }
    if missing_reviews:
        raise PlanError("Every non-pass finding needs a pharmacist review before sign-off.")

    source_orders = {
        order.id: order
        for order in episode.orders
        if order.generic
        and order.norm_status in {NormStatus.ACCEPTED, NormStatus.CONFIRMED}
        and catalog.is_antibiotic(order.generic)
    }
    supplied = [item.source_order_id for item in request.items]
    if len(supplied) != len(set(supplied)):
        raise PlanError("Each antibiotic order must appear exactly once in the plan.")
    if set(supplied) != set(source_orders):
        raise PlanError("The plan must include exactly one disposition for every antibiotic order.")

    items = tuple(
        _validate_item(item, source_orders[item.source_order_id], catalog) for item in request.items
    )
    status = (
        TreatmentPlanStatus.ACTION_REQUIRED
        if any(
            item.disposition in {MedicationDisposition.REQUEST_INFO, MedicationDisposition.ESCALATE}
            for item in items
        )
        else TreatmentPlanStatus.READY
    )
    return items, status


def _validate_item(request: PlanItemRequest, order, catalog: Catalog) -> MedicationPlanItem:
    if order.generic is None:
        raise PlanError(f"Order {order.id} has no confirmed drug identity.")
    before = RegimenSnapshot(
        source_order_id=order.id,
        generic=order.generic,
        dose_mg=order.dose_mg,
        freq_per_day=order.freq_per_day,
        route=order.route,
        total_duration_days=order.duration_days,
        course_started_at=order.started_at,
        planned_stop_at=(
            order.started_at + timedelta(days=order.duration_days) if order.duration_days else None
        ),
    )
    disposition = request.disposition
    resolved = {
        MedicationDisposition.CONTINUE,
        MedicationDisposition.MODIFY,
        MedicationDisposition.SWITCH,
    }
    if disposition in resolved and request.final_regimen is None:
        raise PlanError(f"{disposition.value} requires a complete final regimen.")
    if disposition not in resolved and request.final_regimen is not None:
        raise PlanError(f"{disposition.value} must not include a final regimen.")
    if disposition is not MedicationDisposition.CONTINUE:
        if not request.reason_code or not request.rationale or not request.rationale.strip():
            raise PlanError(f"{disposition.value} requires a reason and rationale.")

    final = (
        _canonical_regimen(request.final_regimen, order.id, catalog)
        if request.final_regimen
        else None
    )
    if disposition is MedicationDisposition.CONTINUE:
        if not _same_regimen(before, final):
            raise PlanError(
                "CONTINUE must preserve drug, dose, route, frequency, and total duration."
            )
    elif disposition is MedicationDisposition.MODIFY:
        assert final is not None
        if final.generic != before.generic:
            raise PlanError("MODIFY cannot change the generic; use SWITCH.")
        if _same_regimen(before, final):
            raise PlanError("MODIFY must change at least one regimen field.")
    elif disposition is MedicationDisposition.SWITCH:
        assert final is not None
        if final.generic == before.generic:
            raise PlanError("SWITCH requires a different antibiotic.")
    elif disposition is MedicationDisposition.REQUEST_INFO:
        if not request.requested_inputs:
            raise PlanError("REQUEST_INFO requires at least one requested input.")
    elif disposition is MedicationDisposition.ESCALATE:
        if not request.escalation_destination or request.escalation_urgency not in {
            "ROUTINE",
            "URGENT",
        }:
            raise PlanError("ESCALATE requires a destination and ROUTINE or URGENT urgency.")

    return MedicationPlanItem(
        source_order_id=order.id,
        disposition=disposition,
        before=before,
        final_regimen=final,
        reason_code=request.reason_code,
        rationale=request.rationale.strip() if request.rationale else None,
        linked_findings=request.linked_findings,
        requested_inputs=request.requested_inputs,
        requested_from=request.requested_from,
        due_at=request.due_at,
        escalation_destination=request.escalation_destination,
        escalation_urgency=request.escalation_urgency,
    )


def _canonical_regimen(
    request: RegimenRequest, source_order_id: str, catalog: Catalog
) -> RegimenSnapshot:
    normalized = catalog.normalize(request.generic)
    if normalized.status is not NormStatus.ACCEPTED or not normalized.generic:
        raise PlanError(f"Final drug '{request.generic}' is not recognized by the catalog.")
    if not catalog.is_antibiotic(normalized.generic):
        raise PlanError(f"Final drug '{normalized.generic}' is not an antibiotic.")
    return RegimenSnapshot(
        source_order_id=source_order_id,
        generic=normalized.generic,
        dose_mg=request.dose_mg,
        freq_per_day=request.freq_per_day,
        route=request.route,
        total_duration_days=request.total_duration_days,
        course_started_at=request.course_started_at,
        planned_stop_at=request.course_started_at + timedelta(days=request.total_duration_days),
    )


def _same_regimen(before: RegimenSnapshot, after: RegimenSnapshot | None) -> bool:
    return after is not None and (
        before.generic,
        before.dose_mg,
        before.freq_per_day,
        before.route,
        before.total_duration_days,
        before.course_started_at,
    ) == (
        after.generic,
        after.dose_mg,
        after.freq_per_day,
        after.route,
        after.total_duration_days,
        after.course_started_at,
    )
