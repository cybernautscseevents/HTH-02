"""Prescription image -> OCR -> drugs.py normalization -> DrugOrder -> evaluate_episode."""

import pytest

from backend.stewardship.drugs import Catalog
from backend.stewardship.episode import evaluate_episode
from backend.stewardship.renal import RenalDosing
from backend.stewardship.schemas import EvaluationStatus, NormStatus, Outcome, Route, Trigger
from prescription_ocr.orders import dose_mg, doses_per_day, duration_days, read_orders, route
from prescription_ocr.pipeline import read_prescription
from prescription_ocr.types import OcrResult

from .fakes import T0, FakeRulePack, episode, patient

TRANSCRIPT = """Patient: R. Sharma Age 45
Diagnosis: Acute cystitis
Rx
1. Tab Ciprofloxacin 500 mg BD x 3 days
2. Cap Nitrofurntoin 100 mg 1-0-1 x 5 days
3. Tab Paracetamol 650 mg SOS
Follow up after 5 days"""


class FakeEngine:
    """Stands in for GlmOcrEngine; returns a fixed transcript without loading the model."""

    def __init__(self, text: str = TRANSCRIPT) -> None:
        self.text = text
        self.images: list[str] = []

    def transcribe(self, image):
        self.images.append(str(image))
        return OcrResult(self.text, self.text, "fake-ocr", "test", "cpu", "float32", 0.0)


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.load()


def ocr(text: str) -> OcrResult:
    return OcrResult(text, text, "fake-ocr", "test", "cpu", "float32", 0.0)


# --- Field parsing: only unambiguous notation is read ---


@pytest.mark.parametrize(
    ("strength", "expected"),
    [
        ("500 mg", 500.0),
        ("1 g", 1000.0),
        ("1gm", 1000.0),
        ("500/125 mg", None),
        ("5 ml", None),
        ("0 mg", None),  # a zero dose is not a dose; R3 cannot assess it
        ("0.0 g", None),
        ("1,000 mg", None),  # thousands or decimal comma depends on the writer: not read
        ("1,5 g", None),
    ],
)
def test_dose_mg(strength, expected):
    assert dose_mg(strength) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Tab X 500 mg BD", 2.0),
        ("Tab X 500 mg TDS", 3.0),
        ("Tab X 1-0-1", 2.0),
        ("Inj X 1 g q8h", 3.0),
        ("Inj X 1 g 12 hourly", 2.0),
        ("Tab X 650 mg SOS", None),
        ("Tab X 500 mg BD 1-1-1", None),  # two readings disagree
        ("Tab X 500 mg", None),
        ("X 500 mg PO DAILY", 1.0),
        ("X 500 mg daily x 5 days", 1.0),
        ("Inj X 1 g q8hr", 3.0),
        ("Inj X 1 g q8hrs", 3.0),
        ("Inj X 1 g q 8 hour", 3.0),
        ("Inj X 1 g q 12 hours", 2.0),
        ("Tab X 500 mg twice daily", 2.0),  # "daily" here is not a second, once-daily reading
        ("Tab X 1-0-1 daily", 2.0),
        ("Tab X 500 mg 2 times daily", None),  # counts are not read beside "daily"
        ("Tab X 500 mg 1xDaily", None),
        ("Tab X 500 mg daily PRN", None),
    ],
)
def test_doses_per_day(text, expected):
    assert doses_per_day(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("x 5 days", 5), ("for 1 week", 7), ("5 days then 7 days", None), ("BD", None)],
)
def test_duration_days(text, expected):
    assert duration_days(text) == expected


def test_route():
    assert route("Inj X 1 g IV OD", "injection") is Route.IV
    assert route("Inj X 1 g", "injection") is None  # IV or IM not written
    assert route("Tab X 500 mg", "tablet") is Route.PO
    assert route("X 500 mg IV IM", None) is None


# --- OCR uncertainty is preserved, never turned into a drug ---


