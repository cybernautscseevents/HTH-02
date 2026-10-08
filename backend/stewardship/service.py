"""Application service: request in, evaluated and explained report out.

This is orchestration only. Every clinical result comes from evaluate_episode(); the service
builds its inputs (intake), attaches an action and a guideline explanation to each finding
(advice, evidence), adds a plain-language summary of the finished report (summary), records
reviews through apply_review into the audit log, and adds the deterministic DrugBank
drug-drug interaction lookup for the episode's medication pairs (ddi).
"""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from .advice import CultureSummary, action_for, culture_summary
from .audit import AuditLog
from .ddi import DDIFinding, DDIProvider, DDIResult, check_pairs
from .drugs import Catalog
from .episode import _sort_key, evaluate_episode
from .evidence import EvidenceRetriever, Explainer, Passage, TemplateExplainer
from .intake import (
    CultureInput,
    EpisodeRequest,
    build_episode,
    build_specimens,
    diagnosis_line,
    patient_identity,
    read_diagnosis,
)
from .narrative import PlanNarrativeSummarizer, TemplatePlanNarrativeSummarizer
from .ports import RenalChecker
from .review import ReviewError, apply_review
from .rulepack import YamlRulePack
from .schemas import (
    AllergyStatus,
    AuditEntry,
    Comorbidity,
    Episode,
    Evaluation,
    EvaluationStatus,
    Evidence,
    Finding,
    NormStatus,
    Outcome,
    Review,
    ReviewAction,
    ReviewPhase,
    Severity,
    TreatmentPlanSignOff,
    Trigger,
)
from .summary import EvaluationSummary, Summarizer, TemplateSummarizer, evidence_for
from .timeout import first_antibiotic_start, is_timeout_due
from .treatment_plan import (
    PlanError,
    TreatmentPlanRequest,
    unchanged_non_antibiotics,
    validate_plan,
)

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


class PrescriptionPatient(BaseModel):
    """The patient ID and name printed on a prescription, None where the page has none."""

    id: str | None
    name: str | None


class PrescriptionDiagnosis(BaseModel):
    """The diagnosis written on a prescription and the syndrome it reads as, if unambiguous."""

    text: str | None
    syndrome_code: str | None
    syndrome_name: str | None
    note: str | None  # why no syndrome was read from it


class EvaluationReport(Evaluation):
    """The engine's Evaluation, unchanged, plus what the clinician needs to act on it."""

    syndrome: SyndromeView
    orders: tuple[OrderView, ...]
    culture: CultureSummary
    items: tuple[FindingView, ...]
    warnings: tuple[str, ...] = ()
    # Written after every result above is fixed; explanation only, never read by review.
    summary: EvaluationSummary | None = None


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: str
    evaluation_id: str
    finding_rule_id: str | None = None
    order_id: str | None = None
    reviewer: str
    action: ReviewAction
    reason_code: str | None = None
    note: str | None = None


class PatientChanges(BaseModel):
    """Patient values to try in a what-if evaluation; a field left out keeps its value."""

    model_config = ConfigDict(extra="forbid")

    serum_creatinine_mg_dl: float | None = None
    allergy_status: AllergyStatus | None = None
    allergies: tuple[str, ...] | None = None
    pregnant: bool | None = None
    comorbidities: tuple[Comorbidity, ...] | None = None


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


class TimeoutItem(BaseModel):
    episode_id: str
    patient_id: str
    setting: str
    antibiotic_name: str
    started_at: datetime
    hours_elapsed: float
    status: str
    evaluation_id: str | None = None
    plan_id: str | None = None
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None


class NotFoundError(KeyError):
    """Unknown episode, evaluation, or treatment plan id."""


