"""Qwen-VL OCR: structured output parsing, structured lines -> DrugOrder, and the full pipeline.

The model is never loaded here. A fake processor and model return canned text, so these tests
check what the engine and parsers do with whatever a model says, including bad output.
"""

import json

import pytest

from backend.stewardship.drugs import Catalog
from backend.stewardship.episode import evaluate_episode
from backend.stewardship.renal import RenalDosing
from backend.stewardship.schemas import EvaluationStatus, NormStatus, Outcome, Route, Trigger
from prescription_ocr.orders import read_orders
from prescription_ocr.pipeline import build_engine, read_prescription
from prescription_ocr.qwen import (
    QwenOcrError,
    QwenOutputError,
    QwenVlConfig,
    QwenVlEngine,
    parse_qwen_output,
)
from prescription_ocr.types import OcrResult, ReadLine

from .fakes import T0, FakeRulePack, episode, patient


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.load()


def answer(*medicines: dict) -> str:
    return json.dumps({"medicines": list(medicines)})


def med(as_written: str, **fields) -> dict:
    return {"as_written": as_written, "legible": True} | fields


def qwen_ocr(*lines: ReadLine) -> OcrResult:
    text = "\n".join(line.text for line in lines)
    return OcrResult(text, text, "fake-qwen", "test", "cpu", "float32", 0.0, lines=lines)


# --- Parsing the model's structured answer ---


def test_parses_all_fields():
    raw = answer(
        med(
            "Tab Ciprofloxacin 500 mg",
            dose="500 mg",
            frequency="BD",
            route="PO",
            duration="x 5 days",
        )
    )
    (line,), warnings = parse_qwen_output(raw)
    assert line == ReadLine(
        "Tab Ciprofloxacin 500 mg", "500 mg", "BD", "PO", "x 5 days", legible=True
    )
    assert warnings == ()


def test_missing_and_null_fields_stay_empty():
    raw = answer(
        med("Tab Azee", dose=None, frequency="", route="null", duration="N/A"),
        {"as_written": "Cap Foo", "legible": True},
    )
    lines, _ = parse_qwen_output(raw)
    for line in lines:
        assert (line.dose, line.frequency, line.route, line.duration) == (None,) * 4


def test_missing_legible_flag_is_not_trusted():
    (line,), _ = parse_qwen_output('{"medicines": [{"as_written": "Tab Foo 5 mg"}]}')
    assert line.legible is False


@pytest.mark.parametrize(
    ("flag", "expected"),
    [(True, True), ("true", True), ("false", False), (False, False), (1, False), (None, False)],
)
def test_legible_flag_values(flag, expected):
    (line,), _ = parse_qwen_output(answer({"as_written": "Tab Foo", "legible": flag}))
    assert line.legible is expected


def test_multiple_medicines_keep_their_order():
    raw = answer(med("Tab Amoxicillin 500 mg"), med("Syp Ostocalcium"), med("Inj Cefepime 1 g"))
    lines, _ = parse_qwen_output(raw)
    assert [line.as_written for line in lines] == [
        "Tab Amoxicillin 500 mg",
        "Syp Ostocalcium",
        "Inj Cefepime 1 g",
    ]


def test_code_fence_and_chatter_around_json_are_ignored():
    raw = "Here you go:\n```json\n" + answer(med("Tab Foo")) + "\n```\nHope that helps."
    (line,), _ = parse_qwen_output(raw)
    assert line.as_written == "Tab Foo"


def test_bare_list_is_accepted():
    (line,), _ = parse_qwen_output(json.dumps([med("Tab Foo")]))
    assert line.as_written == "Tab Foo"


def test_numbers_become_text():
    (line,), _ = parse_qwen_output(answer(med("Tab Foo", dose=500, frequency=2.5)))
    assert (line.dose, line.frequency) == ("500", "2.5")


def test_empty_medicine_list_is_valid_not_an_error():
    lines, _ = parse_qwen_output('{"medicines": []}')
    assert lines == ()


def test_entries_without_a_name_are_dropped_with_a_warning():
    raw = answer(med("Tab Foo"), {"dose": "5 mg"}, "Tab Bar", {"as_written": "  "})
    lines, warnings = parse_qwen_output(raw)
    assert [line.as_written for line in lines] == ["Tab Foo"]
    assert "3 entries" in warnings[0]


