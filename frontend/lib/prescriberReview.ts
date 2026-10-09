/**
 * The doctor's review of a plan the pharmacist signed.
 *
 * Demo only: reviews live in this browser's localStorage, keyed by plan id, and never reach the
 * backend. They are merged into the audit log on screen so the trail reads as one record.
 */

import type { AuditEntry } from '@/types/stewardship'

export type PrescriberDecision = 'APPROVED' | 'CHANGES_REQUESTED'

export interface PrescriberReview {
  plan_id: string
  evaluation_id: string
  decision: PrescriberDecision
  comment: string | null
  by: string
  at: string
}

const KEY = 'rxPrescriberReviews'

export function getPrescriberReviews(): Record<string, PrescriberReview> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '{}')
  } catch {
    return {}
  }
}

export function savePrescriberReview(review: PrescriberReview): void {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...getPrescriberReviews(), [review.plan_id]: review }))
  } catch {
    /* no storage: the review lasts until the page reloads */
  }
}

/** Prescriber reviews in the audit-log shape. */
export function prescriberReviewEntries(): AuditEntry[] {
  return Object.values(getPrescriberReviews()).map((review) => ({
    at: review.at,
    actor: review.by,
    action: `plan_review.${review.decision}`,
    entity: 'treatment_plan',
    entity_id: review.plan_id,
    payload: { note: review.comment, reviewer_role: 'PHYSICIAN' },
  }))
}
