"""In-memory stand-ins for teammates' modules, plus builders for test inputs.

TEST FIXTURES ONLY. The doses, durations and tiers below exist to exercise the engine's
logic. They are not clinical guidance and must never be copied into the rule pack.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from backend.stewardship.schemas import (
    AllergyStatus,
    AwareTier,
    CoverageEstimate,
    CultureStatus,
    DataProvenance,
    DrugOrder,
    DrugRegimen,
    Episode,
    Evidence,
    Finding,
    Isolate,
    NormStatus,
    Outcome,
    Patient,
    Route,
    Setting,
    Severity,
    Sex,
    Specimen,
    Susceptibility,
    SyndromeRule,
)

T0 = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)

FIXTURE_EVIDENCE = Evidence(source_id="test-fixture", title="Test fixture, not guidance", page="0")


def regimen(
    generic: str,
    route: Route = Route.PO,
    dose=(100.0, 1000.0),
    days=(3, 7),
) -> DrugRegimen:
    return DrugRegimen(
        generic=generic,
        route=route,
        daily_dose_mg_min=dose[0],
        daily_dose_mg_max=dose[1],
        duration_days_min=days[0],
        duration_days_max=days[1],
        evidence=FIXTURE_EVIDENCE,
    )


SYNDROMES = {
    "cystitis": SyndromeRule(
        code="cystitis",
        name="Uncomplicated cystitis",
        antibiotics_indicated=True,
        first_line=(regimen("nitrofurantoin", dose=(200, 400), days=(5, 5)),),
        alternatives=(regimen("ciprofloxacin", dose=(500, 1000), days=(3, 3)),),
        culture_required=False,
        evidence=FIXTURE_EVIDENCE,
    ),
    "pyelonephritis": SyndromeRule(
        code="pyelonephritis",
        name="Pyelonephritis",
        antibiotics_indicated=True,
        first_line=(regimen("amikacin", route=Route.IV, dose=(500, 1500), days=(7, 14)),),
        alternatives=(
            regimen("ceftriaxone", route=Route.IV, dose=(1000, 2000), days=(7, 14)),
            regimen("gentamicin", route=Route.IV, dose=(100, 500), days=(7, 14)),
        ),
        culture_required=True,
        evidence=FIXTURE_EVIDENCE,
    ),
    "viral_uri": SyndromeRule(
        code="viral_uri",
        name="Viral upper respiratory infection",
        antibiotics_indicated=False,
        culture_required=False,
        evidence=FIXTURE_EVIDENCE,
    ),
}

TIERS = {
    "nitrofurantoin": AwareTier.ACCESS,
    "amoxicillin": AwareTier.ACCESS,
    "amikacin": AwareTier.ACCESS,
    "gentamicin": AwareTier.ACCESS,
    "ciprofloxacin": AwareTier.WATCH,
    "ceftriaxone": AwareTier.WATCH,
    "meropenem": AwareTier.WATCH,
    "colistin": AwareTier.RESERVE,
    "mystery-mycin": AwareTier.NOT_CLASSIFIED,
}


class FakeRulePack:
    version = "test-1"

    def syndrome(self, code: str) -> SyndromeRule | None:
        return SYNDROMES.get(code)


@dataclass
class FakeCatalog:
    intrinsic: set[tuple[str, str]] = field(default_factory=set)
    unknown_organisms: set[str] = field(default_factory=set)

    def aware_tier(self, generic: str, route: Route | None = None) -> AwareTier:
        return TIERS.get(generic, AwareTier.NOT_CLASSIFIED)

    def is_antibiotic(self, generic: str) -> bool:
        return generic in TIERS

    def knows_organism(self, organism: str) -> bool:
        return organism not in self.unknown_organisms

    def intrinsically_resistant(self, organism: str, generic: str) -> bool:
        return (organism, generic) in self.intrinsic


class FakeRenal:
    def check(self, order: DrugOrder, patient: Patient) -> Finding:
        return Finding(
            rule_id="R4_RENAL",
            outcome=Outcome.PASS,
            severity=Severity.INFO,
            order_id=order.id,
            message="fake renal check",
        )


class CrashingRenal:
    def check(self, order: DrugOrder, patient: Patient) -> Finding:
        raise RuntimeError("renal table not loaded")


class FakeCoverage:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Setting, tuple[str, ...]]] = []

    def estimate(
        self, syndrome_code: str, setting: Setting, regimens: Sequence[str]
    ) -> tuple[CoverageEstimate, ...]:
        self.calls.append((syndrome_code, setting, tuple(regimens)))
        return tuple(
            CoverageEstimate(
                regimen=r,
                median=0.5,
                lower=0.4,
                upper=0.6,
                p_at_least_target=0.1,
                n_isolates=100,
                provenance=DataProvenance.SYNTHETIC,
                abstained=False,
                note="fake",
            )
            for r in regimens
        )


def patient(**overrides) -> Patient:
    values = dict(
        id="p1",
        age_years=45,
        sex=Sex.F,
        weight_kg=60.0,
        serum_creatinine_mg_dl=0.9,
        allergy_status=AllergyStatus.NONE_KNOWN,
    )
    return Patient(**(values | overrides))


def order(generic: str | None = "nitrofurantoin", **overrides) -> DrugOrder:
    values = dict(
        id="o1",
        raw_text=generic or "unreadable",
        generic=generic,
        norm_status=NormStatus.ACCEPTED,
        dose_mg=100.0,
        freq_per_day=2.0,
        route=Route.PO,
        duration_days=5,
        started_at=T0,
    )
    return DrugOrder(**(values | overrides))


def isolate(organism="escherichia coli", contaminant=False, **results: str) -> Isolate:
    return Isolate(
        id=f"iso-{organism}",
        organism=organism,
        probable_contaminant=contaminant,
        susceptibilities=tuple(Susceptibility(agent=a, result=r) for a, r in results.items()),
    )


def specimen(status=CultureStatus.FINAL, isolates=(), **overrides) -> Specimen:
    values = dict(id="s1", specimen_type="urine", status=status, collected_at=T0, isolates=isolates)
    return Specimen(**(values | overrides))


def episode(orders=None, specimens=(), **overrides) -> Episode:
    values = dict(
        id="e1",
        patient=patient(),
        setting=Setting.OPD,
        syndrome_code="cystitis",
        started_at=T0,
        orders=orders if orders is not None else (order(),),
        specimens=specimens,
    )
    return Episode(**(values | overrides))