def test_repeated_entries_are_collapsed():
    lines, _ = parse_qwen_output(answer(*[med("Tab Foo", frequency="BD")] * 5))
    assert len(lines) == 1


@pytest.mark.parametrize(
    "raw", ["", "I cannot read this image.", "{not json", '{"medicines": 3}', '{"other": []}']
)
def test_unparseable_output_raises(raw):
    with pytest.raises(QwenOutputError):
        parse_qwen_output(raw)


def test_truncated_output_keeps_only_complete_lines():
    full = answer(med("Tab Foo", frequency="BD"), med("Tab Bar", frequency="TDS"))
    truncated = full[: full.rindex("Tab Bar") + 4]  # cut inside the second entry
    lines, warnings = parse_qwen_output(truncated)
    assert [line.as_written for line in lines] == ["Tab Foo"]
    assert "recovered 1" in warnings[0]


# --- Structured lines -> catalog -> DrugOrder ---


def read(catalog, *lines: ReadLine):
    return read_orders(qwen_ocr(*lines), catalog, started_at=T0)


def test_exact_generic_with_all_fields(catalog):
    reading = read(
        catalog,
        ReadLine("Tab Ciprofloxacin 500 mg", "500 mg", "BD", None, "x 3 days"),
    )
    (o,) = reading.orders
    assert (o.norm_status, o.generic) == (NormStatus.ACCEPTED, "ciprofloxacin")
    assert (o.dose_mg, o.freq_per_day, o.route, o.duration_days) == (500.0, 2.0, Route.PO, 3)


def test_indian_brand_goes_through_the_existing_catalog(catalog):
    (reading,) = read(
        catalog, ReadLine("Syp Augmentin DDS", None, "twice daily", None, "7 days")
    ).readings
    assert reading.order.generic == "amoxicillin/clavulanic acid"
    assert reading.order.brand == "augmentin"
    assert reading.order.freq_per_day == 2.0
    assert reading.order.duration_days == 7
    assert "india-pharma.gsk.com" in reading.reason


def test_missing_directions_stay_empty_for_the_rules(catalog):
    (o,) = read(catalog, ReadLine("Inj Cefepime")).orders
    assert o.generic == "cefepime"
    assert (o.dose_mg, o.freq_per_day, o.route, o.duration_days) == (None, None, None, None)


def test_misread_name_is_ambiguous_never_chosen(catalog):
    (o,) = read(catalog, ReadLine("Cap Nitrofurntoin 100 mg", None, "BD")).orders
    assert o.norm_status is NormStatus.AMBIGUOUS
    assert o.generic is None
    assert "nitrofurantoin" in o.norm_candidates


def test_unknown_name_is_no_match(catalog):
    (o,) = read(catalog, ReadLine("Tab Zzqx 10 mg")).orders
    assert (o.norm_status, o.generic) == (NormStatus.NO_MATCH, None)


def test_illegible_line_makes_no_order_and_is_reported(catalog):
    reading = read(
        catalog,
        ReadLine("Tab Ciprofloxacin 500 mg", frequency="BD"),
        ReadLine("Tab Cefxm??", legible=False),
    )
    assert [o.generic for o in reading.orders] == ["ciprofloxacin"]
    assert reading.uncertain_lines == ("Tab Cefxm??",)
    assert any("could not be read confidently" in w for w in reading.warnings)


def test_uncertain_line_can_become_an_order_but_is_never_accepted(catalog):
    ocr = qwen_ocr(ReadLine("Tab Ciprofloxacin 500 mg", frequency="BD", legible=False))
    reading = read_orders(ocr, catalog, started_at=T0, uncertain_as_orders=True)
    (o,) = reading.orders
    assert (o.norm_status, o.generic) == (NormStatus.AMBIGUOUS, None)
    assert o.norm_candidates == ("ciprofloxacin",)
    assert o.freq_per_day == 2.0  # directions are still read
    assert reading.uncertain_lines == ()
    assert "confirm the drug" in reading.readings[0].reason
    assert any("need confirmation" in w for w in reading.warnings)


def test_uncertain_misread_stays_unidentified_when_made_an_order(catalog):
    ocr = qwen_ocr(ReadLine("Tab Zzqx 10 mg", legible=False))
    (o,) = read_orders(ocr, catalog, started_at=T0, uncertain_as_orders=True).orders
    assert (o.norm_status, o.generic) == (NormStatus.NO_MATCH, None)


