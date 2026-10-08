"""Kidney-function dose check (rule R4) against US FDA label renal dosing tables.

Creatinine clearance is estimated with the Cockcroft-Gault equation, the estimate the drug
labels themselves use. Each band in data/renal_dosing.csv quotes its label and says one of:
no change needed ("none"), a modified regimen with an optional daily cap ("adjust"), or do
not use ("avoid"). A drug, route or clearance the table does not cover is CANNOT_ASSESS.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from . import config
from .schemas import (
    DrugOrder,
    Evidence,
    Finding,
    Outcome,
    Patient,
    Route,
    Severity,
    Sex,
    Suggestion,
)

RULE_ID = "R4_RENAL"

COCKCROFT_GAULT = Evidence(
    source_id="cockcroft-gault-1976",
    title="Cockcroft DW, Gault MH. Prediction of creatinine clearance from serum creatinine. "
    "Nephron 1976;16(1):31-41.",
)


def creatinine_clearance(patient: Patient) -> float | None:
    """Cockcroft-Gault estimate in mL/min using actual body weight; None if inputs are missing."""
    if patient.weight_kg is None or patient.serum_creatinine_mg_dl is None:
        return None
    crcl = (140 - patient.age_years) * patient.weight_kg / (72 * patient.serum_creatinine_mg_dl)
    return crcl * 0.85 if patient.sex is Sex.F else crcl


@dataclass(frozen=True)
class RenalBand:
    generic: str
    routes: frozenset[Route]
    crcl_low: int
    crcl_high: int
    action: str  # "none" | "adjust" | "avoid"
    max_daily_mg: float | None
    evidence: Evidence


def load_renal_bands(path: Path = config.RENAL_DOSING_CSV) -> dict[str, tuple[RenalBand, ...]]:
    """Read the renal dosing table, grouped by generic name."""
    bands: dict[str, list[RenalBand]] = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            band = RenalBand(
                generic=row["generic"],
                routes=frozenset(Route(r) for r in row["routes"].split("|")),
                crcl_low=int(row["crcl_low"]),
                crcl_high=int(row["crcl_high"]),
                action=row["action"],
                max_daily_mg=float(row["max_daily_mg"]) if row["max_daily_mg"] else None,
                evidence=Evidence(
                    source_id=row["source_id"],
                    title=row["title"],
                    page=f"Section {row['section']}",
                    quote=row["quote"],
                ),
            )
            bands.setdefault(band.generic, []).append(band)
    return {generic: tuple(rows) for generic, rows in bands.items()}


class RenalDosing:
    """RenalChecker port backed by the FDA label renal dosing table."""

    def __init__(self, bands: dict[str, tuple[RenalBand, ...]]) -> None:
        self._bands = bands

    @classmethod
    def load(cls, path: Path = config.RENAL_DOSING_CSV) -> "RenalDosing":
        return cls(load_renal_bands(path))

    def check(self, order: DrugOrder, patient: Patient) -> Finding:
        """R4: is the order suitable for the patient's estimated creatinine clearance?"""

        def finding(outcome: Outcome, severity: Severity, message: str, **extra) -> Finding:
            return Finding(
                rule_id=RULE_ID,
                outcome=outcome,
                severity=severity,
                order_id=order.id,
                message=message,
                **extra,
            )

        bands = self._bands.get(order.generic, ())
        if order.route is not None:
            bands = tuple(b for b in bands if order.route in b.routes)
        if not bands:
            route = f" by the {order.route} route" if order.route else ""
            return finding(
                Outcome.CANNOT_ASSESS,
                Severity.LOW,
                f"No renal dosing data for {order.generic}{route}; kidney dosing not checked.",
            )
        if all(b.action == "none" for b in bands):
            return finding(
                Outcome.PASS,
                Severity.INFO,
                f"No renal dose adjustment is needed for {order.generic}.",
                evidence=(bands[0].evidence,),
            )
        if patient.age_years < config.ADULT_AGE_YEARS:
            return finding(
                Outcome.CANNOT_ASSESS,
                Severity.MODERATE,
                "Renal dosing rules cover adults only; kidney dosing was not checked.",
            )
        crcl = creatinine_clearance(patient)
        if crcl is None:
            missing = tuple(
                name
                for name, value in (
                    ("weight_kg", patient.weight_kg),
                    ("serum_creatinine_mg_dl", patient.serum_creatinine_mg_dl),
                )
                if value is None
            )
            return finding(
                Outcome.CANNOT_ASSESS,
                Severity.MODERATE,
                f"Kidney function unknown; {order.generic} needs dose changes in renal impairment.",
                missing_inputs=missing,
            )

        clearance = round(crcl)
        band = next((b for b in bands if b.crcl_low <= clearance <= b.crcl_high), None)
        crcl_text = f"estimated creatinine clearance {clearance} mL/min"
        if band is None:
            return finding(
                Outcome.CANNOT_ASSESS,
                Severity.MODERATE,
                f"The label gives no dosing for {order.generic} at {crcl_text}.",
            )
        evidence = (band.evidence, COCKCROFT_GAULT)

        if band.action == "none":
            return finding(
                Outcome.PASS,
                Severity.INFO,
                f"No renal dose adjustment is needed for {order.generic} at {crcl_text}.",
                evidence=evidence,
            )
        if band.action == "avoid":
            return finding(
                Outcome.FLAG,
                Severity.HIGH,
                f"The label advises against {order.generic} at {crcl_text}.",
                evidence=evidence,
                suggestion=Suggestion(
                    action="switch",
                    detail="Choose an agent suitable for reduced kidney function.",
                ),
            )

        regimen = Suggestion(
            action="adjust_dose", drug=order.generic, detail=f"Label: {band.evidence.quote}"
        )
        if band.max_daily_mg is None:
            return finding(
                Outcome.FLAG,
                Severity.MODERATE,
                f"{order.generic} needs a renal dose adjustment at {crcl_text}.",
                evidence=evidence,
                suggestion=regimen,
            )
        limit = band.max_daily_mg
        missing = tuple(
            name
            for name, value in (("dose_mg", order.dose_mg), ("freq_per_day", order.freq_per_day))
            if value is None
        )
        if missing:
            return finding(
                Outcome.CANNOT_ASSESS,
                Severity.MODERATE,
                f"Renal limit for {order.generic} is {limit:g} mg/day at {crcl_text}; "
                "dose or frequency missing.",
                evidence=evidence,
                missing_inputs=missing,
            )
        daily = order.dose_mg * order.freq_per_day
        if daily <= limit:
            return finding(
                Outcome.PASS,
                Severity.INFO,
                f"Daily dose {daily:g} mg is within the renal limit of {limit:g} mg/day at "
                f"{crcl_text}.",
                evidence=evidence,
            )
        return finding(
            Outcome.FLAG,
            Severity.HIGH if daily > limit * config.HIGH_DOSE_FACTOR else Severity.MODERATE,
            f"Daily dose {daily:g} mg exceeds the renal limit of {limit:g} mg/day at {crcl_text}.",
            evidence=evidence,
            suggestion=regimen,
        )
