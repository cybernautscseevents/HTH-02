/**
 * TypeScript mirrors of the backend stewardship Pydantic schemas.
 * Keep in sync with backend/stewardship/schemas.py.
 * Do NOT add logic here — these are pure data shapes.
 */

// ─── Enums ────────────────────────────────────────────────────────────────────

export type Outcome = 'PASS' | 'FLAG' | 'CANNOT_ASSESS'

export type Severity = 'INFO' | 'LOW' | 'MODERATE' | 'HIGH'

export type NormStatus = 'ACCEPTED' | 'AMBIGUOUS' | 'NO_MATCH' | 'CONFIRMED'

export type AwareTier = 'ACCESS' | 'WATCH' | 'RESERVE' | 'NOT_CLASSIFIED'

export type Route = 'PO' | 'IV' | 'IM'

export type Setting = 'OPD' | 'WARD' | 'ICU'

export type Sex = 'M' | 'F'

export type AllergyStatus = 'KNOWN' | 'NONE_KNOWN' | 'UNKNOWN'

export type CultureStatus =
  | 'NOT_SENT'
  | 'PENDING'
  | 'NO_GROWTH'
  | 'GROWTH_NO_AST'
  | 'FINAL'
  | 'CONTAMINATED'

export type SIR = 'S' | 'I' | 'R' | 'SDD'

export type Trigger =
  | 'NEW_PRESCRIPTION'
  | 'CULTURE_RESULT'
  | 'LAB_UPDATE'
  | 'TIMEOUT_DUE'
  | 'MANUAL'

export type EvaluationStatus = 'OK' | 'FLAGGED' | 'INCOMPLETE'

export type ReviewAction = 'ACCEPT' | 'MODIFY' | 'REMOVE' | 'OVERRIDE' | 'ESCALATE'

export type SuggestedAction =
  | 'switch'
  | 'stop'
  | 'adjust_dose'
  | 'adjust_duration'
  | 'send_culture'
  | 'confirm_drug'
  | 'provide_input'

export type DataProvenance = 'PUBLIC' | 'SYNTHETIC' | 'HOSPITAL'

// ─── Reason codes (from review.py) ────────────────────────────────────────────

export const REASON_CODES = [
  'CLINICAL_JUDGEMENT',
  'CULTURE_PENDING',
  'PATIENT_FACTOR',
  'GUIDELINE_EXCEPTION',
  'TIMEOUT_DONE',
] as const

export type ReasonCode = (typeof REASON_CODES)[number]

// ─── Core Models ──────────────────────────────────────────────────────────────

export interface Evidence {
  source_id: string
  title: string
  page?: string | null
  quote?: string | null
  provenance: DataProvenance
}

export interface Patient {
  id: string
  age_years: number
  sex: Sex
  weight_kg?: number | null
  serum_creatinine_mg_dl?: number | null
  allergy_status: AllergyStatus
  allergies: string[]
  pregnant?: boolean | null
}

export interface DrugOrder {
  id: string
  raw_text: string
  generic?: string | null
  brand?: string | null
  norm_status: NormStatus
  norm_candidates: string[]
  dose_mg?: number | null
  freq_per_day?: number | null
  route?: Route | null
  duration_days?: number | null
  started_at: string // ISO datetime
}

export interface Susceptibility {
  agent: string
  result: SIR
}

export interface Isolate {
  id: string
  organism: string
  probable_contaminant: boolean
  susceptibilities: Susceptibility[]
}

export interface Specimen {
  id: string
  specimen_type: string
  status: CultureStatus
  collected_at?: string | null
  reported_at?: string | null
  isolates: Isolate[]
}

export interface Episode {
  id: string
  patient: Patient
  setting: Setting
  syndrome_code?: string | null
  diagnosis_text?: string | null
  started_at: string
  orders: DrugOrder[]
  specimens: Specimen[]
}

export interface DrugRegimen {
  generic: string
  route: Route
  daily_dose_mg_min?: number | null // null: guideline gives no fixed mg/day (e.g. weight-based)
  daily_dose_mg_max?: number | null
  duration_days_min?: number | null
  duration_days_max?: number | null
  evidence: Evidence
}

export interface SyndromeRule {
  code: string
  name: string
  antibiotics_indicated: boolean
  first_line: DrugRegimen[]
  alternatives: DrugRegimen[]
  culture_required: boolean
  evidence: Evidence
}

export interface Suggestion {
  action: SuggestedAction
  drug?: string | null
  detail: string
}

export interface Finding {
  rule_id: string
  outcome: Outcome
  severity: Severity
  order_id?: string | null
  message: string
  evidence: Evidence[]
  suggestion?: Suggestion | null
  missing_inputs: string[]
}

export interface CoverageEstimate {
  regimen: string
  median: number
  lower: number
  upper: number
  p_at_least_target: number
  n_isolates: number
  provenance: DataProvenance
  abstained: boolean
  note: string
}

export interface Evaluation {
  id: string
  episode_id: string
  evaluated_at: string
  trigger: Trigger
  ruleset_version: string
  inputs_hash: string
  status: EvaluationStatus
  findings: Finding[]
  coverage: CoverageEstimate[]
}

// ─── Application layer (backend/stewardship/service.py) ───────────────────────

export interface GuidelinePassage {
  text: string
  document: string
  section: string
  page?: string | null
  distance: number
}

/** A finding as shown to the clinician: rule result + what to do + why. */
export interface FindingView {
  rule_id: string
  outcome: Outcome
  severity: Severity
  order_id?: string | null
  drug?: string | null
  message: string
  action?: string | null
  suggestion_action?: SuggestedAction | null
  missing_inputs: string[]
  evidence: Evidence[]
  explanation: string
  guideline_passages: GuidelinePassage[]
}

