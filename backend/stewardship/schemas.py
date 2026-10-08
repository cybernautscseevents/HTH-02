"""Data models shared by every part of the stewardship engine.

All models are immutable: an evaluation is a pure function of these inputs, and nothing
downstream can change a prescription or a finding after the fact. Datetimes must be
timezone-aware so time-out arithmetic never mixes local and UTC times.
"""

from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class Outcome(StrEnum):
    PASS = "PASS"
    FLAG = "FLAG"
    CANNOT_ASSESS = "CANNOT_ASSESS"


class Severity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class NormStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    AMBIGUOUS = "AMBIGUOUS"
    NO_MATCH = "NO_MATCH"
    CONFIRMED = "CONFIRMED"  # identity confirmed by a person


class AwareTier(StrEnum):
    ACCESS = "ACCESS"
    WATCH = "WATCH"
    RESERVE = "RESERVE"
    NOT_CLASSIFIED = "NOT_CLASSIFIED"


class Route(StrEnum):
    PO = "PO"
    IV = "IV"
    IM = "IM"


class Setting(StrEnum):
    OPD = "OPD"
    WARD = "WARD"
    ICU = "ICU"


class Sex(StrEnum):
    M = "M"
    F = "F"


class AllergyStatus(StrEnum):
    KNOWN = "KNOWN"
    NONE_KNOWN = "NONE_KNOWN"
    UNKNOWN = "UNKNOWN"


class CultureStatus(StrEnum):
    NOT_SENT = "NOT_SENT"
    PENDING = "PENDING"
    NO_GROWTH = "NO_GROWTH"
    GROWTH_NO_AST = "GROWTH_NO_AST"
    FINAL = "FINAL"
    CONTAMINATED = "CONTAMINATED"


class SIR(StrEnum):
    S = "S"
    I = "I"  # noqa: E741 - standard laboratory abbreviation
    R = "R"
    SDD = "SDD"


class Trigger(StrEnum):
    NEW_PRESCRIPTION = "NEW_PRESCRIPTION"
    CULTURE_RESULT = "CULTURE_RESULT"
    LAB_UPDATE = "LAB_UPDATE"
    TIMEOUT_DUE = "TIMEOUT_DUE"
    MANUAL = "MANUAL"


class EvaluationStatus(StrEnum):
    OK = "OK"
    FLAGGED = "FLAGGED"
    INCOMPLETE = "INCOMPLETE"  # at least one check failed to run


class ReviewAction(StrEnum):
    ACCEPT = "ACCEPT"
    MODIFY = "MODIFY"
    OVERRIDE = "OVERRIDE"
    ESCALATE = "ESCALATE"


class SuggestedAction(StrEnum):
    SWITCH = "switch"
    STOP = "stop"
    ADJUST_DOSE = "adjust_dose"
    ADJUST_DURATION = "adjust_duration"
    SEND_CULTURE = "send_culture"
    CONFIRM_DRUG = "confirm_drug"
    PROVIDE_INPUT = "provide_input"


class DataProvenance(StrEnum):
    PUBLIC = "PUBLIC"
    SYNTHETIC = "SYNTHETIC"
    HOSPITAL = "HOSPITAL"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Evidence(_Frozen):
    source_id: str
    title: str
    page: str | None = None
    quote: str | None = None
    provenance: DataProvenance = DataProvenance.PUBLIC


class Patient(_Frozen):
    id: str
    age_years: int = Field(ge=0, le=120)
    sex: Sex
    weight_kg: float | None = Field(default=None, gt=0)
    serum_creatinine_mg_dl: float | None = Field(default=None, gt=0)
    allergy_status: AllergyStatus
    allergies: tuple[str, ...] = ()
    pregnant: bool | None = None


class DrugOrder(_Frozen):
    id: str
    raw_text: str
    generic: str | None = None
    brand: str | None = None
    norm_status: NormStatus
    norm_candidates: tuple[str, ...] = ()
    dose_mg: float | None = Field(default=None, gt=0)
    freq_per_day: float | None = Field(default=None, gt=0)
    route: Route | None = None
    duration_days: int | None = Field(default=None, ge=0)
    started_at: AwareDatetime


class Susceptibility(_Frozen):
    agent: str  # generic name
    result: SIR


class Isolate(_Frozen):
    id: str
    organism: str
    probable_contaminant: bool = False
    susceptibilities: tuple[Susceptibility, ...] = ()


class Specimen(_Frozen):
    id: str
    specimen_type: str  # "urine", "blood", "sputum", "pus"
    status: CultureStatus
    collected_at: AwareDatetime | None = None
    reported_at: AwareDatetime | None = None
    isolates: tuple[Isolate, ...] = ()


class Episode(_Frozen):
    id: str
    patient: Patient
    setting: Setting
    syndrome_code: str | None = None
    diagnosis_text: str | None = None
    started_at: AwareDatetime
    orders: tuple[DrugOrder, ...]
    specimens: tuple[Specimen, ...] = ()


class DrugRegimen(_Frozen):
    """One guideline regimen. A dose or duration the guideline does not give as a fixed amount
    (weight-based doses, durations stated for the syndrome only) is None, and R3/R5 then return
    CANNOT_ASSESS instead of guessing."""

    generic: str
    route: Route
    daily_dose_mg_min: float | None = Field(default=None, gt=0)
    daily_dose_mg_max: float | None = Field(default=None, gt=0)
    duration_days_min: int | None = Field(default=None, ge=0)
    duration_days_max: int | None = Field(default=None, ge=0)
    evidence: Evidence


class SyndromeRule(_Frozen):
    code: str
    name: str
    antibiotics_indicated: bool
    first_line: tuple[DrugRegimen, ...] = ()
    alternatives: tuple[DrugRegimen, ...] = ()
    culture_required: bool
    evidence: Evidence


class Suggestion(_Frozen):
    action: SuggestedAction
    drug: str | None = None
    detail: str


class Finding(_Frozen):
    rule_id: str
    outcome: Outcome
    severity: Severity
    order_id: str | None = None
    message: str
    evidence: tuple[Evidence, ...] = ()
    suggestion: Suggestion | None = None
    missing_inputs: tuple[str, ...] = ()


class CoverageEstimate(_Frozen):
    regimen: str
    median: float = Field(ge=0, le=1)
    lower: float = Field(ge=0, le=1)
    upper: float = Field(ge=0, le=1)
    p_at_least_target: float = Field(ge=0, le=1)
    n_isolates: int = Field(ge=0)
    provenance: DataProvenance
    abstained: bool
    note: str


class Evaluation(_Frozen):
    id: str
    episode_id: str
    evaluated_at: AwareDatetime
    trigger: Trigger
    ruleset_version: str
    inputs_hash: str
    status: EvaluationStatus
    findings: tuple[Finding, ...]
    coverage: tuple[CoverageEstimate, ...] = ()


class Review(_Frozen):
    id: str
    episode_id: str
    evaluation_id: str
    finding_rule_id: str | None = None  # None: review of the whole episode (e.g. time-out)
    order_id: str | None = None
    reviewer: str
    action: ReviewAction
    reason_code: str | None = None
    note: str | None = None
    at: AwareDatetime


class AuditEntry(_Frozen):
    at: AwareDatetime
    actor: str
    action: str
    entity: str
    entity_id: str
    payload: dict
