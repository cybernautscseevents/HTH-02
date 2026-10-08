"""Interfaces the core engine depends on, implemented by teammates' modules.

The engine codes against these protocols so the rules can be built and tested before the
drug catalog, kidney checker, rule pack and coverage estimator are finished.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

from .schemas import (
    AwareTier,
    CoverageEstimate,
    DrugOrder,
    Finding,
    Patient,
    Route,
    Setting,
    SyndromeRule,
)

if TYPE_CHECKING:
    from .records import PatientRecord


class DrugCatalog(Protocol):
    def aware_tier(self, generic: str, route: Route | None = None) -> AwareTier:
        """WHO AWaRe tier. Some drugs (fosfomycin, minocycline) differ by route; without a route
        such a drug is NOT_CLASSIFIED."""
        ...

    def is_antibiotic(self, generic: str) -> bool: ...

    def knows_organism(self, organism: str) -> bool:
        """False when the organism is not in the reference list, so intrinsic resistance for it
        cannot be checked."""
        ...

    def intrinsically_resistant(self, organism: str, generic: str) -> bool: ...


class RenalChecker(Protocol):
    def check(self, order: DrugOrder, patient: Patient) -> Finding:
        """Return a finding with rule_id "R4_RENAL"."""
        ...


class RulePack(Protocol):
    version: str

    def syndrome(self, code: str) -> SyndromeRule | None: ...


class CoverageEstimator(Protocol):
    def estimate(
        self, syndrome_code: str, setting: Setting, regimens: Sequence[str]
    ) -> tuple[CoverageEstimate, ...]: ...


class PatientRecordSource(Protocol):
    def get(self, patient_id: str) -> "PatientRecord | None":
        """What the hospital already holds for this patient, or None when it has no record."""
        ...
