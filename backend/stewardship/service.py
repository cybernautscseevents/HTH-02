"""Application service: request in, evaluated and explained report out.

This is orchestration only. Every clinical result comes from evaluate_episode(); the service
builds its inputs (intake), attaches an action and a guideline explanation to each finding
(advice, evidence), and records reviews through apply_review into the audit log.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import BaseModel

from .advice import CultureSummary, action_for, culture_summary
from .audit import AuditLog
from .drugs import Catalog
from .episode import evaluate_episode
from .evidence import EvidenceRetriever, Explainer, Passage, TemplateExplainer
from .intake import EpisodeRequest, build_episode
from .ports import RenalChecker
from .review import ReviewError, apply_review
from .rulepack import YamlRulePack
from .schemas import (
    AuditEntry,
    Episode,
    Evaluation,
    EvaluationStatus,
    Evidence,
    Finding,
    NormStatus,
    Outcome,
    Review,
    ReviewAction,
    Severity,
    Trigger,
)
from .timeout import first_antibiotic_start, is_timeout_due


class OrderView(BaseModel):
    id: str
    raw_text: str
    generic: str | None
    brand: str | None
    norm_status: NormStatus
    norm_candidates: tuple[str, ...]
    norm_reason: str
    dose_mg: float | None
    freq_per_day: float | None
    route: str | None
    duration_days: int | None


class FindingView(BaseModel):
    """A finding as shown to the clinician: the rule result, what to do, and why."""

    rule_id: str
    outcome: Outcome
    severity: str
    order_id: str | None
    drug: str | None
    message: str
    action: str | None
    suggestion_action: str | None
    missing_inputs: tuple[str, ...]
    evidence: tuple[Evidence, ...]
    explanation: str
    guideline_passages: tuple[Passage, ...] = ()


class SyndromeView(BaseModel):
    code: str | None
    name: str | None
    resolution: str  # selected | mapped_from_text | unresolved


class EvaluationReport(Evaluation):
    """The engine's Evaluation, unchanged, plus what the clinician needs to act on it."""

    syndrome: SyndromeView
    orders: tuple[OrderView, ...]
    culture: CultureSummary
    items: tuple[FindingView, ...]
    warnings: tuple[str, ...] = ()


class ReviewRequest(BaseModel):
    episode_id: str
    evaluation_id: str
    finding_rule_id: str | None = None
    order_id: str | None = None
    reviewer: str
    action: ReviewAction
    reason_code: str | None = None
    note: str | None = None


class RecentEvaluation(BaseModel):
    evaluation_id: str
    episode_id: str
    patient_id: str
    status: EvaluationStatus
    evaluated_at: datetime
    high_count: int
    moderate_count: int


class DashboardStats(BaseModel):
    total_reviewed: int
    flagged_count: int
    pending_review_count: int
    high_severity_count: int
    timeout_due_count: int
    recent_evaluations: tuple[RecentEvaluation, ...]


class NotFoundError(KeyError):
    """Unknown episode or evaluation id."""


