"""Application service: request in, evaluated and explained report out.

This is orchestration only. Every clinical result comes from evaluate_episode(); the service
builds its inputs (intake), attaches an action and a guideline explanation to each finding
(advice, evidence), records reviews through apply_review into the audit log, and adds the
deterministic DrugBank drug-drug interaction lookup for the episode's medication pairs (ddi).
"""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import BaseModel

from .advice import CultureSummary, action_for, culture_summary
from .audit import AuditLog
from .ddi import DDIFinding, DDIProvider, DDIResult, check_pairs
from .drugs import Catalog
from .episode import _sort_key, evaluate_episode
from .evidence import EvidenceRetriever, Explainer, Passage, TemplateExplainer
from .intake import EpisodeRequest, build_episode
from .ports import RenalChecker
from .review import apply_review
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
    Trigger,
)
from .timeout import first_antibiotic_start, is_timeout_due

logger = logging.getLogger(__name__)


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
    # Structured DrugBank pair result behind a DDI_* finding; None for every other rule.
    ddi: DDIResult | None = None


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
        ddi: DDIProvider | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.catalog = catalog
        self.rulepack = rulepack
        self.renal = renal
        self.audit = audit
        self.retriever = retriever
        self.explainer = explainer or TemplateExplainer()
        self.ddi = ddi
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
        ddi_findings, ddi_crashed = self._ddi_checks(episode)
        ddi_by_rule = {df.finding.rule_id: df.result for df in ddi_findings}
        findings = tuple(sorted([*result.findings, *(df.finding for df in ddi_findings)], key=_sort_key))
        status = result.status
        if ddi_crashed:
            # Same contract as a failed engine check: a partial run is INCOMPLETE, never OK.
            status = EvaluationStatus.INCOMPLETE
        elif status is EvaluationStatus.OK and any(
            f.outcome is not Outcome.PASS for f in findings
        ):
            status = EvaluationStatus.FLAGGED
        syndrome = self.rulepack.syndrome(episode.syndrome_code) if episode.syndrome_code else None
        names = {o.id: o.generic for o in episode.orders}
        items = tuple(
            self._view(
                f,
                names.get(f.order_id) or _ddi_label(ddi_by_rule.get(f.rule_id)),
                syndrome,
                episode.syndrome_code,
                ddi=ddi_by_rule.get(f.rule_id),
            )
            for f in findings
        )
        dumped = result.model_dump()
        dumped["status"] = status
        dumped["findings"] = findings
        report = EvaluationReport(
            **dumped,
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

    def _ddi_checks(self, episode: Episode) -> tuple[tuple[DDIFinding, ...], bool]:
        """Medication-pair interaction lookup. No provider means no DDI check at all; any
        failure is reported as a crashed check (evaluation INCOMPLETE), never swallowed."""
        if self.ddi is None:
            return (), False
        try:
            checks = check_pairs(episode, self.ddi)
        except Exception as exc:  # noqa: BLE001 - defensive; check_pairs catches per pair
            logger.exception("Drug-drug interaction checks failed for episode %s", episode.id)
            return (), True
        return checks.findings, checks.crashed

    def evaluate_request(self, request: EpisodeRequest) -> EvaluationReport:
        return self.evaluate(self.create_episode(request).id)

    def get_evaluation(self, evaluation_id: str) -> EvaluationReport:
        try:
            return self._evaluations[evaluation_id]
        except KeyError:
            raise NotFoundError(f"Unknown evaluation {evaluation_id}") from None

    def _view(
        self,
        finding: Finding,
        drug,
        syndrome,
        syndrome_code,
        ddi: DDIResult | None = None,
    ) -> FindingView:
        passages: list[Passage] = []
        # A DDI finding is explained by DrugBank itself; guideline passages from the
        # retrieval corpus are unrelated to it and must not be cited alongside it.
        if self.retriever is not None and ddi is None and finding.outcome is not Outcome.PASS:
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
            ddi=ddi,
        )

    # --- review, audit, time-out --------------------------------------------------------

    def review(self, request: ReviewRequest) -> AuditEntry:
        """Validate a pharmacist decision against its evaluation and append it to the audit log."""
        evaluation = self.get_evaluation(request.evaluation_id)
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


def _ddi_label(result: DDIResult | None) -> str | None:
    """Drug shown for a DDI finding: "a + b" for a pair, the raw text for an unreadable order."""
    if result is None:
        return None
    if result.drug_a and result.drug_b:
        return f"{result.drug_a} + {result.drug_b}"
    return result.drug_a


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
