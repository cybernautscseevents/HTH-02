from backend.stewardship.narrative import (
    OptionalLlmPlanNarrativeSummarizer,
    TemplatePlanNarrativeSummarizer,
)
from backend.stewardship.schemas import (
    MedicationDisposition,
    MedicationPlanItem,
    NarrativeSource,
    RegimenSnapshot,
    Route,
    TreatmentPlanStatus,
)

from .fakes import T0


def item() -> MedicationPlanItem:
    regimen = RegimenSnapshot(
        source_order_id="rx-1",
        generic="amoxicillin",
        dose_mg=500,
        freq_per_day=3,
        route=Route.PO,
        total_duration_days=5,
        course_started_at=T0,
    )
    return MedicationPlanItem(
        source_order_id="rx-1",
        disposition=MedicationDisposition.CONTINUE,
        before=regimen,
        final_regimen=regimen,
    )


def test_template_narrative_uses_only_signed_plan_facts():
    narrative = TemplatePlanNarrativeSummarizer().summarize([item()], TreatmentPlanStatus.READY, T0)
    assert narrative.source is NarrativeSource.TEMPLATE
    assert "amoxicillin 500 mg, PO, 3 times daily, for 5 days total" in narrative.text
    assert "authoritative" in narrative.disclaimer


def test_optional_narrative_falls_back_on_failure_or_unsupported_claim():
    def broken(_prompt):
        raise RuntimeError("offline")

    failed = OptionalLlmPlanNarrativeSummarizer(broken).summarize(
        [item()], TreatmentPlanStatus.READY, T0
    )
    unsafe = OptionalLlmPlanNarrativeSummarizer(
        lambda _prompt: "This is safe and recommended."
    ).summarize([item()], TreatmentPlanStatus.READY, T0)
    assert failed.source is NarrativeSource.TEMPLATE
    assert unsafe.source is NarrativeSource.TEMPLATE


def test_optional_narrative_cannot_mutate_structured_plan():
    original = item()
    narrative = OptionalLlmPlanNarrativeSummarizer(
        lambda _prompt: "Continue amoxicillin 500 mg PO 3 times daily for 5 days."
    ).summarize([original], TreatmentPlanStatus.READY, T0)
    assert narrative.source is NarrativeSource.LLM
    assert original.final_regimen.generic == "amoxicillin"
    assert original.final_regimen.dose_mg == 500
