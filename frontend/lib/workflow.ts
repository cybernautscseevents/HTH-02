/**
 * Client-side state of the five-stage review workflow.
 *
 * Stages: 1 prescription, 2 clinical context, 3 rule analysis, 4 finding review, 5 final plan.
 * Stages 1 and 2 are inputs and stay editable. Stages 3 to 5 are results derived from them.
 * When an input changes, `invalidateResults()` retires the evaluation built from the old
 * inputs: it can no longer be shown or acted on, and the user must run the stages again.
 *
 * The active chain lives in sessionStorage (one per tab). Retired evaluation ids live in
 * localStorage so a stale result stays hidden in every tab. Both are wrapped in try/catch;
 * without storage the workflow just starts from stage 1.
 */

import { useCallback, useEffect, useState } from 'react'
import type { Finding, Review } from '@/types/stewardship'

const CHAIN_KEY = 'rxWorkflow'
const RETIRED_KEY = 'rxRetiredEvaluations'
const CONTEXT_KEY = 'rxContext'
// Written by the prescription stage and read by the clinical-context stage.
const STAGE_INPUT_KEYS = ['pendingDrugs', 'rxReview', 'ocrRawText', 'rxDiagnosis', 'rxPatient', CONTEXT_KEY]

export interface Chain {
  /** Fingerprint of the prescription the results were built from. */
  rxFingerprint: string | null
  /** Fingerprint of the clinical-context form that produced `evaluationId`. */
  contextFingerprint: string | null
  episodeId: string | null
  evaluationId: string | null
}

const EMPTY: Chain = { rxFingerprint: null, contextFingerprint: null, episodeId: null, evaluationId: null }

export function getChain(): Chain {
  try {
    const raw = sessionStorage.getItem(CHAIN_KEY)
    return raw ? { ...EMPTY, ...JSON.parse(raw) } : EMPTY
  } catch {
    return EMPTY
  }
}

export function setChain(patch: Partial<Chain>): Chain {
  const next = { ...getChain(), ...patch }
  try {
    sessionStorage.setItem(CHAIN_KEY, JSON.stringify(next))
  } catch {
    /* no storage: nothing is remembered */
  }
  return next
}

function retired(): string[] {
  try {
    return JSON.parse(localStorage.getItem(RETIRED_KEY) ?? '[]')
  } catch {
    return []
  }
}

/** True when the evaluation was built from inputs that have since changed. */
export function isRetired(evaluationId: string): boolean {
  return retired().includes(evaluationId)
}

/** Retire the current evaluation (stages 3 to 5). Returns true when there was one. */
export function invalidateResults(): boolean {
  const { evaluationId } = getChain()
  if (!evaluationId) return false
  try {
    localStorage.setItem(RETIRED_KEY, JSON.stringify([...retired(), evaluationId].slice(-200)))
  } catch {
    /* ignore */
  }
  setChain({ evaluationId: null, episodeId: null, contextFingerprint: null })
  return true
}

/** A new prescription starts a new review: forget every stage input and result. */
export function clearWorkflow() {
  try {
    sessionStorage.removeItem(CHAIN_KEY)
    STAGE_INPUT_KEYS.forEach((key) => sessionStorage.removeItem(key))
  } catch {
    /* ignore */
  }
}

/** The prescription changed: results are retired and the saved text is rebuilt from the orders. */
export function prescriptionChanged() {
  invalidateResults()
  try {
    const saved = sessionStorage.getItem(CONTEXT_KEY)
    if (saved) {
      const { prescription: _dropped, ...rest } = JSON.parse(saved)
      sessionStorage.setItem(CONTEXT_KEY, JSON.stringify(rest))
    }
  } catch {
    /* ignore */
  }
}

export const contextKey = CONTEXT_KEY

/**
 * The stepper links a page may offer. Going back is always free. Going forward needs every
 * stage before the target to be complete, so `completeThrough` is the highest finished stage.
 */
export function reachableLinks(
  current: number,
  completeThrough: number,
  hrefs: Partial<Record<1 | 2 | 3 | 4 | 5, string>>
): Partial<Record<1 | 2 | 3 | 4 | 5, string>> {
  const out: Partial<Record<1 | 2 | 3 | 4 | 5, string>> = {}
  for (const key of [1, 2, 3, 4, 5] as const) {
    const href = hrefs[key]
    if (!href || key === current) continue
    if (key < current || key <= completeThrough + 1) out[key] = href
  }
  return out
}

/** The active chain, read after mount (storage does not exist during server rendering). */
export function useChain(): [Chain, () => void] {
  const [chain, setValue] = useState<Chain>(EMPTY)
  const refresh = useCallback(() => setValue(getChain()), [])
  useEffect(refresh, [refresh])
  return [chain, refresh]
}

/** Findings that still need a pharmacist decision. Stage 4 is complete when this is empty. */
export function unreviewedFindings(findings: Finding[], reviews: Review[]): Finding[] {
  return findings.filter(
    (f) =>
      f.outcome !== 'PASS' &&
      !reviews.some(
        (r) => r.finding_rule_id === f.rule_id && (r.order_id ?? null) === (f.order_id ?? null)
      )
  )
}

/** True when a decision was recorded after the plan was signed, so the plan is out of date. */
export function planIsStale(signedAt: string, reviews: Review[]): boolean {
  return reviews.some((r) => Date.parse(r.at) > Date.parse(signedAt))
}
