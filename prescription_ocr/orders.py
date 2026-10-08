"""Turn an OCR transcript into DrugOrders for the stewardship engine.

The drug name on each medicine line goes through the stewardship drug catalog
(backend.stewardship.drugs.Catalog.normalize), so OCR never decides a drug's identity: a misread
name stays AMBIGUOUS or NO_MATCH and rule R0 asks a person to confirm it.

Dose, frequency, route and duration are read only from unambiguous notation (for example
"500 mg", "BD", "1-0-1", "x 5 days", "IV"). Anything else, or two readings that disagree, is
left empty so the rules return CANNOT_ASSESS instead of checking a guessed value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime

from backend.stewardship.drugs import Catalog
from backend.stewardship.schemas import DrugOrder, NormStatus, Route
from prescription_ocr.transcript import ParsedLine, parse_prescription_lines
from prescription_ocr.types import OcrResult, ReadLine

_SINGLE_STRENGTH = re.compile(r"^(\d+(?:\.\d+)?)\s*(mg|gm?)$", re.IGNORECASE)
_FREQUENCY_WORDS = {
    1: r"od|once\s+(?:a\s+)?daily|once\s+a\s+day|hs",
    2: r"bd|bid|twice\s+(?:a\s+)?daily|twice\s+a\s+day",
    3: r"tds|tid|thrice\s+(?:a\s+)?daily|thrice\s+a\s+day",
    4: r"qid|qds",
}
_AS_NEEDED = re.compile(r"\b(?:sos|prn|as\s+needed|stat)\b", re.IGNORECASE)
_MEAL_PATTERN = re.compile(r"(?<![\d/.-])([0-4])\s*-\s*([0-4])\s*-\s*([0-4])(?![\d/.-])")
_HOURLY = re.compile(r"\b(?:q\s*(\d{1,2})\s*h|(\d{1,2})\s*(?:-\s*)?hourly)\b", re.IGNORECASE)
_DURATION = re.compile(r"\b(\d{1,3})\s*(days?|weeks?|wks?)\b", re.IGNORECASE)
_ROUTE_WORDS = {
    Route.IV: r"iv|i\.v\.?|intravenous(?:ly)?",
    Route.IM: r"im|i\.m\.?|intramuscular(?:ly)?",
    Route.PO: r"po|p\.o\.?|oral(?:ly)?|by\s+mouth",
}
_ORAL_FORMS = frozenset({"tablet", "capsule", "syrup", "suspension", "sachet"})


def _single(values: set) -> object | None:
    """The value when exactly one distinct reading was found, else None."""
    return next(iter(values)) if len(values) == 1 else None


def dose_mg(strength: str | None) -> float | None:
    """Single-ingredient strength in mg ("500 mg", "1 g"); None for combinations or other units."""
    match = _SINGLE_STRENGTH.match((strength or "").strip())
    if not match:
        return None
    amount = float(match.group(1))
    return amount * 1000 if match.group(2).lower().startswith("g") else amount


def doses_per_day(text: str) -> float | None:
    """Doses per day from standard notation; None if absent, as-needed or conflicting."""
    if _AS_NEEDED.search(text):
        return None
    found: set[float] = set()
    for count, pattern in _FREQUENCY_WORDS.items():
        if re.search(rf"\b(?:{pattern})\b", text, re.IGNORECASE):
            found.add(float(count))
    for match in _MEAL_PATTERN.finditer(text):
        total = sum(int(n) for n in match.groups())
        if total:
            found.add(float(total))
    for match in _HOURLY.finditer(text):
        hours = int(match.group(1) or match.group(2))
        if hours and 24 % hours == 0:
            found.add(24.0 / hours)
    return _single(found)


def duration_days(text: str) -> int | None:
    """Planned duration in days ("x 5 days", "for 1 week"); None if absent or conflicting."""
    found = {
        int(n) * (7 if unit.lower().startswith("w") else 1) for n, unit in _DURATION.findall(text)
    }
    return _single(found)


def route(text: str, dosage_form: str | None) -> Route | None:
    """Route written on the line, else implied by an oral dosage form; injections need IV or IM."""
    written = {
        r for r, pattern in _ROUTE_WORDS.items() if re.search(rf"\b(?:{pattern})(?!\w)", text, re.I)
    }
    if written:
        return _single(written)
    return Route.PO if dosage_form in _ORAL_FORMS else None


@dataclass(frozen=True)
class OrderReading:
    """One medicine line as read from the image, and the order built from it."""

    line_number: int
    raw_line: str
    order: DrugOrder
    reason: str


@dataclass(frozen=True)
class PrescriptionReading:
    """Everything read from one prescription image, kept for human review."""

    ocr: OcrResult
    readings: tuple[OrderReading, ...]
    unparsed_lines: tuple[str, ...]
    warnings: tuple[str, ...]
    # Lines a vision model marked not legible. They are reported, never turned into orders.
    uncertain_lines: tuple[str, ...] = ()

    @property
    def orders(self) -> tuple[DrugOrder, ...]:
        return tuple(r.order for r in self.readings)


def build_order(
    line: ParsedLine, catalog: Catalog, *, order_id: str, started_at: datetime
) -> OrderReading:
    """Build a DrugOrder from one parsed medicine line."""
    name = catalog.normalize(line.medicine_text)
    order = DrugOrder(
        id=order_id,
        raw_text=line.raw_line,
        generic=name.generic,
        brand=name.brand,
        norm_status=name.status,
        norm_candidates=name.candidates,
        dose_mg=dose_mg(line.strength),
        freq_per_day=doses_per_day(line.raw_line),
        route=route(line.raw_line, line.dosage_form),
        duration_days=duration_days(line.raw_line),
        started_at=started_at,
    )
    return OrderReading(line.line_number, line.raw_line, order, name.reason)


def _agree(field_value, line_value):
    """A value read from both a structured field and the written line must match.

    One source alone is used as is. Two sources that disagree give None, so the rule returns
    CANNOT_ASSESS instead of checking a guess.
    """
    if field_value is None:
        return line_value
    return field_value if line_value in (None, field_value) else None


def build_order_from_read_line(
    read: ReadLine, catalog: Catalog, *, number: int, order_id: str, started_at: datetime
) -> OrderReading:
    """Build a DrugOrder from one structured line. Identity still comes only from the catalog."""
    parsed = parse_prescription_lines(read.as_written)
    base = parsed[0] if parsed else ParsedLine(number, read.as_written, read.as_written, None, None)
    name = catalog.normalize(base.medicine_text)
    text = read.text
    order = DrugOrder(
        id=order_id,
        raw_text=text,
        generic=name.generic,
        brand=name.brand,
        norm_status=name.status,
        norm_candidates=name.candidates,
        dose_mg=_agree(dose_mg(read.dose), dose_mg(base.strength)),
        freq_per_day=_agree(doses_per_day(read.frequency or ""), doses_per_day(read.as_written)),
        route=_agree(route(read.route or "", None), route(read.as_written, base.dosage_form)),
        duration_days=_agree(duration_days(read.duration or ""), duration_days(read.as_written)),
        started_at=started_at,
    )
    return OrderReading(number, text, order, name.reason)


def _needs_confirmation(reading: OrderReading) -> OrderReading:
    """An order from a line the model could not read confidently is never accepted on its own.

    A name that matches the catalog exactly is still only a candidate: a person confirms it.
    """
    order = reading.order
    if order.norm_status is not NormStatus.ACCEPTED:
        return reading
    held = order.model_copy(
        update={
            "generic": None,
            "norm_status": NormStatus.AMBIGUOUS,
            "norm_candidates": (order.generic,),
        }
    )
    reason = f"{reading.reason} The model marked this line not legible; confirm the drug."
    return replace(reading, order=held, reason=reason)


def _read_structured(
    ocr: OcrResult, catalog: Catalog, started_at: datetime, *, uncertain_as_orders: bool
) -> PrescriptionReading:
    readings: list[OrderReading] = []
    uncertain: list[str] = []
    held = 0
    warnings = list(ocr.warnings)
    for number, read in enumerate(ocr.lines or (), start=1):
        if not read.legible and not uncertain_as_orders:
            uncertain.append(read.text)
            continue
        held += not read.legible
        parsed = parse_prescription_lines(read.as_written)
        if len(parsed) > 1:
            # One entry names several medicines: split it, and read directions per medicine.
            warnings.append(f"Line {number} names more than one medicine; split into orders.")
            for part in parsed:
                readings.append(
                    build_order(
                        replace(part, line_number=number),
                        catalog,
                        order_id=f"rx-{len(readings) + 1}",
                        started_at=started_at,
                    )
                )
            continue
        reading = build_order_from_read_line(
            read, catalog, number=number, order_id=f"rx-{len(readings) + 1}", started_at=started_at
        )
        readings.append(reading if read.legible else _needs_confirmation(reading))
    if held:
        warnings.append(
            f"{held} line(s) marked not legible by the model became orders that need confirmation."
        )
    if uncertain:
        warnings.append(
            f"{len(uncertain)} line(s) could not be read confidently and were not turned into "
            "orders; check the prescription: " + "; ".join(uncertain)
        )
    if not readings and not uncertain:
        warnings.append("No medicine lines were found in the transcript.")
    return PrescriptionReading(ocr, tuple(readings), (), tuple(warnings), tuple(uncertain))


def read_orders(
    ocr: OcrResult, catalog: Catalog, *, started_at: datetime, uncertain_as_orders: bool = False
) -> PrescriptionReading:
    """Parse an OCR result into orders, keeping lines that were not read as medicines.

    A plain transcript goes through the line parser; structured lines from a vision model skip
    the guesswork of finding medicine lines but use the same field parsers and the same catalog.
    Lines the model marked not legible are reported and make no order, unless uncertain_as_orders
    is set: then they become orders that always need a person to confirm the drug.
    """
    if ocr.lines is not None:
        return _read_structured(ocr, catalog, started_at, uncertain_as_orders=uncertain_as_orders)
    parsed = parse_prescription_lines(ocr.text)
    readings = tuple(
        build_order(line, catalog, order_id=f"rx-{i}", started_at=started_at)
        for i, line in enumerate(parsed, start=1)
    )
    used = {line.line_number for line in parsed}
    unparsed = tuple(
        text
        for number, text in enumerate(ocr.text.splitlines(), start=1)
        if text.strip() and number not in used
    )
    warnings = list(ocr.warnings)
    if not parsed:
        warnings.append("No medicine lines were found in the transcript.")
    return PrescriptionReading(ocr, readings, unparsed, tuple(warnings))
