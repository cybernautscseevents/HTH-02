"""Turn application input (typed prescription, diagnosis, cultures) into an Episode.

Nothing here decides anything clinical. Drug identity comes only from Catalog.normalize, the
syndrome only from an explicit code or an explicit phrase table, and a culture is recorded as
the state the caller states. Whatever cannot be resolved is left empty, so the rules answer
CANNOT_ASSESS instead of working on a guess. Handwriting OCR is not part of this path; it can
still feed `parse_prescription_text` with a transcript.
"""

import re
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from prescription_ocr.orders import OrderReading, build_order
from prescription_ocr.transcript import parse_prescription_lines

from .drugs import Catalog
from .schemas import (
    SIR,
    CultureStatus,
    Episode,
    Isolate,
    NormStatus,
    Patient,
    Setting,
    Specimen,
    Susceptibility,
)


class IntakeError(ValueError):
    """The request is inconsistent and was rejected instead of being guessed at."""


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IsolateInput(_Input):
    organism: str = Field(min_length=1)
    probable_contaminant: bool = False
    # Drug name as written -> S/I/R/SDD. Names go through the drug catalog.
    susceptibilities: dict[str, SIR] = {}


class CultureInput(_Input):
    """A culture as the clinician states it. NOT_SENT / absent means no culture is available;
    NO_GROWTH means a negative culture. The two are never interchangeable."""

    specimen_type: str = Field(min_length=1)
    status: CultureStatus
    collected_at: AwareDatetime | None = None
    reported_at: AwareDatetime | None = None
    isolates: tuple[IsolateInput, ...] = ()


class ConfirmedDrugInput(_Input):
    order_id: str = Field(min_length=1)
    raw_text: str = Field(min_length=1)
    generic: str = Field(min_length=1)


class EpisodeRequest(_Input):
    patient: Patient
    setting: Setting = Setting.WARD
    syndrome_code: str | None = None
    diagnosis_text: str | None = None
    prescription: str = Field(min_length=1)
    confirmed_drugs: tuple[ConfirmedDrugInput, ...] = ()
    started_at: AwareDatetime | None = None
    cultures: tuple[CultureInput, ...] = ()


# Phrase -> syndrome code. Only phrases that name exactly one syndrome are listed. Pneumonia
# and cellulitis are absent on purpose: the rule pack splits them by setting or severity, which
# free text does not state, so a person must choose the code.
DIAGNOSIS_PHRASES: dict[str, tuple[str, ...]] = {
    "cystitis": (
        "cystitis",
        "uncomplicated uti",
        "uncomplicated urinary tract infection",
        "lower urinary tract infection",
    ),
    "pyelonephritis": ("pyelonephritis",),
    "acute_bronchitis": ("acute bronchitis",),
    "bronchiolitis": ("bronchiolitis",),
    "copd_exacerbation": (
        "copd exacerbation",
        "exacerbation of copd",
        "infective exacerbation of copd",
        "aecopd",
    ),
    "viral_uri": ("viral uri", "viral urti", "viral laryngitis", "uncomplicated viral urti"),
    "acute_gastroenteritis_no_danger_signs": ("acute gastroenteritis without danger signs",),
}


# Words a diagnosis may carry beside its phrase without changing the syndrome.
_DIAGNOSIS_FILLER = frozenset({"acute"})
_PHRASE_CODE = {p: code for code, phrases in DIAGNOSIS_PHRASES.items() for p in phrases}
# Longest phrase first, so "uncomplicated viral urti" is not read as "viral urti" plus a word.
_PHRASE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in sorted(_PHRASE_CODE, key=len, reverse=True)) + r")\b"
)
_NEGATION = re.compile(
    r"\b(?:no|not|non|without|negative|denies|denied|excluded|ruled|rule|unlikely|absent)\b"
)


