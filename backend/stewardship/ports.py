"""Interfaces the core engine depends on, implemented by teammates' modules.

The engine codes against these protocols so the rules can be built and tested before the
drug catalog, kidney checker, rule pack and coverage estimator are finished.
"""

from collections.abc import Sequence
from typing import Protocol

from .schemas import AwareTier, CoverageEstimate, DrugOrder, Finding, Patient, Setting, SyndromeRule


class DrugCatalog(Protocol):
    def aware_tier(self, generic: str) -> AwareTier: ...

    def is_antibiotic(self, generic: str) -> bool: ...

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