export interface CultureSummary {
  state: 'NOT_AVAILABLE' | CultureStatus
  message: string
  action?: string | null
}

export interface SyndromeInfo {
  code: string
  name: string
  antibiotics_indicated: boolean
  culture_required: boolean
  source: string
  page?: string | null
}

/** The engine's Evaluation plus the extra fields the application layer adds. */
export interface EvaluationReport extends Evaluation {
  syndrome?: { code: string | null; name: string | null; resolution: string }
  culture?: CultureSummary
  items?: FindingView[]
  warnings?: string[]
}

export interface CultureInput {
  specimen_type: string
  status: CultureStatus
  isolates: {
    organism: string
    probable_contaminant?: boolean
    susceptibilities: Record<string, SIR>
  }[]
}

/** Body of POST /api/episodes and POST /api/evaluate. */
export interface EpisodeRequest {
  patient: Patient
  setting: Setting
  syndrome_code?: string | null
  diagnosis_text?: string | null
  prescription: string
  confirmed_drugs?: {
    order_id: string
    raw_text: string
    generic: string
  }[]
  cultures: CultureInput[]
}

export interface Review {
  id: string
  episode_id: string
  evaluation_id: string
  finding_rule_id?: string | null
  order_id?: string | null
  reviewer: string
  action: ReviewAction
  reason_code?: ReasonCode | null
  note?: string | null
  at: string
}

export type ReviewPhase = 'INITIAL' | 'ANTIBIOTIC_TIMEOUT_48H'
export type MedicationDisposition =
  | 'CONTINUE'
  | 'MODIFY'
  | 'SWITCH'
  | 'STOP'
  | 'REQUEST_INFO'
  | 'ESCALATE'
export type TreatmentPlanStatus = 'READY' | 'ACTION_REQUIRED'

export interface RegimenSnapshot {
  source_order_id?: string | null
  generic: string
  dose_mg?: number | null
  freq_per_day?: number | null
  route?: Route | null
  total_duration_days?: number | null
  course_started_at: string
  planned_stop_at?: string | null
}

export interface MedicationPlanItem {
  source_order_id: string
  disposition: MedicationDisposition
  before: RegimenSnapshot
  final_regimen?: RegimenSnapshot | null
  reason_code?: string | null
  rationale?: string | null
  linked_findings: string[]
  requested_inputs: string[]
  requested_from?: string | null
  due_at?: string | null
  escalation_destination?: string | null
  escalation_urgency?: string | null
}

export interface PlanNarrative {
  text: string
  source: 'TEMPLATE' | 'LLM'
  generator: string
  generated_at: string
  disclaimer: string
}

export interface TreatmentPlan {
  id: string
  episode_id: string
  evaluation_id: string
  evaluation_inputs_hash: string
  ruleset_version: string
  phase: ReviewPhase
  status: TreatmentPlanStatus
  items: MedicationPlanItem[]
  reviewer: string
  reviewer_role: string
  signed_at: string
  version: number
  supersedes_id?: string | null
  idempotency_key: string
  narrative: PlanNarrative
}

export interface RegimenRequest {
  generic: string
  dose_mg: number
  freq_per_day: number
  route: Route
  total_duration_days: number
  course_started_at: string
}

export interface PlanItemRequest {
  source_order_id: string
  disposition: MedicationDisposition
  final_regimen?: RegimenRequest | null
  reason_code?: string | null
  rationale?: string | null
  linked_findings?: string[]
  requested_inputs?: string[]
  requested_from?: string | null
  due_at?: string | null
  escalation_destination?: string | null
  escalation_urgency?: 'ROUTINE' | 'URGENT' | null
}

export interface TreatmentPlanRequest {
  phase: ReviewPhase
  items: PlanItemRequest[]
  reviewer: string
  reviewer_role: string
  idempotency_key: string
  supersedes_id?: string | null
}

export interface AuditEntry {
  at: string
  actor: string
  action: string
  entity: string
  entity_id: string
  payload: Record<string, unknown>
}

// ─── OCR / Upload types (frontend-specific) ────────────────────────────────────

export interface ExtractedDrug {
  id: string
  raw_text: string
  generic?: string | null
  norm_status: NormStatus
  norm_candidates: string[]
  dose_mg?: number | null
  freq_per_day?: number | null
  route?: Route | null
  duration_days?: number | null
  excluded?: boolean
}

export interface OCRResult {
  success: boolean
  raw_text: string
  drugs: ExtractedDrug[]
  processing_time_ms: number
  model?: string
  warnings?: string[]
}

export interface ParsePrescriptionResult {
  orders: ExtractedDrug[]
  warnings: string[]
}

// ─── Dashboard KPIs (frontend-specific) ───────────────────────────────────────

export interface DashboardStats {
  total_reviewed: number
  flagged_count: number
  pending_review_count: number
  high_severity_count: number
  timeout_due_count: number
  recent_evaluations: RecentEvaluation[]
}

export interface RecentEvaluation {
  evaluation_id: string
  episode_id: string
  patient_id: string
  status: EvaluationStatus
  evaluated_at: string
  high_count: number
  moderate_count: number
}

// ─── 48-hour Review (frontend-specific) ────────────────────────────────────────

export interface TimeoutItem {
  episode_id: string
  patient_id: string
  setting: Setting
  antibiotic_name: string
  started_at: string
  hours_elapsed: number
  status: 'REVIEW_DUE' | 'REVIEWED'
  evaluation_id?: string | null
  plan_id?: string | null
  reviewed_at?: string | null
  reviewed_by?: string | null
}
