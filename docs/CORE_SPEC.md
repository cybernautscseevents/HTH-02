# HC-03 Antibiotic Stewardship Copilot — Core Engine Build Spec

Owner: core lead. Teammates own `drugs-dosing` and `evidence-coverage` (see §2).
Timebox: hours 0–12 of a 24-hour hackathon. Merge + green scenario tests by hour 12–14.

## 0. Context (read first)

- Repo: RxGuard (`/home/kart/Projects/Kshema`). Existing pipeline is CLI-only; no API, DB or frontend.
- Problem HC-03: check antibiotic prescriptions against guidelines and local resistance, flag wrong
  drug / dose / duration / no culture, suggest safer options **for pharmacist approval**.
- The core engine is a **pure, deterministic** library. No network, no LLM, no database inside it.
  The API and UI (hours 14–19) call it; they are out of scope for this spec.
- Design principle: every check returns `PASS`, `FLAG` or `CANNOT_ASSESS`. Missing or uncertain input
  is never a silent pass. Every finding carries a `rule_id` and evidence (source + page).

## 1. Hour 0–1.5 (with the team)

1. Repo cleanup:
   - `git mv` into `legacy/`: `backend/modules/module2`, `module4`, `module5`, `module8`, `module9`,
     `backend/script.py`, `backend/modules/module1/trocr_offline_infer.py`.
   - Remove `langchain`, `chromadb`, `sentence-transformers`, `pypdf`, `networkx` from `requirements.txt`
     (nothing live imports them).
   - Add `pyproject.toml`: ruff (line length 100, rules E,F,I,B,UP), pytest (`testpaths = ["backend/tests"]`).
2. Write `backend/stewardship/schemas.py` (§3) and `backend/stewardship/ports.py` (§4). Push to `main`
   so both teammates branch from it.
3. Write the three scenario files in `backend/tests/scenarios/` (§9) together with the team.

## 2. Ownership (no two people edit the same file)

| Core lead (this spec) | Person 2 — drugs & dosing | Person 3 — evidence & coverage |
|---|---|---|
| `stewardship/schemas.py`, `ports.py`, `rules.py`, `culture.py`, `timeout.py`, `review.py`, `audit.py`, `episode.py`, `config.py` | `stewardship/drugs.py`, `modules/module3/*`, `modules/module7/*`, `data/indian_drug_lexicon.csv`, `data/aware.csv`, `data/intrinsic_resistance.csv`, `stewardship/rulepack/renal.yaml` | `stewardship/rulepack.py`, `stewardship/rulepack/syndromes.yaml`, `stewardship/coverage.py`, `data/amrsn_2024_urine.csv` |

Changes to `schemas.py` / `ports.py` go through the core lead.

## 3. `schemas.py` — Pydantic v2 models

All models `frozen=True` unless noted. Use `StrEnum`.

```text
Enums
  Outcome:        PASS | FLAG | CANNOT_ASSESS
  Severity:       INFO | LOW | MODERATE | HIGH
  NormStatus:     ACCEPTED | AMBIGUOUS | NO_MATCH | CONFIRMED      # CONFIRMED = human-confirmed
  AwareTier:      ACCESS | WATCH | RESERVE | NOT_CLASSIFIED
  Route:          PO | IV | IM
  Setting:        OPD | WARD | ICU
  Sex:            M | F
  AllergyStatus:  KNOWN | NONE_KNOWN | UNKNOWN
  CultureStatus:  NOT_SENT | PENDING | NO_GROWTH | GROWTH_NO_AST | FINAL | CONTAMINATED
  SIR:            S | I | R | SDD
  Trigger:        NEW_PRESCRIPTION | CULTURE_RESULT | LAB_UPDATE | TIMEOUT_DUE | MANUAL
  EvaluationStatus: OK | FLAGGED | INCOMPLETE
  ReviewAction:   ACCEPT | MODIFY | OVERRIDE | ESCALATE
  DataProvenance: PUBLIC | SYNTHETIC | HOSPITAL

Evidence        source_id: str, title: str, page: str | None, quote: str | None,
                provenance: DataProvenance = PUBLIC
Patient         id, age_years: int, sex: Sex, weight_kg: float | None,
                serum_creatinine_mg_dl: float | None, allergy_status: AllergyStatus,
                allergies: tuple[str, ...] = (), pregnant: bool | None
DrugOrder       id, raw_text: str, generic: str | None, brand: str | None,
                norm_status: NormStatus, norm_candidates: tuple[str, ...] = (),
                dose_mg: float | None, freq_per_day: float | None, route: Route | None,
                duration_days: int | None, started_at: datetime
Susceptibility  agent: str (generic name), result: SIR
Isolate         id, organism: str, probable_contaminant: bool = False,
                susceptibilities: tuple[Susceptibility, ...] = ()
Specimen        id, type: str ("urine" | "blood" | "sputum" | "pus"), status: CultureStatus,
                collected_at: datetime | None, reported_at: datetime | None,
                isolates: tuple[Isolate, ...] = ()
Episode         id, patient: Patient, setting: Setting, syndrome_code: str | None,
                diagnosis_text: str | None, started_at: datetime,
                orders: tuple[DrugOrder, ...], specimens: tuple[Specimen, ...] = ()
Suggestion      action: str ("switch" | "stop" | "adjust_dose" | "adjust_duration" | "send_culture"
                | "confirm_drug" | "provide_input"), drug: str | None, detail: str
Finding         rule_id: str, outcome: Outcome, severity: Severity, order_id: str | None,
                message: str, evidence: tuple[Evidence, ...] = (),
                suggestion: Suggestion | None = None, missing_inputs: tuple[str, ...] = ()
CoverageEstimate (owned by Person 3, defined here) regimen: str, median: float, lower: float,
                upper: float, p_at_least_target: float, n_isolates: int,
                provenance: DataProvenance, abstained: bool, note: str
Evaluation      episode_id, evaluated_at: datetime, trigger: Trigger, ruleset_version: str,
                inputs_hash: str, status: EvaluationStatus, findings: tuple[Finding, ...],
                coverage: tuple[CoverageEstimate, ...] = ()
Review          id, evaluation_id, finding_rule_id: str, order_id: str | None, reviewer: str,
                action: ReviewAction, reason_code: str | None, note: str | None, at: datetime
AuditEntry      at: datetime, actor: str, action: str, entity: str, entity_id: str,
                payload: dict
```

