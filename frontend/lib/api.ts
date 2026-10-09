/**
 * API layer for the Antibiotic Stewardship Copilot.
 *
 * All functions are async and typed. When USE_MOCK is true they return mock data.
 * To wire up the real backend, set USE_MOCK = false and fill in BASE_URL.
 * No other files need to change.
 */

import type {
  AuditEntry,
  CultureInput,
  DashboardStats,
  Episode,
  EpisodeRequest,
  Evaluation,
  EvaluationReport,
  SyndromeInfo,
  OCRResult,
  ParsePrescriptionResult,
  PatientChanges,
  PatientRecord,
  Review,
  TimeoutConfig,
  TimeoutItem,
  TreatmentPlan,
  TreatmentPlanRequest,
  Trigger,
} from '@/types/stewardship'
import {
  MOCK_AUDIT_LOG,
  MOCK_EPISODE,
  MOCK_EVALUATION,
  MOCK_OCR_RESULT,
  MOCK_STATS,
  MOCK_TIMEOUTS,
} from '@/lib/mock-data'

// ─── Configuration ─────────────────────────────────────────────────────────────

/** Real API is the default; set NEXT_PUBLIC_USE_MOCK=true for the offline visual demo. */
const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === 'true'

/** Base URL of the stewardship API (ignored when USE_MOCK = true). */
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
const mockPlans = new Map<string, TreatmentPlan[]>()

// ─── Helpers ───────────────────────────────────────────────────────────────────

function delay(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    // The backend explains a rejected request in `detail`; show that, not just the status.
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ? String(body.detail) : `API error ${res.status}: ${path}`)
  }
  return res.json() as Promise<T>
}

// ─── Health ────────────────────────────────────────────────────────────────────

/** Backend status and the version of the guideline rule pack it evaluates with. */
export async function getHealth(): Promise<{ status: string; ruleset_version: string }> {
  if (USE_MOCK) return { status: 'ok', ruleset_version: 'mock data' }
  return apiFetch<{ status: string; ruleset_version: string }>('/api/health')
}

// ─── Dashboard ─────────────────────────────────────────────────────────────────

export async function getStats(): Promise<DashboardStats> {
  if (USE_MOCK) {
    await delay(400)
    return MOCK_STATS
  }
  return apiFetch<DashboardStats>('/api/stats')
}

// ─── Upload / OCR ──────────────────────────────────────────────────────────────

