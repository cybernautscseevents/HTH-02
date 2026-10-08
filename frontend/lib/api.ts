/**
 * API layer for the Antibiotic Stewardship Copilot.
 *
 * All functions are async and typed. When USE_MOCK is true they return mock data.
 * To wire up the real backend, set USE_MOCK = false and fill in BASE_URL.
 * No other files need to change.
 */

import type {
  AuditEntry,
  DashboardStats,
  Episode,
  EpisodeRequest,
  Evaluation,
  EvaluationReport,
  SyndromeInfo,
  OCRResult,
  Review,
  TimeoutItem,
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

/** Mock data is used unless NEXT_PUBLIC_USE_MOCK=false (see frontend/.env.example). */
const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== 'false'

/** Base URL of the stewardship API (ignored when USE_MOCK = true). */
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

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

// ─── Dashboard ─────────────────────────────────────────────────────────────────

export async function getStats(): Promise<DashboardStats> {
  if (USE_MOCK) {
    await delay(400)
    return MOCK_STATS
  }
  return apiFetch<DashboardStats>('/api/stats')
}

// ─── Upload / OCR ──────────────────────────────────────────────────────────────

export async function uploadPrescription(file: File): Promise<OCRResult> {
  if (USE_MOCK) {
    // Simulate OCR processing time
    await delay(2200)
    return MOCK_OCR_RESULT
  }
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE_URL}/api/ocr`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(`OCR API error ${res.status}`)
  return res.json() as Promise<OCRResult>
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

// ─── Evaluation ────────────────────────────────────────────────────────────────

export async function evaluateEpisode(episodeId: string): Promise<EvaluationReport> {
  if (USE_MOCK) {
    // Simulate engine processing time
    await delay(1800)
    return { ...MOCK_EVALUATION, episode_id: episodeId }
  }
  return apiFetch<EvaluationReport>(`/api/episodes/${episodeId}/evaluate`, {
    method: 'POST',
  })
}

export async function getEvaluation(evaluationId: string): Promise<EvaluationReport> {
  if (USE_MOCK) {
    await delay(300)
    return MOCK_EVALUATION
  }
  return apiFetch<EvaluationReport>(`/api/evaluations/${evaluationId}`)
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

export async function getTimeoutDue(): Promise<TimeoutItem[]> {
  if (USE_MOCK) {
    await delay(300)
    return MOCK_TIMEOUTS
  }
  return apiFetch<TimeoutItem[]>('/api/timeout-due')
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