def test_only_illegible_lines_do_not_claim_there_were_no_medicines(catalog):
    reading = read(catalog, ReadLine("???", legible=False))
    assert reading.orders == ()
    assert not any("No medicine lines" in w for w in reading.warnings)


def test_no_medicines_warns(catalog):
    reading = read_orders(qwen_ocr(), catalog, started_at=T0)
    assert reading.orders == ()
    assert any("No medicine lines" in w for w in reading.warnings)


def test_field_that_disagrees_with_the_written_line_is_left_empty(catalog):
    (o,) = read(
        catalog, ReadLine("Tab Ciprofloxacin 500 mg BD", frequency="TDS", route="IV")
    ).orders
    assert o.freq_per_day is None  # BD in the name, TDS in the field
    assert o.route is None  # IV in the field, tablet in the name


def test_agreeing_field_and_line_are_both_fine(catalog):
    (o,) = read(catalog, ReadLine("Tab Ciprofloxacin 500 mg BD", "500 mg", "twice daily")).orders
    assert (o.dose_mg, o.freq_per_day) == (500.0, 2.0)


def test_unitless_or_combination_strength_is_not_a_dose(catalog):
    (o,) = read(catalog, ReadLine("Tab Augmentin 625", "625", "1 BD")).orders
    assert o.generic == "amoxicillin/clavulanic acid"
    assert o.dose_mg is None


def test_brand_outside_the_catalog_is_not_guessed(catalog):
    (o,) = read(catalog, ReadLine("Tab Ciplox 500", "500", "1 BD")).orders
    assert (o.norm_status, o.generic) == (NormStatus.NO_MATCH, None)


def test_several_medicines_in_one_entry_are_split(catalog):
    reading = read(catalog, ReadLine("Tab Ciprofloxacin 500 mg BD; Cap Amoxicillin 500 mg TDS"))
    assert [o.generic for o in reading.orders] == ["ciprofloxacin", "amoxicillin"]
    assert [o.freq_per_day for o in reading.orders] == [2.0, 3.0]
    assert any("more than one medicine" in w for w in reading.warnings)


def test_two_brands_joined_by_plus_are_not_accepted(catalog):
    (o,) = read(catalog, ReadLine("Augmentin 625 + Metrogyl 400")).orders
    assert o.norm_status is NormStatus.AMBIGUOUS
    assert o.generic is None


def test_order_ids_are_unique_and_sequential(catalog):
    reading = read(catalog, ReadLine("Tab A1"), ReadLine("x", legible=False), ReadLine("Tab B1"))
    assert [o.id for o in reading.orders] == ["rx-1", "rx-2"]


# --- Engine with a fake model ---


class FakeInputs(dict):
    def __init__(self):
        super().__init__(input_ids=FakeIds())


class FakeIds:
    shape = (1, 3)


class FakeProcessor:
    def __init__(self, reply: str):
        self.reply = reply
        self.messages = None

    def apply_chat_template(self, messages, **kwargs):
        self.messages = messages
        return FakeInputs()

    def decode(self, ids, skip_special_tokens=True):
        return self.reply


class FakeModel:
    def generate(self, **kwargs):
        return [[0, 1, 2, 3, 4]]


def fake_engine(reply: str) -> QwenVlEngine:
    return QwenVlEngine(
        QwenVlConfig(quantization="none"), processor=FakeProcessor(reply), model=FakeModel()
    )


def image():
    return pytest.importorskip("PIL.Image").new("RGB", (64, 64), "white")


def test_engine_returns_structured_lines_and_a_readable_transcript():
    engine = fake_engine(answer(med("Tab Ciplox 500", frequency="BD")))
    result = engine.transcribe(image())
    assert result.lines == (ReadLine("Tab Ciplox 500", None, "BD", None, None, True),)
    assert result.text == "Tab Ciplox 500 BD"
    assert result.model_id == "Qwen/Qwen2.5-VL-3B-Instruct"


def test_engine_prompt_forbids_normalizing_and_inventing():
    engine = fake_engine(answer())
    engine.transcribe(image())
    prompt = engine.processor.messages[0]["content"][1]["text"]
    assert "Never invent" in prompt
    assert "Do not correct" in prompt


