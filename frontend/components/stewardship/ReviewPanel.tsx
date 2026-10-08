'use client'

import React, { useEffect, useState } from 'react'
import { CheckCircle2, ChevronDown, Edit3, Trash2 } from 'lucide-react'
import type { Finding, ReasonCode, Review, ReviewAction } from '@/types/stewardship'
import { REASON_CODES } from '@/types/stewardship'
import { Button } from '@/components/ui/Button'

interface ReviewPanelProps {
  finding: Finding
  reviewer: string
  review?: Review
  onSubmit?: (action: ReviewAction, reasonCode?: ReasonCode, note?: string) => Promise<void>
}

const reasonLabels: Record<string, string> = {
  CLINICAL_JUDGEMENT: 'Clinical judgement',
  CULTURE_PENDING: 'Culture pending',
  PATIENT_FACTOR: 'Patient-specific factor',
  GUIDELINE_EXCEPTION: 'Guideline exception',
  TIMEOUT_DONE: '48-hour review completed',
}

const decisionStyles: Record<string, { label: string; box: string; text: string }> = {
  ACCEPT: { label: 'Approved', box: 'border-[#A9CFB7] bg-[#F0FBF4]', text: 'text-[#1A6B3C]' },
  MODIFY: { label: 'Modified', box: 'border-[#E8D5A7] bg-[#FFF9EB]', text: 'text-[#8B5E00]' },
  REMOVE: { label: 'Removed', box: 'border-[#D9A4A4] bg-[#FDF2F2]', text: 'text-[#8B1A1A]' },
  OVERRIDE: { label: 'Overridden', box: 'border-[#D9A4A4] bg-[#FDF2F2]', text: 'text-[#8B1A1A]' },
  ESCALATE: { label: 'Escalated', box: 'border-[#E9BE91] bg-[#FFF5EB]', text: 'text-[#934B13]' },
}

export const ReviewPanel: React.FC<ReviewPanelProps> = ({
  finding,
  reviewer,
  review,
  onSubmit,
}) => {
  const [action, setAction] = useState<ReviewAction | null>(null)
  const [reason, setReason] = useState<ReasonCode | ''>('')
  const [note, setNote] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submittedAction, setSubmittedAction] = useState<ReviewAction | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (review) setSubmittedAction(review.action)
  }, [review])

  const decision = review?.action ?? submittedAction
  if (decision) {
    const style = decisionStyles[decision]
    return (
      <div className={`rounded-md border px-4 py-3 ${style.box}`}>
        <div className="flex items-center gap-2">
          <CheckCircle2 className={`h-4 w-4 ${style.text}`} />
          <span className={`text-sm font-medium ${style.text}`}>{style.label}</span>
          <span className="ml-auto text-[10px] text-[#6B6A65]">{review?.reviewer ?? reviewer}</span>
        </div>
        {(review?.reason_code || review?.note) && (
          <p className="mt-1.5 text-xs text-[#6B6A65]">
            {review.reason_code ? reasonLabels[review.reason_code] ?? review.reason_code : ''}
            {review.reason_code && review.note ? ' — ' : ''}
            {review.note ?? ''}
          </p>
        )}
        <p className="mt-2 text-[10px] text-[#6B6A65]">
          Recorded in the audit log. Apply medication changes in the prescribing system.
        </p>
      </div>
    )
  }

  const needsReason = action === 'MODIFY' || action === 'REMOVE'
  const cannotApprove = finding.outcome === 'CANNOT_ASSESS'

  const submit = async () => {
    if (!action || (needsReason && !reason)) return
    setSubmitting(true)
    setError(null)
    try {
      await onSubmit?.(action, reason || undefined, note || undefined)
      setSubmittedAction(action)
      setAction(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not record the review.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-3">
      <div>
        <p className="text-[11px] font-medium uppercase tracking-[0.06em] text-[#6B6A65]">Pharmacist decision</p>
        <p className="mt-0.5 text-xs text-[#6B6A65]">Choose what should happen to this recommendation.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          disabled={cannotApprove}
          onClick={() => setAction(action === 'ACCEPT' ? null : 'ACCEPT')}
          className={`flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium ${
            action === 'ACCEPT' ? 'border-[#1A6B3C] bg-[#F0FBF4] text-[#1A6B3C]' : 'border-[#C8C7C0] bg-white text-[#1A1A1A]'
          } disabled:cursor-not-allowed disabled:opacity-40`}
        >
          <CheckCircle2 className="h-3.5 w-3.5" /> Approve
        </button>
        <button
          onClick={() => setAction(action === 'MODIFY' ? null : 'MODIFY')}
          className={`flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium ${
            action === 'MODIFY' ? 'border-[#D8B15B] bg-[#FFF9EB] text-[#8B5E00]' : 'border-[#C8C7C0] bg-white text-[#1A1A1A]'
          }`}
        >
          <Edit3 className="h-3.5 w-3.5" /> Modify
        </button>
        <button
          onClick={() => setAction(action === 'REMOVE' ? null : 'REMOVE')}
          className={`flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium ${
            action === 'REMOVE' ? 'border-[#B95A5A] bg-[#FDF2F2] text-[#8B1A1A]' : 'border-[#C8C7C0] bg-white text-[#1A1A1A]'
          }`}
        >
          <Trash2 className="h-3.5 w-3.5" /> Remove
        </button>
      </div>

      {cannotApprove && (
        <p className="rounded-md border border-[#E8D5A7] bg-[#FFF9EB] px-3 py-2 text-xs text-[#8B5E00]">
          Missing information cannot be approved. Supply it, modify the plan, or remove the order with a reason.
        </p>
      )}

      {action && (
        <div className="space-y-3 border-t border-[#E2E1DC] pt-3">
          {needsReason && (
            <label className="block text-xs text-[#6B6A65]">
              Reason <span className="text-[#8B1A1A]">*</span>
              <span className="relative mt-1.5 block">
                <select
                  value={reason}
                  onChange={(event) => setReason(event.target.value as ReasonCode)}
                  className="w-full appearance-none rounded-md border border-[#C8C7C0] bg-white px-3 py-2 text-sm text-[#1A1A1A] outline-none focus:border-[#3730A3]"
                >
                  <option value="">Select reason...</option>
                  {REASON_CODES.filter((code) => code !== 'TIMEOUT_DONE').map((code) => (
                    <option key={code} value={code}>{reasonLabels[code]}</option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#6B6A65]" />
              </span>
            </label>
          )}
          <label className="block text-xs text-[#6B6A65]">
            Clinical note {action === 'ACCEPT' && <span className="text-[#8B8982]">(optional)</span>}
            <textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              rows={2}
              className="mt-1.5 w-full resize-y rounded-md border border-[#C8C7C0] bg-white px-3 py-2 text-sm text-[#1A1A1A] outline-none focus:border-[#3730A3]"
              placeholder="Document the decision for the audit trail"
            />
          </label>
          {error && <p className="text-xs text-[#8B1A1A]">{error}</p>}
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant={action === 'ACCEPT' ? 'success' : action === 'MODIFY' ? 'warning' : 'danger'}
              isLoading={submitting}
              disabled={needsReason && !reason}
              onClick={submit}
            >
              {action === 'ACCEPT' ? 'Approve finding' : action === 'MODIFY' ? 'Record modification' : 'Record removal'}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => { setAction(null); setReason(''); setNote('') }}>Cancel</Button>
          </div>
        </div>
      )}
    </div>
  )
}