def test_exact_name_becomes_an_identified_order(catalog):
    (reading,) = read_orders(
        ocr("Tab Ciprofloxacin 500 mg BD x 3 days"), catalog, started_at=T0
    ).readings
    o = reading.order
    assert (o.norm_status, o.generic) == (NormStatus.ACCEPTED, "ciprofloxacin")
    assert (o.dose_mg, o.freq_per_day, o.route, o.duration_days) == (500.0, 2.0, Route.PO, 3)
    assert o.raw_text == "Tab Ciprofloxacin 500 mg BD x 3 days"


def test_indian_brand_from_ocr_uses_person2_catalog(catalog):
    (reading,) = read_orders(
        ocr("Tab Augmentin 625 Duo 1-0-1 x 5 days"), catalog, started_at=T0
    ).readings
    assert reading.order.generic == "amoxicillin/clavulanic acid"
    assert reading.order.dose_mg is None  # "625" has no unit and is a combination
    assert "india-pharma.gsk.com" in reading.reason


def test_misread_name_is_ambiguous_with_candidates(catalog):
    (reading,) = read_orders(ocr("Cap Nitrofurntoin 100 mg BD"), catalog, started_at=T0).readings
    assert reading.order.norm_status is NormStatus.AMBIGUOUS
    assert reading.order.generic is None
    assert "nitrofurantoin" in reading.order.norm_candidates


def test_unknown_name_is_no_match(catalog):
    (reading,) = read_orders(ocr("Tab Zzqx 10 mg OD"), catalog, started_at=T0).readings
    assert (reading.order.norm_status, reading.order.generic) == (NormStatus.NO_MATCH, None)


def test_non_medicine_lines_are_kept_for_review(catalog):
    reading = read_orders(ocr(TRANSCRIPT), catalog, started_at=T0)
    assert "Diagnosis: Acute cystitis" in reading.unparsed_lines
    assert "Follow up after 5 days" in reading.unparsed_lines
    assert len(reading.orders) == 3


def test_empty_transcript_warns(catalog):
    reading = read_orders(ocr(""), catalog, started_at=T0)
    assert reading.orders == ()
    assert reading.warnings


# --- End to end ---


def test_image_to_evaluate_episode(catalog):
    engine = FakeEngine()
    reading = read_prescription("rx-001.jpg", engine, catalog, started_at=T0)
    assert engine.images == ["rx-001.jpg"]

    result = evaluate_episode(
        episode(orders=reading.orders, syndrome_code="cystitis", patient=patient()),
        now=T0,
        trigger=Trigger.NEW_PRESCRIPTION,
        rulepack=FakeRulePack(),
        catalog=catalog,
        renal=RenalDosing.load(),
    )

    cipro, nitro, para = reading.orders
    findings = {(f.rule_id, f.order_id): f for f in result.findings}
    # Identified order is checked by every rule.
    assert findings[("R0_IDENTIFIED", cipro.id)].outcome is Outcome.PASS
    assert findings[("R2_AWARE", cipro.id)].outcome is Outcome.FLAG  # Watch; Access first-line
    assert findings[("R3_DOSE", cipro.id)].outcome is Outcome.PASS
    assert findings[("R5_DURATION", cipro.id)].outcome is Outcome.PASS
    # A misread name stops at R0 and is never checked as a guessed drug.
    only = [f for f in result.findings if f.order_id == nitro.id]
    assert [(f.rule_id, f.outcome) for f in only] == [("R0_IDENTIFIED", Outcome.CANNOT_ASSESS)]
    # A known non-antibiotic is identified and no stewardship rule runs on it.
    only = [f for f in result.findings if f.order_id == para.id]
    assert [(f.rule_id, f.outcome) for f in only] == [("R0_IDENTIFIED", Outcome.PASS)]
    assert findings[("R0_IDENTIFIED", nitro.id)].suggestion.action == "confirm_drug"
    assert result.status is EvaluationStatus.FLAGGED


def test_ocr_engine_failure_propagates(catalog):
    from prescription_ocr.glm import GlmOcrError

    class BrokenEngine:
        def transcribe(self, image):
            raise GlmOcrError("image not found: missing.jpg")

    with pytest.raises(GlmOcrError):
        read_prescription("missing.jpg", BrokenEngine(), catalog, started_at=T0)
