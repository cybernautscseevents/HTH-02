"""Presentation-only summaries of signed antibiotic plans.

The structured plan is authoritative. Narrative text never feeds back into clinical state.
"""

import logging
import re
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Protocol

from .schemas import (
    MedicationDisposition,
    MedicationPlanItem,
    NarrativeSource,
    PlanNarrative,
    TreatmentPlanStatus,
)

logger = logging.getLogger(__name__)
DISCLAIMER = "Explanatory summary only; the signed structured regimen is authoritative."


class PlanNarrativeSummarizer(Protocol):
    def summarize(
        self,
        items: Sequence[MedicationPlanItem],
        status: TreatmentPlanStatus,
        generated_at: datetime,
    ) -> PlanNarrative: ...


class TemplatePlanNarrativeSummarizer:
    def summarize(
        self,
        items: Sequence[MedicationPlanItem],
        status: TreatmentPlanStatus,
        generated_at: datetime,
    ) -> PlanNarrative:
        statements = [_item_sentence(item) for item in items]
        if status is TreatmentPlanStatus.ACTION_REQUIRED:
            statements.append("The plan has outstanding information or escalation actions.")
        return PlanNarrative(
            text=" ".join(statements),
            source=NarrativeSource.TEMPLATE,
            generator="rxguard-template-v1",
            generated_at=generated_at,
            disclaimer=DISCLAIMER,
        )


class OptionalLlmPlanNarrativeSummarizer:
    """Optional wording layer with deterministic fallback and conservative output checks."""

    def __init__(self, complete: Callable[[str], str], model: str = "injected") -> None:
        self._complete = complete
        self._model = model
        self._fallback = TemplatePlanNarrativeSummarizer()

    def summarize(
        self,
        items: Sequence[MedicationPlanItem],
        status: TreatmentPlanStatus,
        generated_at: datetime,
    ) -> PlanNarrative:
        fallback = self._fallback.summarize(items, status, generated_at)
        prompt = (
            "Rewrite this signed treatment-plan summary in concise clinical prose. "
            "Do not add recommendations, drugs, doses, dates, or claims of safety. "
            "The structured plan remains authoritative.\n" + fallback.text
        )
        try:
            text = self._complete(prompt).strip()
        except Exception:
            logger.exception("Plan narrative generation failed; using template")
            return fallback
        if not _acceptable(text, fallback.text):
            return fallback
        return PlanNarrative(
            text=text,
            source=NarrativeSource.LLM,
            generator=self._model,
            generated_at=generated_at,
            disclaimer=DISCLAIMER,
        )


def _item_sentence(item: MedicationPlanItem) -> str:
    drug = item.before.generic
    if item.disposition is MedicationDisposition.STOP:
        return f"Stop {drug}."
    if item.disposition is MedicationDisposition.REQUEST_INFO:
        requested = ", ".join(item.requested_inputs)
        return f"Further information is required for {drug}: {requested}."
    if item.disposition is MedicationDisposition.ESCALATE:
        return f"Escalate the {drug} decision to {item.escalation_destination}."
    regimen = item.final_regimen
    assert regimen is not None
    details = [
        f"{regimen.dose_mg:g} mg",
        regimen.route.value,
        f"{regimen.freq_per_day:g} times daily",
    ]
    if regimen.total_duration_days is not None:
        details.append(f"for {regimen.total_duration_days} days total")
    verb = {
        MedicationDisposition.CONTINUE: "Continue",
        MedicationDisposition.MODIFY: "Modify",
        MedicationDisposition.SWITCH: "Switch to",
    }[item.disposition]
    return f"{verb} {regimen.generic} " + ", ".join(details) + "."


def _acceptable(text: str, template: str) -> bool:
    if not text or re.search(r"\b(safe|safety|recommend(?:ed|ation)?)\b", text, re.I):
        return False
    return set(re.findall(r"\d+(?:\.\d+)?", text)) <= set(re.findall(r"\d+(?:\.\d+)?", template))