export async function uploadPrescription(
  file: File,
  engine: 'glm' | 'qwen' = 'glm'
): Promise<OCRResult> {
  if (USE_MOCK) {
    await delay(1200)
    return MOCK_OCR_RESULT
  }
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE_URL}/api/ocr?engine=${engine}`, { method: 'POST', body: form })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ? String(body.detail) : `OCR API error ${res.status}`)
  }
  return res.json() as Promise<OCRResult>
}

export async function parsePrescriptionText(text: string): Promise<ParsePrescriptionResult> {
  if (USE_MOCK) {
    await delay(350)
    return { orders: MOCK_OCR_RESULT.drugs, warnings: [] }
  }
  return apiFetch<ParsePrescriptionResult>('/api/parse-prescription', {
    method: 'POST',
    body: JSON.stringify({ text }),
  })
}

// ─── Patient record ────────────────────────────────────────────────────────────

/** Hospital record for a patient ID, to pre-fill the form. Throws when there is none. */
export async function getPatientRecord(patientId: string): Promise<PatientRecord> {
  if (USE_MOCK) {
    await delay(300)
    return { patient: { ...MOCK_EPISODE.patient, id: patientId }, cultures: [], source: 'mock data' }
  }
  return apiFetch<PatientRecord>(`/api/patients/${encodeURIComponent(patientId)}`)
}

// ─── Episode ───────────────────────────────────────────────────────────────────

/** Syndrome codes the engine accepts: exactly the guideline rule pack. */
export async function getSyndromes(): Promise<SyndromeInfo[]> {
  if (USE_MOCK) return []
  return apiFetch<SyndromeInfo[]>('/api/syndromes')
}

export async function createEpisode(data: EpisodeRequest): Promise<Episode> {
  if (USE_MOCK) {
    await delay(500)
    return {
      ...MOCK_EPISODE,
      patient: data.patient,
      setting: data.setting,
      syndrome_code: data.syndrome_code ?? null,
      diagnosis_text: data.diagnosis_text ?? null,
      id: `EP-${Date.now()}`,
    }
  }
  return apiFetch<Episode>('/api/episodes', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getEpisode(episodeId: string): Promise<Episode> {
  if (USE_MOCK) {
    await delay(300)
    return MOCK_EPISODE
  }
  return apiFetch<Episode>(`/api/episodes/${episodeId}`)
}

export async function getEpisodes(hasCulture = false): Promise<Episode[]> {
  if (USE_MOCK) {
    await delay(300)
    return hasCulture ? [MOCK_EPISODE] : [MOCK_EPISODE]
  }
  return apiFetch<Episode[]>(`/api/episodes${hasCulture ? '?has_culture=true' : ''}`)
}

// ─── Evaluation ────────────────────────────────────────────────────────────────

/** Attach a culture reported after the episode was created; returns the re-evaluation. */
export async function addCulture(episodeId: string, culture: CultureInput): Promise<EvaluationReport> {
  if (USE_MOCK) {
    await delay(800)
    return { ...MOCK_EVALUATION, episode_id: episodeId, trigger: 'CULTURE_RESULT' }
  }
  return apiFetch<EvaluationReport>(`/api/episodes/${episodeId}/cultures`, {
    method: 'POST',
    body: JSON.stringify(culture),
  })
}

export async function evaluateEpisode(
  episodeId: string,
  trigger: Trigger = 'NEW_PRESCRIPTION'
): Promise<EvaluationReport> {
  if (USE_MOCK) {
    // Simulate engine processing time
    await delay(1800)
    return { ...MOCK_EVALUATION, episode_id: episodeId }
  }
  return apiFetch<EvaluationReport>(
    `/api/episodes/${episodeId}/evaluate?trigger=${encodeURIComponent(trigger)}`,
    { method: 'POST' }
  )
}

/** Re-run the rules with changed patient values. The result is not stored or reviewable. */
export async function whatIfEpisode(
  episodeId: string,
  changes: PatientChanges
): Promise<EvaluationReport> {
  if (USE_MOCK) {
    await delay(200)
    return { ...MOCK_EVALUATION, episode_id: episodeId }
  }
  return apiFetch<EvaluationReport>(`/api/episodes/${episodeId}/what-if`, {
    method: 'POST',
    body: JSON.stringify(changes),
  })
}

export async function getEvaluation(evaluationId: string): Promise<EvaluationReport> {
  if (USE_MOCK) {
    await delay(300)
    return MOCK_EVALUATION
  }
  return apiFetch<EvaluationReport>(`/api/evaluations/${evaluationId}`)
}

export async function getEvaluationReviews(evaluationId: string): Promise<Review[]> {
  if (USE_MOCK) return []
  return apiFetch<Review[]>(`/api/evaluations/${evaluationId}/reviews`)
}

export async function getTreatmentPlans(evaluationId: string): Promise<TreatmentPlan[]> {
  if (USE_MOCK) return mockPlans.get(evaluationId) ?? []
  return apiFetch<TreatmentPlan[]>(`/api/evaluations/${evaluationId}/treatment-plans`)
}

export async function getLatestTreatmentPlan(evaluationId: string): Promise<TreatmentPlan | null> {
  const plans = await getTreatmentPlans(evaluationId)
  return plans[0] ?? null
}

export async function signTreatmentPlan(
  evaluationId: string,
  request: TreatmentPlanRequest
): Promise<TreatmentPlan> {
  if (USE_MOCK) throw new Error('Treatment-plan sign-off requires the backend.')
  return apiFetch<TreatmentPlan>(`/api/evaluations/${evaluationId}/treatment-plans`, {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

// ─── Review ────────────────────────────────────────────────────────────────────

export async function submitReview(review: Omit<Review, 'id' | 'at'>): Promise<AuditEntry> {
  if (USE_MOCK) {
    await delay(600)
    const entry: AuditEntry = {
      at: new Date().toISOString(),
      actor: review.reviewer,
      action: `review.${review.action}`,
      entity: review.finding_rule_id ? 'finding' : 'episode',
      entity_id: review.finding_rule_id
        ? `${review.evaluation_id}:${review.finding_rule_id}:${review.order_id ?? 'null'}`
        : review.episode_id,
      payload: review as unknown as Record<string, unknown>,
    }
    return entry
  }
  return apiFetch<AuditEntry>('/api/reviews', {
    method: 'POST',
    body: JSON.stringify(review),
  })
}

// ─── Culture / 48h Review ─────────────────────────────────────────────────────

export async function getTimeoutConfig(): Promise<TimeoutConfig> {
  if (USE_MOCK) return { review_due_after_minutes: 48 * 60, demo_mode: false }
  return apiFetch<TimeoutConfig>('/api/timeouts/config')
}

export async function getTimeoutDue(): Promise<TimeoutItem[]> {
  if (USE_MOCK) {
    await delay(300)
    return MOCK_TIMEOUTS
  }
  return apiFetch<TimeoutItem[]>('/api/timeouts?status=all')
}

// ─── Audit Log ─────────────────────────────────────────────────────────────────

export async function getAuditLog(entityId?: string): Promise<AuditEntry[]> {
  if (USE_MOCK) {
    await delay(300)
    if (entityId) return MOCK_AUDIT_LOG.filter((e) => e.entity_id.includes(entityId))
    return MOCK_AUDIT_LOG
  }
  const qs = entityId ? `?entity_id=${entityId}` : ''
  return apiFetch<AuditEntry[]>(`/api/audit${qs}`)
}