class ConflictError(ValueError):
    """A write conflicts with a newer or duplicate clinical record."""


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
        summarizer: Summarizer | None = None,
        plan_summarizer: PlanNarrativeSummarizer | None = None,
        ddi: DDIProvider | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.catalog = catalog
        self.rulepack = rulepack
        self.renal = renal
        self.audit = audit
        self.retriever = retriever
        self.explainer = explainer or TemplateExplainer()
        self.summarizer = summarizer or TemplateSummarizer()
        self.plan_summarizer = plan_summarizer or TemplatePlanNarrativeSummarizer()
        self.ddi = ddi
        self.clock = clock
        self._episodes: dict[str, Episode] = {}
        self._extras: dict[str, tuple[tuple[OrderView, ...], str, tuple[str, ...]]] = {}
        self._evaluations: dict[str, EvaluationReport] = {}
        self._reviews: list[Review] = []
        self._treatment_plans: list[TreatmentPlanSignOff] = []
        self._plan_idempotency: dict[str, tuple[str, TreatmentPlanSignOff]] = {}

    # --- episodes -----------------------------------------------------------------------

    def create_episode(self, request: EpisodeRequest) -> Episode:
        episode_id = f"EP-{uuid.uuid4().hex[:8]}"
        episode, readings, how, warnings = build_episode(
            request,
            episode_id=episode_id,
            catalog=self.catalog,
            codes=self.rulepack.codes(),
            now=self.clock(),
            names=self.syndrome_names(),
        )
        views = tuple(_order_view(r.order, r.reason) for r in readings)
        self._episodes[episode_id] = episode
        self._extras[episode_id] = (views, how, warnings)
        return episode

    def add_culture(self, episode_id: str, culture: CultureInput) -> EvaluationReport:
        """Attach a culture reported after the episode was created and re-run the rules.

        Earlier specimens are kept as they were; a new report is added beside them, never
        written over one."""
        episode = self.get_episode(episode_id)
        specimens = build_specimens((culture,), self.catalog, first=len(episode.specimens) + 1)
        self._episodes[episode_id] = episode.model_copy(
            update={"specimens": episode.specimens + specimens}
        )
        return self.evaluate(episode_id, Trigger.CULTURE_RESULT)

    def syndrome_names(self) -> dict[str, str]:
        return {code: self.rulepack.syndrome(code).name for code in self.rulepack.codes()}

    def prescription_patient(self, text: str) -> PrescriptionPatient:
        patient_id, name = patient_identity(text)
        return PrescriptionPatient(id=patient_id, name=name)

    def prescription_diagnosis(self, text: str) -> PrescriptionDiagnosis:
        """What the prescriber wrote as the diagnosis, for the reviewer to confirm."""
        diagnosis = diagnosis_line(text)
        names = self.syndrome_names()
        code, why = read_diagnosis(diagnosis, names)
        if diagnosis is None:
            why = "No diagnosis is written on the prescription."
        elif code is None and why is None:
            why = "The diagnosis does not name a syndrome in the guideline rule pack."
        return PrescriptionDiagnosis(
            text=diagnosis,
            syndrome_code=code,
            syndrome_name=names.get(code) if code else None,
            note=why,
        )

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
        report = self._report(self.get_episode(episode_id), trigger)
        summary = self.summarizer.explain(report, evidence_for(report))
        report = report.model_copy(update={"summary": summary})
        self._evaluations[report.id] = report
        return report

    def what_if(self, episode_id: str, changes: PatientChanges) -> EvaluationReport:
        """Evaluate the stored episode with some patient values changed, without saving.

        The result is never stored, so it cannot be reviewed, signed or audited; it shows
        what the same rules return for different inputs. No summary is written, so a model
        is never called and the result comes back fast enough to follow a slider."""
        episode = self.get_episode(episode_id)
        patient = type(episode.patient)(
            **(episode.patient.model_dump() | changes.model_dump(exclude_unset=True))
        )
        return self._report(episode.model_copy(update={"patient": patient}), Trigger.MANUAL)

    def _report(self, episode: Episode, trigger: Trigger) -> EvaluationReport:
        views, how, warnings = self._extras[episode.id]
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
        findings = tuple(
            sorted([*result.findings, *(df.finding for df in ddi_findings)], key=_sort_key)
        )
        status = result.status
        if ddi_crashed:
            # Same contract as a failed engine check: a partial run is INCOMPLETE, never OK.
            status = EvaluationStatus.INCOMPLETE
        elif status is EvaluationStatus.OK and any(f.outcome is not Outcome.PASS for f in findings):
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
        return report

    def _ddi_checks(self, episode: Episode) -> tuple[tuple[DDIFinding, ...], bool]:
        """Medication-pair interaction lookup. No provider means no DDI check at all; any
        failure is reported as a crashed check (evaluation INCOMPLETE), never swallowed."""
        if self.ddi is None:
            return (), False
        try:
            checks = check_pairs(episode, self.ddi)
        except Exception:  # noqa: BLE001 - defensive; check_pairs catches per pair
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
                    finding.outcome is not Outcome.PASS and finding.severity is Severity.MODERATE
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
        if request.episode_id != evaluation.episode_id:
            raise ReviewError("Review episode_id does not match the evaluation episode.")
        review = Review(id=uuid.uuid4().hex, at=self.clock(), **request.model_dump())
        entry = apply_review(evaluation, review)  # raises ReviewError if not acceptable
        self.audit.append(entry)
        self._reviews.append(review)
        return entry

    def treatment_plans_for_evaluation(
        self, evaluation_id: str
    ) -> tuple[TreatmentPlanSignOff, ...]:
        self.get_evaluation(evaluation_id)
        return tuple(
            reversed(
                [plan for plan in self._treatment_plans if plan.evaluation_id == evaluation_id]
            )
        )

    def latest_treatment_plan(self, evaluation_id: str) -> TreatmentPlanSignOff:
        plans = self.treatment_plans_for_evaluation(evaluation_id)
        if not plans:
            raise NotFoundError(f"No treatment plan for evaluation {evaluation_id}")
        return plans[0]

    def sign_treatment_plan(
        self, evaluation_id: str, request: TreatmentPlanRequest
    ) -> TreatmentPlanSignOff:
        evaluation = self.get_evaluation(evaluation_id)
        episode = self.get_episode(evaluation.episode_id)
        fingerprint = request.model_dump_json()
        existing = self._plan_idempotency.get(request.idempotency_key)
        if existing:
            if existing[0] != fingerprint:
                raise ConflictError("Idempotency key was already used for a different plan.")
            return existing[1]

        episode_evaluations = [
            report for report in self._evaluations.values() if report.episode_id == episode.id
        ]
        if not episode_evaluations or episode_evaluations[-1].id != evaluation.id:
            raise ConflictError("A newer evaluation exists; review it before signing a plan.")
        prior = [plan for plan in self._treatment_plans if plan.evaluation_id == evaluation.id]
        if prior and request.supersedes_id != prior[-1].id:
            raise ConflictError("A signed plan exists; a revision must supersede the latest plan.")
        if request.supersedes_id and (not prior or request.supersedes_id != prior[-1].id):
            raise ConflictError("The superseded plan is not the latest plan for this evaluation.")

        now = self.clock()
        if request.phase is ReviewPhase.ANTIBIOTIC_TIMEOUT_48H:
            if evaluation.trigger is not Trigger.TIMEOUT_DUE:
                raise PlanError("A 48-hour plan requires a TIMEOUT_DUE evaluation.")
            if not prior and not is_timeout_due(episode, now, self._treatment_plans, self.catalog):
                raise PlanError("This episode is not currently due for a 48-hour review.")

        items, status = validate_plan(
            request,
            episode,
            evaluation,
            self.reviews_for_evaluation(evaluation.id),
            self.catalog,
        )
        narrative = self.plan_summarizer.summarize(items, status, now)
        plan = TreatmentPlanSignOff(
            id=f"PLAN-{uuid.uuid4().hex[:10]}",
            episode_id=episode.id,
            evaluation_id=evaluation.id,
            evaluation_inputs_hash=evaluation.inputs_hash,
            ruleset_version=evaluation.ruleset_version,
            phase=request.phase,
            status=status,
            items=items,
            other_medications=unchanged_non_antibiotics(episode, self.catalog),
            reviewer=request.reviewer,
            reviewer_role=request.reviewer_role,
            signed_at=now,
            version=len(prior) + 1,
            supersedes_id=request.supersedes_id,
            idempotency_key=request.idempotency_key,
            narrative=narrative,
        )
        action = "treatment_plan.superseded" if prior else "treatment_plan.signed"
        self.audit.append(
            AuditEntry(
                at=now,
                actor=plan.reviewer,
                action=action,
                entity="treatment_plan",
                entity_id=plan.id,
                payload=plan.model_dump(mode="json"),
            )
        )
        self._treatment_plans.append(plan)
        self._plan_idempotency[request.idempotency_key] = (fingerprint, plan)
        return plan

    def timeout_items(self) -> tuple[TimeoutItem, ...]:
        now = self.clock()
        items: list[TimeoutItem] = []
        for episode in self._episodes.values():
            start = first_antibiotic_start(episode, self.catalog)
            if start is None:
                continue
            drugs = [
                order.generic
                for order in episode.orders
                if order.generic and self.catalog.is_antibiotic(order.generic)
            ]
            completed = next(
                (
                    plan
                    for plan in reversed(self._treatment_plans)
                    if plan.episode_id == episode.id
                    and plan.phase is ReviewPhase.ANTIBIOTIC_TIMEOUT_48H
                ),
                None,
            )
            if completed:
                items.append(
                    TimeoutItem(
                        episode_id=episode.id,
                        patient_id=episode.patient.id,
                        setting=episode.setting.value,
                        antibiotic_name=", ".join(drugs),
                        started_at=start,
                        hours_elapsed=round((now - start).total_seconds() / 3600, 1),
                        status="REVIEWED",
                        evaluation_id=completed.evaluation_id,
                        plan_id=completed.id,
                        reviewed_at=completed.signed_at,
                        reviewed_by=completed.reviewer,
                    )
                )
            elif is_timeout_due(episode, now, self._treatment_plans, self.catalog):
                latest = next(
                    (
                        report
                        for report in reversed(tuple(self._evaluations.values()))
                        if report.episode_id == episode.id
                    ),
                    None,
                )
                items.append(
                    TimeoutItem(
                        episode_id=episode.id,
                        patient_id=episode.patient.id,
                        setting=episode.setting.value,
                        antibiotic_name=", ".join(drugs),
                        started_at=start,
                        hours_elapsed=round((now - start).total_seconds() / 3600, 1),
                        status="REVIEW_DUE",
                        evaluation_id=latest.id if latest else None,
                    )
                )
        return tuple(items)

    def timeout_due(self) -> list[dict]:
        return [
            item.model_dump(mode="json")
            for item in self.timeout_items()
            if item.status == "REVIEW_DUE"
        ]


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
