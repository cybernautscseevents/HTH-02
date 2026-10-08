'use client'

import React, { useState } from 'react'
import { CheckCircle2, Edit3, AlertOctagon, ChevronDown, Loader2, Check } from 'lucide-react'
import type { Finding, ReviewAction, ReasonCode } from '@/types/stewardship'
import { REASON_CODES } from '@/types/stewardship'
import { Button } from '@/components/ui/Button'

interface ReviewPanelProps {
  finding: Finding
  evaluationId: string
  episodeId: string
  reviewer: string
  onSubmit?: (action: ReviewAction, reasonCode?: ReasonCode, note?: string) => Promise<void>
  disabled?: boolean
}

const REASON_LABELS: Record<string, string> = {
  CLINICAL_JUDGEMENT: 'Clinical judgement',
  CULTURE_PENDING: 'Culture pending',
  PATIENT_FACTOR: 'Patient-specific factor',
  GUIDELINE_EXCEPTION: 'Guideline exception',
  TIMEOUT_DONE: '48-hour review completed',
}

type ReviewState = 'idle' | 'submitting' | 'done'

export const ReviewPanel: React.FC<ReviewPanelProps> = ({
  finding,
  evaluationId,
  episodeId,
  reviewer,
  onSubmit,
  disabled = false,
}) => {
  const [selectedAction, setSelectedAction] = useState<ReviewAction | null>(null)
  const [reasonCode, setReasonCode] = useState<ReasonCode | ''>('')
  const [note, setNote] = useState('')
  const [state, setState] = useState<ReviewState>('idle')
  const [doneAction, setDoneAction] = useState<ReviewAction | null>(null)

  const cannotAssess = finding.outcome === 'CANNOT_ASSESS'

  const handleSubmit = async () => {
    if (!selectedAction) return
    if (selectedAction === 'OVERRIDE' && !reasonCode) return

    setState('submitting')
    try {
      await onSubmit?.(
        selectedAction,
        reasonCode || undefined,
        note || undefined,
      )
      setDoneAction(selectedAction)
      setState('done')
    } catch {
      setState('idle')
    }
  }

  if (state === 'done') {
    return (
      <div className="flex items-center gap-2 py-2">
        <Check className="w-4 h-4 text-emerald-400" />
        <span className="text-sm text-emerald-400 font-medium">
          Review recorded: {doneAction}
        </span>
        <button
          onClick={() => {
            setState('idle')
            setSelectedAction(null)
            setReasonCode('')
            setNote('')
          }}
          className="ml-2 text-xs text-slate-400 hover:text-slate-200 underline transition-colors"
        >
          Undo
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
        Pharmacist Review
      </p>

      {/* Action buttons */}
      <div className="flex flex-wrap gap-2">
        {/* Accept — disabled for CANNOT_ASSESS */}
        <button
          disabled={disabled || cannotAssess}
          onClick={() => setSelectedAction(selectedAction === 'ACCEPT' ? null : 'ACCEPT')}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium border transition-all ${
            selectedAction === 'ACCEPT'
              ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300'
              : 'border-[#3b4263] text-slate-300 hover:border-emerald-500/30 hover:text-emerald-300'
          } disabled:opacity-40 disabled:cursor-not-allowed`}
          title={cannotAssess ? 'Cannot accept a CANNOT_ASSESS finding. Provide missing input or override.' : ''}
        >
          <CheckCircle2 className="w-4 h-4" />
          Accept suggestion
        </button>

        <button
          disabled={disabled}
          onClick={() => setSelectedAction(selectedAction === 'MODIFY' ? null : 'MODIFY')}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium border transition-all ${
            selectedAction === 'MODIFY'
              ? 'bg-indigo-500/20 border-indigo-500/40 text-indigo-300'
              : 'border-[#3b4263] text-slate-300 hover:border-indigo-500/30 hover:text-indigo-300'
          } disabled:opacity-40 disabled:cursor-not-allowed`}
        >
          <Edit3 className="w-4 h-4" />
          Modify plan
        </button>

        <button
          disabled={disabled}
          onClick={() => setSelectedAction(selectedAction === 'OVERRIDE' ? null : 'OVERRIDE')}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium border transition-all ${
            selectedAction === 'OVERRIDE'
              ? 'bg-rose-500/20 border-rose-500/40 text-rose-300'
              : 'border-[#3b4263] text-slate-300 hover:border-rose-500/30 hover:text-rose-300'
          } disabled:opacity-40 disabled:cursor-not-allowed`}
        >
          <AlertOctagon className="w-4 h-4" />
          Override with reason
        </button>
      </div>

      {/* Cannot assess notice */}
      {cannotAssess && (
        <p className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
          This finding cannot be accepted — missing information must be supplied (Modify) or the finding overridden with a documented reason.
        </p>
      )}

      {/* Override/Modify expanded form */}
      {(selectedAction === 'OVERRIDE' || selectedAction === 'MODIFY') && (
        <div className="space-y-3 pt-2">
          {/* Reason code (required for OVERRIDE) */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">
              Reason code {selectedAction === 'OVERRIDE' && <span className="text-rose-400">*</span>}
            </label>
            <div className="relative">
              <select
                value={reasonCode}
                onChange={(e) => setReasonCode(e.target.value as ReasonCode)}
                className="w-full appearance-none bg-[#0f1117] border border-[#2d3148] rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                <option value="">Select reason...</option>
                {REASON_CODES.filter((r) => r !== 'TIMEOUT_DONE').map((code) => (
                  <option key={code} value={code}>
                    {REASON_LABELS[code]}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
            </div>
          </div>

          {/* Free-text note */}
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">
              Justification / note
            </label>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Document your clinical reasoning..."
              rows={3}
              className="w-full bg-[#0f1117] border border-[#2d3148] rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none"
            />
          </div>
        </div>
      )}

      {/* Note for ACCEPT */}
      {selectedAction === 'ACCEPT' && (
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1.5">
            Optional note
          </label>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Add context for the audit log..."
            rows={2}
            className="w-full bg-[#0f1117] border border-[#2d3148] rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none"
          />
        </div>
      )}

      {/* Submit */}
      {selectedAction && (
        <div className="flex items-center gap-3 pt-1">
          <Button
            variant={
              selectedAction === 'ACCEPT'
                ? 'success'
                : selectedAction === 'OVERRIDE'
                ? 'danger'
                : 'primary'
            }
            size="sm"
            isLoading={state === 'submitting'}
            disabled={selectedAction === 'OVERRIDE' && !reasonCode}
            onClick={handleSubmit}
          >
            {state === 'submitting' ? (
              'Submitting...'
            ) : selectedAction === 'ACCEPT' ? (
              'Confirm acceptance'
            ) : selectedAction === 'MODIFY' ? (
              'Record modification'
            ) : (
              'Submit override'
            )}
          </Button>
          <button
            onClick={() => {
              setSelectedAction(null)
              setReasonCode('')
              setNote('')
            }}
            className="text-xs text-slate-400 hover:text-slate-200 transition-colors"
          >
            Cancel
          </button>
          {reviewer && (
            <span className="text-[11px] text-slate-500 ml-auto">
              as {reviewer}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