Validators: `age_years` 0–120, `weight_kg` > 0, `serum_creatinine_mg_dl` > 0, `duration_days` ≥ 0.

## 4. `ports.py` — what teammates provide (typing.Protocol)

The core codes against these. Until teammates merge, use fakes in `backend/tests/fakes.py`.

```python
class DrugCatalog(Protocol):            # Person 2
    def aware_tier(self, generic: str) -> AwareTier: ...
    def is_antibiotic(self, generic: str) -> bool: ...            # ATC J01*
    def intrinsically_resistant(self, organism: str, generic: str) -> bool: ...

class RenalChecker(Protocol):           # Person 2
    def check(self, order: DrugOrder, patient: Patient) -> Finding: ...   # rule_id "R4_RENAL"

class RulePack(Protocol):               # Person 3
    version: str
    def syndrome(self, code: str) -> SyndromeRule | None: ...

class CoverageEstimator(Protocol):      # Person 3
    def estimate(self, syndrome_code: str, setting: Setting,
                 regimens: Sequence[str]) -> tuple[CoverageEstimate, ...]: ...
```

`SyndromeRule` (put in `schemas.py`; Person 3 fills it from YAML):

```text
DrugRegimen     generic: str, route: Route, daily_dose_mg_min: float, daily_dose_mg_max: float,
                duration_days_min: int, duration_days_max: int, evidence: Evidence
SyndromeRule    code: str, name: str, antibiotics_indicated: bool,
                first_line: tuple[DrugRegimen, ...], alternatives: tuple[DrugRegimen, ...],
                culture_required: bool, evidence: Evidence
```

## 5. `rules.py` — per-order prescription checks

Each rule is a pure function `(ctx: RuleContext, order: DrugOrder) -> Finding`.
`RuleContext` (dataclass): `episode`, `rulepack`, `catalog`, `renal`, `now`.
Registry: `ORDER_RULES: tuple[Rule, ...]` executed in order. Rule IDs are stable strings.