class StewardshipService:
    def __init__(
        self,
        *,
        catalog: Catalog,
        rulepack: YamlRulePack,
        renal: RenalChecker,
        audit: AuditLog,
        retriever: EvidenceRetriever | None = None,
        explainer: Explainer | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.catalog = catalog
        self.rulepack = rulepack
        self.renal = renal
        self.audit = audit
        self.retriever = retriever
        self.explainer = explainer or TemplateExplainer()
        self.clock = clock
        self._episodes: dict[str, Episode] = {}
        self._extras: dict[str, tuple[tuple[OrderView, ...], str, tuple[str, ...]]] = {}
        self._evaluations: dict[str, EvaluationReport] = {}
        self._reviews: list[Review] = []

    # --- episodes -----------------------------------------------------------------------

    def create_episode(self, request: EpisodeRequest) -> Episode:
        episode_id = f"EP-{uuid.uuid4().hex[:8]}"
        episode, readings, how, warnings = build_episode(
            request,
            episode_id=episode_id,
            catalog=self.catalog,
            codes=self.rulepack.codes(),
            now=self.clock(),
        )
        views = tuple(_order_view(r.order, r.reason) for r in readings)
        self._episodes[episode_id] = episode
        self._extras[episode_id] = (views, how, warnings)
        return episode

    def get_episode(self, episode_id: str) -> Episode:
        try:
            return self._episodes[episode_id]
        except KeyError:
            raise NotFoundError(f"Unknown episode {episode_id}") from None

    def list_episodes(self) -> tuple[Episode, ...]:
        return tuple(reversed(self._episodes.values()))

    def evaluate(
        self, episode_id: str, trigger: Trigger = Trigger.NEW_PRESCRIPTION
    ) -> EvaluationReport:
        """Run the deterministic engine on the stored episode and explain the result."""
        episode = self.get_episode(episode_id)
        views, how, warnings = self._extras[episode_id]
        result = evaluate_episode(
            episode,
            now=self.clock(),
            trigger=trigger,
            rulepack=self.rulepack,
            catalog=self.catalog,
            renal=self.renal,
        )
        syndrome = self.rulepack.syndrome(episode.syndrome_code) if episode.syndrome_code else None
        names = {o.id: o.generic for o in episode.orders}
        items = tuple(
            self._view(f, names.get(f.order_id), syndrome, episode.syndrome_code)
            for f in result.findings
        )
        report = EvaluationReport(
            **result.model_dump(),
            syndrome=SyndromeView(
                code=episode.syndrome_code, name=syndrome.name if syndrome else None, resolution=how
            ),
            orders=views,
            culture=culture_summary(episode.specimens, syndrome),
            items=items,
            warnings=warnings,
        )
        self._evaluations[report.id] = report
        return report

    def evaluate_request(self, request: EpisodeRequest) -> EvaluationReport:
        return self.evaluate(self.create_episode(request).id)

    def get_evaluation(self, evaluation_id: str) -> EvaluationReport:
        try:
            return self._evaluations[evaluation_id]
        except KeyError:
            raise NotFoundError(f"Unknown evaluation {evaluation_id}") from None

    def reviews_for_evaluation(self, evaluation_id: str) -> tuple[Review, ...]:
        self.get_evaluation(evaluation_id)
        return tuple(review for review in self._reviews if review.evaluation_id == evaluation_id)

    def dashboard_stats(self) -> DashboardStats:
        latest: dict[str, EvaluationReport] = {}
        for report in self._evaluations.values():
            latest[report.episode_id] = report
        reports = sorted(latest.values(), key=lambda item: item.evaluated_at, reverse=True)
        reviewed = {
            (review.evaluation_id, review.finding_rule_id, review.order_id)
            for review in self._reviews
            if review.finding_rule_id is not None
        }
        pending = sum(
            1
            for report in reports
            for finding in report.findings
            if finding.outcome is not Outcome.PASS
            and (report.id, finding.rule_id, finding.order_id) not in reviewed
        )
        recent = tuple(
            RecentEvaluation(
                evaluation_id=report.id,
                episode_id=report.episode_id,
                patient_id=self._episodes[report.episode_id].patient.id,
                status=report.status,
                evaluated_at=report.evaluated_at,
                high_count=sum(
                    finding.outcome is not Outcome.PASS and finding.severity is Severity.HIGH
                    for finding in report.findings
                ),
                moderate_count=sum(
                    finding.outcome is not Outcome.PASS
                    and finding.severity is Severity.MODERATE
                    for finding in report.findings
                ),
            )
            for report in reports[:10]
        )
        return DashboardStats(
            total_reviewed=len(reports),
            flagged_count=sum(report.status is not EvaluationStatus.OK for report in reports),
            pending_review_count=pending,
            high_severity_count=sum(
                finding.outcome is not Outcome.PASS and finding.severity is Severity.HIGH
                for report in reports
                for finding in report.findings
            ),
            timeout_due_count=len(self.timeout_due()),
            recent_evaluations=recent,
        )

    def _view(self, finding: Finding, drug, syndrome, syndrome_code) -> FindingView:
        passages: list[Passage] = []
        if self.retriever is not None and finding.outcome is not Outcome.PASS:
            query = " ".join(
                filter(None, [syndrome.name if syndrome else None, drug, finding.message])
            )
            passages = self.retriever.retrieve(query, syndrome_code=syndrome_code, k=2)
        return FindingView(
            rule_id=finding.rule_id,
            outcome=finding.outcome,
            severity=finding.severity.value,
            order_id=finding.order_id,
            drug=drug,
            message=finding.message,
            action=action_for(finding),
            suggestion_action=finding.suggestion.action.value if finding.suggestion else None,
            missing_inputs=finding.missing_inputs,
            evidence=finding.evidence,
            explanation=self.explainer.explain(finding, passages),
            guideline_passages=tuple(passages),
        )

    # --- review, audit, time-out --------------------------------------------------------

    def review(self, request: ReviewRequest) -> AuditEntry:
        """Validate a pharmacist decision against its evaluation and append it to the audit log."""
        evaluation = self.get_evaluation(request.evaluation_id)
        if request.episode_id != evaluation.episode_id:
            raise ReviewError("Review episode_id does not match the evaluation episode.")
        review = Review(id=uuid.uuid4().hex, at=self.clock(), **request.model_dump())
        entry = apply_review(evaluation, review)  # raises ReviewError if not acceptable
        self.audit.append(entry)
        self._reviews.append(review)
        return entry

    def timeout_due(self) -> list[dict]:
        now = self.clock()
        due = []
        for episode in self._episodes.values():
            if is_timeout_due(episode, now, self._reviews, self.catalog):
                start = first_antibiotic_start(episode, self.catalog)
                drugs = [
                    o.generic
                    for o in episode.orders
                    if o.generic and self.catalog.is_antibiotic(o.generic)
                ]
                due.append(
                    {
                        "episode_id": episode.id,
                        "patient_id": episode.patient.id,
                        "setting": episode.setting.value,
                        "antibiotic_name": ", ".join(drugs),
                        "started_at": start.isoformat(),
                        "hours_elapsed": round((now - start).total_seconds() / 3600, 1),
                        "status": "REVIEW_DUE",
                    }
                )
        return due


def _order_view(order, reason: str) -> OrderView:
    return OrderView(
        id=order.id,
        raw_text=order.raw_text,
        generic=order.generic,
        brand=order.brand,
        norm_status=order.norm_status,
        norm_candidates=order.norm_candidates,
        norm_reason=reason,
        dose_mg=order.dose_mg,
        freq_per_day=order.freq_per_day,
        route=order.route.value if order.route else None,
        duration_days=order.duration_days,
    )