def read_diagnosis(text: str | None) -> tuple[str | None, str | None]:
    """(syndrome code, why none) for a free-text diagnosis.

    A code is returned only when the text is one phrase of the table, or several phrases of the
    same syndrome, with nothing else but "acute". A negated, uncertain or second diagnosis
    ("Complicated UTI, not cystitis", "Pneumonia with acute bronchitis", "cystitis?") could
    change the syndrome, so it is not mapped: a person selects the code.
    """
    if not text or not text.strip():
        return None, None
    normalized = " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())
    codes = {_PHRASE_CODE[m.group()] for m in _PHRASE.finditer(normalized)}
    if not codes:
        return None, None
    if len(codes) > 1:
        return None, "The diagnosis names more than one syndrome."
    other = [w for w in _PHRASE.sub(" ", normalized).split() if w not in _DIAGNOSIS_FILLER]
    if any(_NEGATION.fullmatch(w) for w in other):
        return None, "The diagnosis contains a negation."
    if "?" in text:
        return None, "The diagnosis is marked uncertain."
    if other:
        return None, f"The diagnosis says more than the syndrome name ('{' '.join(other)}')."
    return codes.pop(), None


def syndrome_from_text(text: str | None) -> str | None:
    """Syndrome code named by a free-text diagnosis, or None when it is not unambiguous."""
    return read_diagnosis(text)[0]


def resolve_syndrome(
    code: str | None, diagnosis_text: str | None, rulepack_codes: tuple[str, ...]
) -> tuple[str | None, str]:
    """Return (syndrome_code, how it was resolved). An unknown explicit code is rejected."""
    if code:
        if code not in rulepack_codes:
            raise IntakeError(f"Unknown syndrome code '{code}'.")
        return code, "selected"
    mapped = syndrome_from_text(diagnosis_text)
    if mapped:
        return mapped, "mapped_from_text"
    return None, "unresolved"


_PRESCRIPTION_MARKER = re.compile(
    r"^\s*(?:prescription|rx|℞|medications?|drug orders?)\s*:?\s*$", re.I
)
_HEADER_KEY = re.compile(
    r"^\s*(?:patient|name|age|sex|gender|weight|height|diagnosis|allerg(?:y|ies)|"
    r"creatinine|serum creatinine)\s*:",
    re.I,
)
_HEADER_ONLY = re.compile(r"^\s*(?:patient|diagnosis|allerg(?:y|ies))\s*:\s*$", re.I)


