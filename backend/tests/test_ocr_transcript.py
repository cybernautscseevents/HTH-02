"""Transcript cleanup, line parsing and image preparation (from PranamB21's OCR tests)."""

import pytest

from prescription_ocr.transcript import clean_glm_transcript, parse_prescription_lines


def test_cleanup_preserves_lines():
    raw = "The transcription is:\n```text\nTab Napa 500 mg\nCap Amox 250 mg\n```"
    assert clean_glm_transcript(raw) == "Tab Napa 500 mg\nCap Amox 250 mg"


def test_cleanup_converts_html_breaks_to_lines():
    raw = "<p>Medicines:</p><div>Tab Napa 500 mg<br>Cap Amox 250 mg</div>"
    assert clean_glm_transcript(raw) == "Medicines:\nTab Napa 500 mg\nCap Amox 250 mg"


def test_line_parser_extracts_context():
    (line,) = parse_prescription_lines("Tab Napa 500 mg BD x 5 days")
    assert (line.medicine_text, line.strength, line.dosage_form) == ("Napa", "500 mg", "tablet")


def test_parser_skips_headers_and_preserves_numeric_medicine_names():
    lines = parse_prescription_lines(
        "Patient: Jane Doe\n1. 5-Fluorouracil 500 mg\nSyr Cefixime 125 mg/5 mL BD"
    )
    assert [line.medicine_text for line in lines] == ["5-Fluorouracil", "Cefixime"]
    assert lines[1].strength == "125 mg/5 mL"


def test_parser_rejects_headers_clinical_text_and_instructions():
    lines = parse_prescription_lines(
        "History and complaints: headache\n"
        "Chest clear\n"
        "Take twice daily for 5 days\n"
        "Drug orders:\n"
        "1. Tab Montair 10 mg once daily"
    )
    assert [line.medicine_text for line in lines] == ["Montair"]
    assert lines[0].has_medicine_marker


def test_markdown_table_and_collapsed_medicine_lines_are_parsed():
    lines = parse_prescription_lines(
        "| Medicine | Strength |\n| --- | --- |\n| Tab Napa | 500 mg |\n"
        "Tab Napa 500 mg; Cap Amox 250 mg"
    )
    assert [(line.medicine_text, line.strength) for line in lines] == [
        ("Napa", "500 mg"),
        ("Napa", "500 mg"),
        ("Amox", "250 mg"),
    ]


def test_numbered_complaint_is_not_medicine_evidence():
    assert parse_prescription_lines("1. Headache") == ()


def test_common_ocr_form_variants_and_latex_markers_are_parsed():
    lines = parse_prescription_lines(
        "T. Clopitab 75 mg once daily\nJab Pansec 40 mg\n$\\textcircled{2}$ Emeset 4 mg"
    )
    assert [line.medicine_text for line in lines] == ["Clopitab", "Pansec", "Emeset"]
    assert all(line.dosage_form == "tablet" for line in lines[:2])


@pytest.mark.parametrize(
    "text",
    [
        "Tab Amoxicillin 500 mg TDS x 5 days",
        "Inj Amoxicillin 1 g IV OD",
        "Inj. Amoxicillin 1g i.v. q8h",
        "Amoxicillin 500 mg QDS",
    ],
)
def test_frequency_and_route_words_are_not_part_of_the_drug_name(text):
    (line,) = parse_prescription_lines(text)
    assert line.medicine_text == "Amoxicillin"


def test_small_image_is_upscaled_instead_of_rejected():
    image_module = pytest.importorskip("PIL.Image")
    from prescription_ocr.image import prepare_image

    prepared, warnings = prepare_image(image_module.new("L", (71, 15), "white"))
    assert prepared.mode == "RGB"
    assert min(prepared.size) >= 32
    assert "upscaled" in warnings[0].casefold()


def test_transparency_is_composited_on_white():
    image_module = pytest.importorskip("PIL.Image")
    from prescription_ocr.image import prepare_image

    prepared, _ = prepare_image(
        image_module.new("RGBA", (32, 32), (0, 0, 0, 0)), enhance_contrast=False
    )
    assert prepared.getpixel((0, 0)) == (255, 255, 255)


def test_empty_image_is_rejected():
    image_module = pytest.importorskip("PIL.Image")
    from prescription_ocr.image import prepare_image

    with pytest.raises(ValueError, match="positive"):
        prepare_image(image_module.new("RGB", (0, 10)))


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("Ampicillin 500 mg IV q6h", "Ampicillin"),
        ("Amphotericin B 50 mg IV OD", "Amphotericin B"),
        ("Capreomycin 1 g IM OD", "Capreomycin"),
        ("Gentamicin 80 mg IV q8h", "Gentamicin"),
    ],
)
def test_drug_name_starting_with_a_form_word_is_not_cut(text, name):
    (line,) = parse_prescription_lines(text)
    assert (line.medicine_text, line.dosage_form) == (name, None)


@pytest.mark.parametrize(
    ("text", "form"),
    [
        ("Amp Ampicillin 500 mg IV", "ampoule"),
        ("Amp. Ampicillin 500 mg IV", "ampoule"),
        ("Ampoule Ampicillin 500 mg IV", "ampoule"),
        ("Inj Ampicillin 500 mg IV", "injection"),
        ("Cap Amoxicillin 500 mg TDS", "capsule"),
    ],
)
def test_written_form_word_is_still_read(text, form):
    (line,) = parse_prescription_lines(text)
    assert (line.medicine_text, line.dosage_form) == (text.split()[1], form)


@pytest.mark.parametrize(
    ("text", "strength"),
    [("Vancomycin 1,000 mg IV q12h", "1,000 mg"), ("Ceftriaxone 1,5 g IV OD", "1,5 g")],
)
def test_comma_number_is_kept_whole_and_the_line_is_read(text, strength):
    (line,) = parse_prescription_lines(text)
    assert (line.medicine_text, line.strength) == (text.split()[0], strength)


def test_hour_words_are_not_part_of_the_drug_name():
    lines = parse_prescription_lines("Cefazolin 2 g q8hr\nCefazolin 2 g q 8 hour")
    assert [line.medicine_text for line in lines] == ["Cefazolin", "Cefazolin"]