| ID | Logic | Outcome / severity |
|---|---|---|
| `R0_IDENTIFIED` | `norm_status` not in {ACCEPTED, CONFIRMED} | CANNOT_ASSESS / HIGH, suggestion `confirm_drug` listing `norm_candidates`. **All other rules skip this order.** |
| `R1_INDICATION` | no `syndrome_code` or unknown syndrome → CANNOT_ASSESS / MODERATE (`missing_inputs=("syndrome",)`). `antibiotics_indicated=False` → FLAG / HIGH, suggestion `stop`. Generic in first_line → PASS. In alternatives → PASS / INFO ("alternative; first-line is X"). Otherwise → FLAG / MODERATE, suggestion `switch` to first first-line regimen. |
| `R2_AWARE` | tier RESERVE → FLAG / HIGH ("requires stewardship approval"). WATCH and syndrome has an ACCESS first-line regimen → FLAG / MODERATE. NOT_CLASSIFIED → CANNOT_ASSESS / LOW. Else PASS. |
| `R3_DOSE` | `age_years < 18` → CANNOT_ASSESS (adult rules only). `dose_mg` or `freq_per_day` missing → CANNOT_ASSESS. No matching regimen (same generic + route) → CANNOT_ASSESS. Daily = dose × freq; outside [min, max] → FLAG / MODERATE (HIGH if > 1.5 × max), suggestion `adjust_dose`. Else PASS. |
| `R4_RENAL` | delegate to `ctx.renal.check(order, patient)`. If it raises → CANNOT_ASSESS. |
| `R5_DURATION` | `duration_days` missing → CANNOT_ASSESS / LOW. > max → FLAG / MODERATE, suggestion `adjust_duration`. < min → FLAG / LOW. Else PASS. |
| `R6_ALLERGY` | `allergy_status=UNKNOWN` and generic is a beta-lactam → CANNOT_ASSESS / MODERATE. Generic or its class in `allergies` → FLAG / HIGH. Else PASS. (Class lookup: small dict in `rules.py`, e.g. penicillins, cephalosporins.) |

Evidence: R1/R3/R5 attach the regimen's or syndrome's `Evidence`; R2 attaches the WHO AWaRe 2025 source.

Non-antibiotic orders (`catalog.is_antibiotic` false) are skipped entirely.

## 6. `culture.py` — episode-level culture rules

Signature: `(ctx: RuleContext) -> tuple[Finding, ...]`. "Active antibiotics" = identified antibiotic orders.

| ID | Logic | Outcome |
|---|---|---|
| `C1_CULTURE_BEFORE_WATCH` | syndrome `culture_required` and any active drug is WATCH/RESERVE and no specimen with status ≠ NOT_SENT | FLAG / MODERATE, suggestion `send_culture` |
| `C3_BUG_DRUG_MISMATCH` | FINAL specimen, non-contaminant isolate, active drug has result R, **or** `catalog.intrinsically_resistant` | FLAG / HIGH ("therapy likely inactive"), suggestion `switch` |
| `C4_DE_ESCALATE` | FINAL; every non-contaminant isolate is S to some ACCESS drug that is in the syndrome's first_line/alternatives, route-compatible, not blocked by R6; current drug is WATCH/RESERVE | FLAG / MODERATE, suggestion `switch` to the narrowest candidate (sort: tier, then order in rulepack) |
| `C5_NO_GROWTH` | specimen NO_GROWTH and ≥ 48 h since first antibiotic start | FLAG / MODERATE, suggestion `provide_input` ("clinician to decide whether to stop") — never `stop` |
| `C6_CONTAMINANT` | isolate `probable_contaminant` | FLAG / LOW; C3/C4 ignore that isolate |
| `C7_INTERMEDIATE` | active drug has result I | FLAG / MODERATE ("not treated as susceptible for step-down") |
| `C8_NOT_TESTED` | FINAL isolate exists but active drug not in its susceptibilities and not intrinsic | CANNOT_ASSESS / MODERATE |

`NOT_SENT` never counts as negative. PENDING → no culture findings except C1.

## 7. `timeout.py`, `review.py`, `audit.py`, `episode.py`

**`timeout.py`**
- `first_antibiotic_start(episode, catalog) -> datetime | None`
- `is_timeout_due(episode, now, reviews) -> bool`: ≥ 48 h since first start and no review with
  `reason_code="TIMEOUT_DONE"` for this episode. Threshold from `config.TIMEOUT_HOURS = 48`.

**`review.py`**
- `apply_review(evaluation, review) -> AuditEntry`. Raises `ReviewError` when:
  OVERRIDE without `reason_code`; ACCEPT on a CANNOT_ASSESS finding (must MODIFY with the missing input
  or OVERRIDE); `finding_rule_id` not present in the evaluation.
- `REASON_CODES`: `CLINICAL_JUDGEMENT`, `CULTURE_PENDING`, `PATIENT_FACTOR`, `GUIDELINE_EXCEPTION`,
  `TIMEOUT_DONE`.

**`audit.py`**
- `AuditLog` protocol: `append(entry)`, `list(entity_id=None)`.
- `JsonlAuditLog(path)`: append-only, one JSON per line, never rewrites. (DB version replaces it at hour 14.)

**`episode.py`** — the only entry point the API calls:

```python
def evaluate_episode(episode: Episode, *, now: datetime, trigger: Trigger,
                     rulepack: RulePack, catalog: DrugCatalog, renal: RenalChecker,
                     coverage: CoverageEstimator | None = None) -> Evaluation
```