def medicine_text(text: str) -> str:
    """The medicine part of a typed prescription.

    Header lines ("Age: 65", "Diagnosis:" and the diagnosis on the next line) are dropped. If a
    "Prescription:" / "Rx" marker is present, only the lines after it are read.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if _PRESCRIPTION_MARKER.match(line):
            return "\n".join(lines[i + 1 :])
    kept: list[str] = []
    skip_next = False
    for line in lines:
        if skip_next and line.strip():
            skip_next = False
            continue
        if _HEADER_ONLY.match(line):
            skip_next = True
            continue
        if _HEADER_KEY.match(line):
            skip_next = False
            continue
        kept.append(line)
    return "\n".join(kept)


def parse_prescription_text(
    text: str, catalog: Catalog, *, started_at: datetime
) -> tuple[tuple[OrderReading, ...], tuple[str, ...]]:
    """Typed prescription -> orders, using the OCR order parser and the drug catalog.

    Returns the readings plus warnings. A name that is misspelt, ambiguous or unknown stays
    unaccepted, so rule R0 asks a person to confirm it.
    """
    parsed = parse_prescription_lines(medicine_text(text))
    readings = tuple(
        build_order(line, catalog, order_id=f"rx-{i}", started_at=started_at)
        for i, line in enumerate(parsed, start=1)
    )
    warnings = () if readings else ("No medicine lines were found in the prescription.",)
    return readings, warnings


def apply_confirmations(
    readings: tuple[OrderReading, ...],
    confirmations: tuple[ConfirmedDrugInput, ...],
    catalog: Catalog,
) -> tuple[OrderReading, ...]:
    if not confirmations:
        return readings
    by_id = {reading.order.id: reading for reading in readings}
    replacements: dict[str, OrderReading] = {}
    for confirmation in confirmations:
        reading = by_id.get(confirmation.order_id)
        if reading is None or reading.raw_line != confirmation.raw_text:
            raise IntakeError(f"Confirmation does not match parsed order {confirmation.order_id}.")
        normalized = catalog.normalize(confirmation.generic)
        if normalized.status is not NormStatus.ACCEPTED or normalized.generic is None:
            raise IntakeError(f"Confirmed drug '{confirmation.generic}' is not in the catalog.")
        if (
            reading.order.norm_status is NormStatus.AMBIGUOUS
            and normalized.generic not in reading.order.norm_candidates
        ):
            raise IntakeError(
                f"Confirmed drug '{normalized.generic}' was not offered for "
                f"{confirmation.order_id}."
            )
        order = reading.order.model_copy(
            update={
                "generic": normalized.generic,
                "brand": normalized.brand,
                "norm_status": NormStatus.CONFIRMED,
                "norm_candidates": (),
            }
        )
        replacements[confirmation.order_id] = OrderReading(
            reading.line_number,
            reading.raw_line,
            order,
            "Human confirmed from the drug catalog.",
        )
    return tuple(replacements.get(reading.order.id, reading) for reading in readings)


def build_specimens(cultures: tuple[CultureInput, ...], catalog: Catalog) -> tuple[Specimen, ...]:
    """Validate and convert cultures. Inconsistent combinations are rejected, never repaired."""
    specimens = []
    for i, culture in enumerate(cultures, start=1):
        has_growth = culture.status in (
            CultureStatus.FINAL,
            CultureStatus.GROWTH_NO_AST,
            CultureStatus.CONTAMINATED,
        )
        if culture.status is CultureStatus.FINAL and not culture.isolates:
            raise IntakeError(
                f"Culture {i}: a final positive culture needs at least one isolate. Use "
                "NO_GROWTH for a negative culture."
            )
        if culture.isolates and not has_growth:
            raise IntakeError(
                f"Culture {i}: isolates are only valid for a culture with growth, not "
                f"{culture.status.value}."
            )
        isolates = []
        for j, iso in enumerate(culture.isolates, start=1):
            susceptibilities = []
            for agent, result in iso.susceptibilities.items():
                name = catalog.normalize(agent)
                if name.status not in (NormStatus.ACCEPTED, NormStatus.CONFIRMED):
                    raise IntakeError(
                        f"Culture {i}: antibiotic '{agent}' in the susceptibility panel is not "
                        f"recognised ({name.reason})"
                    )
                susceptibilities.append(Susceptibility(agent=name.generic, result=result))
            isolates.append(
                Isolate(
                    id=f"iso-{i}-{j}",
                    organism=iso.organism.strip().lower(),
                    probable_contaminant=iso.probable_contaminant,
                    susceptibilities=tuple(susceptibilities),
                )
            )
        specimens.append(
            Specimen(
                id=f"spec-{i}",
                specimen_type=culture.specimen_type.strip().lower(),
                status=culture.status,
                collected_at=culture.collected_at,
                reported_at=culture.reported_at,
                isolates=tuple(isolates),
            )
        )
    return tuple(specimens)


def build_episode(
    request: EpisodeRequest,
    *,
    episode_id: str,
    catalog: Catalog,
    codes: tuple[str, ...],
    now: datetime,
) -> tuple[Episode, tuple[OrderReading, ...], str, tuple[str, ...]]:
    """Build the Episode the engine evaluates.

    Returns (episode, order readings, how the syndrome was resolved, warnings).
    """
    started_at = request.started_at or now
    syndrome, how = resolve_syndrome(request.syndrome_code, request.diagnosis_text, codes)
    readings, warnings = parse_prescription_text(
        request.prescription, catalog, started_at=started_at
    )
    readings = apply_confirmations(readings, request.confirmed_drugs, catalog)
    if how == "unresolved":
        _, why = read_diagnosis(request.diagnosis_text)
        warnings += (
            "No supported syndrome was selected or recognised in the diagnosis; guideline "
            "checks (R1, R3, R5) cannot run." + (f" {why} Select the syndrome." if why else ""),
        )
    episode = Episode(
        id=episode_id,
        patient=request.patient,
        setting=request.setting,
        syndrome_code=syndrome,
        diagnosis_text=request.diagnosis_text,
        started_at=started_at,
        orders=tuple(r.order for r in readings),
        specimens=build_specimens(request.cultures, catalog),
    )
    return episode, readings, how, warnings
