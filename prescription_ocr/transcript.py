"""Multiline GLM transcript cleanup and medicine-line parsing."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

_MARKDOWN_FENCE = re.compile(r"^\s*```(?:text|markdown)?\s*$", re.IGNORECASE)
_PREAMBLE = re.compile(
    r"^\s*(?:the\s+(?:text|prescription|transcription)\s+(?:is|reads|says)|"
    r"(?:ocr|transcription)\s*(?:result|output)?|transcribed\s+text)\s*:\s*",
    re.IGNORECASE,
)
_PREFIX = re.compile(
    r"^\s*(?P<rx>(?:rx|℞)\s*[:.-]?\s*)?"
    r"(?:(?P<form>tab(?:let)?s?|t(?=\s|[.:-])|[j7]ab|jub|cap(?:sule)?s?|"
    r"syr(?:up)?|syp|inj(?:ection)?s?|cream|ointment|gel|drops?|"
    r"susp(?:ension)?|solution|inhaler|spray|lotion|"
    r"sachet|powder|pwd|mdi|neb(?:ule)?|amp(?:oule)?|vial)\s*[.:-]?\s*)?",
    re.IGNORECASE,
)
_STRENGTH = re.compile(
    r"\b(\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?\s*(?:mcg|mg|gm?|ml|iu|%)"
    r"(?:\s*/\s*\d+(?:\.\d+)?\s*(?:mcg|mg|gm?|ml|iu))?)\b",
    re.IGNORECASE,
)
_LIST_MARKER = re.compile(
    r"^\s*(?:[-*•▪◦]\s+|(?:\(?\d{1,2}\)?[.)-]|[①-⑳])\s*|"
    r"\$?\\textcircled\{\d{1,2}\}\$?\s*)"
)
_NON_MEDICINE = re.compile(
    r"^\s*(?:patient|name|age|sex|gender|date|address|doctor|dr\.|hospital|clinic|"
    r"allerg(?:y|ies)|history|complaints?|examination|findings?|diagnosis|"
    r"provisional|investigations?|advice|follow[- ]?up|signature|contact|time|"
    r"height|weight|bmi|bp|pulse|temperature|nutritional|screening|chief complaint|"
    r"significant history|past history|drug orders?|medications?|medicines?)\s*[:.-]?\s*$",
    re.IGNORECASE,
)
_NON_MEDICINE_START = re.compile(
    r"^\s*(?:patient|age|sex|gender|date|address|doctor|hospital|clinic|allerg(?:y|ies)|"
    r"history and complaints?|examination|provisional/?final diagnosis|nutritional screening|"
    r"advice|follow[- ]?up|investigations?|contact|signature|diet|lifestyle|rehab)\b",
    re.IGNORECASE,
)
_INSTRUCTION = re.compile(
    r"\b(?:od|bd|bid|tid|tds|qid|qds|hs|sos|prn|stat|daily|once|twice|thrice|morning|noon|"
    r"evening|night|after|before|with|without|food|meals?|days?|weeks?|months?|hourly|"
    r"iv|im|po|i\.v|i\.m|q\s*\d{1,2}\s*h|x\s*\d+|"
    r"\d+\s*[-x]\s*\d+(?:\s*[-x]\s*\d+)?|\d+\s*x\s*/?\s*day)\b.*$",
    re.IGNORECASE,
)
_INSTRUCTION_ONLY = re.compile(
    r"^\s*(?:take|apply|use|continue|stop|avoid|review|repeat|mix|drink|eat|"
    r"once|twice|thrice|daily|morning|night|before|after|for\s+\d+|\d+\s*(?:ml|drops?|puffs?|tabs?)\b)",
    re.IGNORECASE,
)
_CLINICAL_TEXT = re.compile(
    r"\b(?:normal|clear|pain|fever|headache|cough|constipation|infection|blood|"
    r"urine|serum|thyroid|haemoglobin|hemoglobin|platelet|creatinine|diagnosis|"
    r"negative|positive|complaint|symptoms?|test|report|rest at home)\b",
    re.IGNORECASE,
)
_TABLE_HEADER = re.compile(
    r"^(?:medicine|drug|brand|strength|dose|dosage|frequency|duration|route)(?:\s+(?:medicine|drug|brand|strength|dose|dosage|frequency|duration|route))*$",
    re.IGNORECASE,
)
_MULTI_MEDICINE_SPLIT = re.compile(
    r"\s*;\s*(?=(?:(?:rx|℞)\s*[:.-]?\s*)?(?:tab(?:let)?s?|"
    r"t(?=\s|[.:-])|[j7]ab|jub|cap(?:sule)?s?|syr(?:up)?|syp|"
    r"inj(?:ection)?s?|cream|ointment|gel|drops?|susp(?:ension)?|"
    r"solution|inhaler|spray|lotion|sachet|powder|pwd|mdi|neb(?:ule)?|amp(?:oule)?|vial)\b)",
    re.IGNORECASE,
)
_FORM_MAP = {
    "tab": "tablet",
    "tabs": "tablet",
    "tablet": "tablet",
    "tablets": "tablet",
    "t": "tablet",
    "jab": "tablet",
    "jub": "tablet",
    "7ab": "tablet",
    "cap": "capsule",
    "caps": "capsule",
    "capsule": "capsule",
    "capsules": "capsule",
    "syr": "syrup",
    "syrup": "syrup",
    "syp": "syrup",
    "inj": "injection",
    "injection": "injection",
    "injections": "injection",
    "cream": "cream",
    "ointment": "ointment",
    "gel": "gel",
    "drop": "drops",
    "drops": "drops",
    "susp": "suspension",
    "suspension": "suspension",
    "solution": "solution",
    "inhaler": "inhaler",
    "mdi": "inhaler",
    "spray": "spray",
    "lotion": "lotion",
    "sachet": "sachet",
    "powder": "powder",
    "pwd": "powder",
    "neb": "nebule",
    "nebule": "nebule",
    "amp": "ampoule",
    "ampoule": "ampoule",
    "vial": "vial",
}


@dataclass(frozen=True)
class ParsedLine:
    line_number: int
    raw_line: str
    medicine_text: str
    strength: str | None
    dosage_form: str | None
    has_medicine_marker: bool = False


def clean_glm_transcript(raw: str) -> str:
    """Remove response wrappers while preserving transcribed content and line breaks."""
    text = html.unescape(raw.replace("\r\n", "\n").replace("\r", "\n"))
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*/?\s*(?:tr|p|div|li|h[1-6])\b[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    cleaned: list[str] = []
    for line in text.split("\n"):
        if _MARKDOWN_FENCE.match(line):
            continue
        line = _PREAMBLE.sub("", line)
        line = re.sub(r"^\s*#{1,6}\s*", "", line)
        line = line.replace("**", "").replace("__", "").strip().strip('"')
        if line:
            cleaned.append(" ".join(line.split()))
    return "\n".join(cleaned)


def _expanded_lines(text: str):
    for line_number, raw in enumerate(text.splitlines(), start=1):
        original = raw.strip()
        if original.startswith("|"):
            cells = [cell.strip() for cell in original.strip("|").split("|")]
            if not cells or all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                continue
            original = " ".join(cell for cell in cells if cell)
            if _TABLE_HEADER.fullmatch(original):
                continue
        for segment in _MULTI_MEDICINE_SPLIT.split(original):
            if segment.strip():
                yield line_number, segment.strip()


def parse_prescription_lines(text: str) -> tuple[ParsedLine, ...]:
    results: list[ParsedLine] = []
    for line_number, original in _expanded_lines(text):
        if not original:
            continue
        has_list_marker = bool(_LIST_MARKER.match(original))
        line = _LIST_MARKER.sub("", original)
        line = re.sub(r"^[•*-]+\s*", "", line).strip()
        if not line or _NON_MEDICINE.match(line) or _NON_MEDICINE_START.match(line):
            continue
        if line.endswith(":") or _INSTRUCTION_ONLY.match(line):
            continue

        prefix = _PREFIX.match(line)
        form_token = prefix.group("form").casefold() if prefix and prefix.group("form") else None
        dosage_form = _FORM_MAP.get(form_token) if form_token else None
        has_rx_marker = bool(prefix and prefix.group("rx"))
        body = line[prefix.end() :] if prefix else line
        strength_match = _STRENGTH.search(body)
        strength = " ".join(strength_match.group(1).split()) if strength_match else None
        has_medicine_marker = has_rx_marker or dosage_form is not None or strength is not None
        has_line_structure = has_list_marker or has_medicine_marker

        medicine = _INSTRUCTION.sub("", body)
        medicine = _STRENGTH.sub(" ", medicine)
        medicine = re.sub(
            r"\([^)]*(?:mg|mcg|ml|gm?|iu|%)\b[^)]*\)", " ", medicine, flags=re.IGNORECASE
        )
        medicine = re.sub(r"\s+", " ", medicine).strip(" |,;:-.()[]")
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9+./-]*", medicine)
        if not tokens or not re.search(r"[A-Za-z]", medicine):
            continue
        if len(tokens) > 8:
            continue
        if _CLINICAL_TEXT.search(medicine) and dosage_form is None and strength is None:
            continue
        if not has_line_structure:
            if len(tokens) > 4 or re.search(r"\d", medicine):
                continue
            if any(len(token) == 1 for token in tokens) and len(tokens) > 2:
                continue
        results.append(
            ParsedLine(
                line_number,
                original,
                medicine,
                strength,
                dosage_form,
                has_medicine_marker,
            )
        )
    return tuple(results)
