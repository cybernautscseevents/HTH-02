"""ICMR AMRSN 2023 network surveillance susceptibility, as advisory context only.

This table is NOT an input to any rule (R0-R6, culture rules) and never changes an outcome. It
answers one question for a pharmacist: "how often was this organism susceptible to this drug in
the national surveillance network?". The numbers come from tertiary-care hospitals across India;
they are not this hospital's antibiogram and not representative of the community.

Rows are returned exactly as the source reports them and are never pooled: a row for urine in OPD
patients and a row for blood isolates are different observations. A result from fewer than
`config.SURVEILLANCE_MIN_ISOLATES` isolates is marked as limited evidence. Rows whose drug name
cannot be matched exactly, or whose percentage disagrees with its own counts, are not loaded and
are listed in `skipped`.
"""

import csv
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from . import config
from .drugs import Catalog
from .schemas import NormStatus

SOURCE = (
    "ICMR Antimicrobial Resistance Research & Surveillance Network (AMRSN), Annual Report 2023 "
    "(network surveillance; not hospital-specific)"
)
# Percentage and counts may differ by rounding; more than this means the row is inconsistent.
_MAX_ROUNDING_GAP = 1.0


class SurveillanceRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    organism: str
    specimen: str
    antibiotic: str  # as printed in the source
    generic: str  # catalog generic name
    susceptible_count: int
    tested_count: int
    susceptibility_percent: float | None  # None where the source prints no percentage
    context: str | None  # patient group the source reports separately (OPD, ICU, CR, ...)
    year: int
    source_page: str
    source_section: str
    notes: str
    limited_evidence: bool  # fewer isolates than config.SURVEILLANCE_MIN_ISOLATES

    @property
    def summary(self) -> str:
        pct = (
            f"{self.susceptibility_percent:g}% " if self.susceptibility_percent is not None else ""
        )
        text = (
            f"{self.organism} ({self.specimen}{', ' + self.context if self.context else ''}): "
            f"{pct}susceptible to {self.generic} ({self.susceptible_count}/{self.tested_count} "
            f"isolates, ICMR AMRSN {self.year}, {self.source_section}, p. {self.source_page})"
        )
        if self.limited_evidence:
            text += (
                f". Limited evidence: fewer than {config.SURVEILLANCE_MIN_ISOLATES} isolates "
                "tested."
            )
        return text


def _generic(name: str, catalog: Catalog) -> str | None:
    """Catalog generic for a printed drug name, matched exactly. The only repairs are removing a
    trailing low-count marker (*) and spaces that PDF extraction put inside a word
    ("Vancomyc in"); both must then give an exact catalog match."""
    for candidate in (name, name.rstrip("*").strip(), re.sub(r"\s+", "", name.rstrip("*"))):
        result = catalog.normalize(candidate)
        if result.status is NormStatus.ACCEPTED and result.generic is not None:
            return result.generic
    return None


def _int(value: str) -> int | None:
    try:
        return int(float(value))
    except ValueError:
        return None


class SurveillanceTable:
    def __init__(self, rows: tuple[SurveillanceRow, ...], skipped: tuple[tuple[dict, str], ...]):
        self.rows = rows
        self.skipped = skipped  # (source row, reason)

    @classmethod
    def load(cls, catalog: Catalog, path: Path = config.SURVEILLANCE_CSV) -> "SurveillanceTable":
        rows, skipped = [], []
        with path.open(encoding="utf-8", newline="") as f:
            for raw in csv.DictReader(f):
                row, reason = _row(raw, catalog)
                if row is None:
                    skipped.append((raw, reason))
                else:
                    rows.append(row)
        return cls(tuple(rows), tuple(skipped))

    def lookup(
        self, generic: str, *, organism: str | None = None, specimen: str | None = None
    ) -> tuple[SurveillanceRow, ...]:
        """Rows for this drug, narrowed by exact (case-insensitive) organism and specimen."""

        def same(a: str, b: str | None) -> bool:
            return b is None or a.strip().lower() == b.strip().lower()

        return tuple(
            r
            for r in self.rows
            if r.generic == generic and same(r.organism, organism) and same(r.specimen, specimen)
        )


def _row(raw: dict, catalog: Catalog) -> tuple[SurveillanceRow | None, str]:
    generic = _generic(raw["antibiotic"], catalog)
    if generic is None:
        return None, f"drug name '{raw['antibiotic']}' does not match the catalog exactly"
    susceptible, tested = _int(raw["susceptible_count"]), _int(raw["tested_count"])
    if susceptible is None or not tested:
        return None, "no isolate counts"
    percent = float(raw["susceptibility_percent"]) if raw["susceptibility_percent"] else None
    if percent is not None and abs(100 * susceptible / tested - percent) > _MAX_ROUNDING_GAP:
        return None, (
            f"printed {percent}% disagrees with its own counts {susceptible}/{tested} "
            f"({100 * susceptible / tested:.1f}%)"
        )
    context = re.search(r"Context=([^.]*)", raw["notes"])
    return (
        SurveillanceRow(
            organism=raw["organism"].strip(),
            specimen=raw["specimen"].strip(),
            antibiotic=raw["antibiotic"].strip(),
            generic=generic,
            susceptible_count=susceptible,
            tested_count=tested,
            susceptibility_percent=percent,
            context=context.group(1).strip() if context else None,
            year=int(raw["year"]),
            source_page=raw["source_page"].strip(),
            source_section=raw["source_section"].strip(),
            notes=raw["notes"].strip(),
            limited_evidence=tested < config.SURVEILLANCE_MIN_ISOLATES,
        ),
        "",
    )