1. Build `RuleContext`.
2. For each order: run R0; if not identified, skip the rest for that order. Else run R1–R6.
3. Run C1–C8.
4. Coverage: only if no specimen is FINAL and `coverage` is given — estimate for the prescribed
   generics + the syndrome's first-line generics. Coverage never creates findings in P0.
5. Any rule that raises → `Finding(rule_id, CANNOT_ASSESS, HIGH, message="check failed: <type>")`,
   log with `logger.exception`, and the evaluation status is `INCOMPLETE`.
6. Status: INCOMPLETE if any rule crashed; else FLAGGED if any FLAG or CANNOT_ASSESS; else OK.
7. `inputs_hash` = sha256 of `episode.model_dump_json()` + `rulepack.version`. Same inputs → same
   hash → same findings (test this).
8. Sort findings: HIGH first, CANNOT_ASSESS before FLAG at the same severity.

**`config.py`**: `TIMEOUT_HOURS`, `HIGH_DOSE_FACTOR = 1.5`, `DATA_DIR`, `RULEPACK_DIR`, all overridable
via environment variables. No other module hard-codes paths or thresholds.

## 8. Code standards (judges read the code)

- Type hints everywhere; module docstring explains *why*; public functions have docstrings.
- `logging.getLogger(__name__)`; no `print`; no bare `except`; no `except Exception: pass`.
- No I/O in `rules.py`, `culture.py`, `timeout.py`, `episode.py` — inputs in, findings out.
- Messages are plain clinical English, no emojis; drug names lower-case generic.
- `ruff check` and `pytest` clean before every merge. Small commits, no AI attribution lines.

## 9. Tests (`backend/tests/`)

Unit (with `fakes.py`):
- R0: AMBIGUOUS order → only R0 finding for that order.
- R1: viral URI + amoxicillin → FLAG HIGH stop; missing syndrome → CANNOT_ASSESS.
- R2: meropenem → FLAG HIGH; ceftriaxone for cystitis → FLAG MODERATE.
- R3: dose missing → CANNOT_ASSESS; age 12 → CANNOT_ASSESS; 2× max → FLAG HIGH; in range → PASS.
- R5: 10 days where max 5 → FLAG; missing → CANNOT_ASSESS.
- R6: unknown allergy + amoxicillin → CANNOT_ASSESS; penicillin allergy + amoxicillin → FLAG HIGH.
- C1, C3 (R result and intrinsic), C4 picks narrowest Access drug, C5 never suggests `stop`,
  C6 contaminant ignored by C4, C8 not tested → CANNOT_ASSESS.
- Crashing fake renal checker → evaluation INCOMPLETE, other findings still present.
- Determinism: evaluating the same episode twice gives identical `inputs_hash` and findings.
- `apply_review`: OVERRIDE without reason raises; ACCEPT on CANNOT_ASSESS raises.

Scenarios (`tests/scenarios/*.json`, episode + expected rule_id/outcome pairs; `test_scenarios.py`
parametrises over them; uses real teammate implementations after merge):
1. `uti_cipro_no_culture.json` — OPD cystitis, ciprofloxacin 500 mg BD × 7 d, culture NOT_SENT.
2. `cap_ceftriaxone_renal.json` — ward CAP, ceftriaxone 2 g OD × 10 d, CrCl ≈ 25, then a FINAL
   culture S to amoxicillin (expects C4 step-down).
3. `cellulitis_ambiguous_brand.json` — typed brand resolves AMBIGUOUS (expects R0 only for that order).

## 10. Order of work (core lead)

| Hours | Deliverable |
|---|---|
| 0–1.5 | Cleanup, `pyproject.toml`, `schemas.py`, `ports.py`, `config.py`, scenario JSON drafts |
| 1.5–3 | `fakes.py`, `RuleContext`, R0 + R1 + tests |
| 3–5 | R2, R3, R5, R6 + tests |
| 5–7 | `culture.py` C1, C3, C4, C5 + tests |
| 7–9 | `episode.py` (crash isolation, status, hash, sorting) + C6–C8 |
| 9–11 | `timeout.py`, `review.py`, `audit.py` + tests |
| 11–12 | Review teammates' PRs against the ports |
| 12–14 | Merge all three branches; scenario tests green |

Done = all tests above pass, `ruff check` clean, every public function documented, and
`evaluate_episode` runs the three scenarios with real teammate code.

## 11. Explicitly not in the core

LLM calls, OCR, HTTP, database, PDF reports, drug interactions, pregnancy checks, per-patient ML.
Legacy `module6/antibiotic_stewardship.py` is superseded: its spectrum sets are replaced by AWaRe tiers
(Person 2), its policy JSON by the rule pack (Person 3), and its LLM-influenced decisions are removed.