def test_engine_raises_on_garbage_instead_of_returning_an_empty_prescription():
    with pytest.raises(QwenOutputError):
        fake_engine("Sorry, I can't help with that.").transcribe(image())


def test_engine_rejects_a_missing_image(tmp_path):
    with pytest.raises(QwenOcrError, match="image not found"):
        fake_engine(answer()).transcribe(tmp_path / "missing.jpg")


def test_config_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("HC03_QWEN_MODEL", "Qwen/Some-Other-VL")
    monkeypatch.setenv("HC03_QWEN_QUANT", "8bit")
    monkeypatch.setenv("HC03_QWEN_MAX_PIXELS", "500000")
    config = QwenVlConfig()
    assert (config.model_id, config.quantization, config.max_pixels) == (
        "Qwen/Some-Other-VL",
        "8bit",
        500000,
    )


def test_bad_config_values_are_rejected():
    with pytest.raises(ValueError):
        QwenVlConfig(quantization="2bit")
    with pytest.raises(ValueError):
        QwenVlConfig(min_pixels=10, max_pixels=5)


def test_build_engine_selects_by_name():
    assert isinstance(build_engine("qwen"), QwenVlEngine)
    with pytest.raises(ValueError, match="unknown OCR engine"):
        build_engine("tesseract")


# --- Full pipeline: Qwen-style output -> catalog -> DrugOrder -> evaluate_episode ---

REPLY = answer(
    med("Tab Ciprofloxacin 500 mg", dose="500 mg", frequency="BD", duration="x 3 days"),
    med("Cap Nitrofurntoin 100 mg", frequency="1-0-1", duration="5 days"),
    med("Tab Paracetamol 650 mg", frequency="SOS"),
    med("Tab C??ft", legible=False),
)


def test_qwen_reading_through_evaluate_episode(catalog):
    reading = read_prescription(
        "rx-001.jpg", _ImageStub(fake_engine(REPLY)), catalog, started_at=T0
    )
    cipro, nitro, para = reading.orders
    assert reading.uncertain_lines == ("Tab C??ft",)

    result = evaluate_episode(
        episode(orders=reading.orders, syndrome_code="cystitis", patient=patient()),
        now=T0,
        trigger=Trigger.NEW_PRESCRIPTION,
        rulepack=FakeRulePack(),
        catalog=catalog,
        renal=RenalDosing.load(),
    )
    findings = {(f.rule_id, f.order_id): f for f in result.findings}
    # The identified drug is checked by every rule on the values the model read.
    assert findings[("R0_IDENTIFIED", cipro.id)].outcome is Outcome.PASS
    assert findings[("R3_DOSE", cipro.id)].outcome is Outcome.PASS  # 500 mg x 2/day
    assert findings[("R5_DURATION", cipro.id)].outcome is Outcome.PASS  # 3 days
    # The misread name and the non-antibiotic stop at R0 and are never checked as a guess.
    for unsure in (nitro, para):
        only = [f for f in result.findings if f.order_id == unsure.id]
        assert [(f.rule_id, f.outcome) for f in only] == [("R0_IDENTIFIED", Outcome.CANNOT_ASSESS)]
    assert findings[("R0_IDENTIFIED", nitro.id)].suggestion.action == "confirm_drug"
    assert result.status is EvaluationStatus.FLAGGED


def test_missing_directions_become_cannot_assess_in_the_rules(catalog):
    reading = read(catalog, ReadLine("Tab Ciprofloxacin"))
    result = evaluate_episode(
        episode(orders=reading.orders, syndrome_code="cystitis", patient=patient()),
        now=T0,
        trigger=Trigger.NEW_PRESCRIPTION,
        rulepack=FakeRulePack(),
        catalog=catalog,
        renal=RenalDosing.load(),
    )
    outcomes = {f.rule_id: f.outcome for f in result.findings}
    assert outcomes["R3_DOSE"] is Outcome.CANNOT_ASSESS
    assert outcomes["R5_DURATION"] is Outcome.CANNOT_ASSESS


class _ImageStub:
    """Lets a fake engine take a path without a real image file."""

    def __init__(self, engine: QwenVlEngine):
        self.engine = engine

    def transcribe(self, image):
        return self.engine.transcribe(_blank())


def _blank():
    return pytest.importorskip("PIL.Image").new("RGB", (64, 64), "white")
