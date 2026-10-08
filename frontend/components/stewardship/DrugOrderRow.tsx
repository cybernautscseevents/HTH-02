'use client'

import React, { useState } from 'react'
import { AlertTriangle, CheckCircle2, CircleSlash2, XCircle } from 'lucide-react'
import type { ExtractedDrug } from '@/types/stewardship'

interface DrugOrderRowProps {
  drug: ExtractedDrug
  onConfirm?: (id: string, generic: string) => void
  onExclude?: (id: string) => void
}

export const DrugOrderRow: React.FC<DrugOrderRowProps> = ({ drug, onConfirm, onExclude }) => {
  const [manualGeneric, setManualGeneric] = useState('')
  const ambiguous = drug.norm_status === 'AMBIGUOUS'
  const unmatched = drug.norm_status === 'NO_MATCH'

  if (drug.excluded) {
    return (
      <div className="flex items-center gap-3 rounded-md border border-[#E2E1DC] bg-[#F4F3EF] p-3 text-[#6B6A65]">
        <CircleSlash2 className="h-4 w-4" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium">Excluded from antibiotic stewardship</p>
          <p className="truncate font-mono text-[10px]">{drug.raw_text}</p>
        </div>
      </div>
    )
  }

  return (
    <div
      className={`rounded-md border p-4 ${
        ambiguous
          ? 'border-[#E8D5A7] bg-[#FFF9EB]'
          : unmatched
          ? 'border-[#D9A4A4] bg-[#FDF2F2]'
          : 'border-[#E2E1DC] bg-white'
      }`}
    >
      <div className="flex items-start gap-3">
        {drug.norm_status === 'ACCEPTED' || drug.norm_status === 'CONFIRMED' ? (
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[#1A6B3C]" />
        ) : ambiguous ? (
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[#8B5E00]" />
        ) : (
          <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-[#8B1A1A]" />
        )}

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium capitalize text-[#1A1A1A]">
              {drug.generic ?? (ambiguous ? 'Confirmation required' : 'Unknown medication')}
            </p>
            <span className="rounded-full border border-current/20 px-2 py-0.5 text-[10px] font-medium text-[#6B6A65]">
              {drug.norm_status.replace('_', ' ')}
            </span>
          </div>
          <p className="mt-1 font-mono text-xs text-[#6B6A65]">“{drug.raw_text}”</p>

          <div className="mt-2 flex flex-wrap gap-1.5">
            {drug.dose_mg && <span className="rounded border border-[#E2E1DC] bg-[#F4F3EF] px-2 py-0.5 font-mono text-[10px] text-[#1A1A1A]">{drug.dose_mg >= 1000 ? `${drug.dose_mg / 1000} g` : `${drug.dose_mg} mg`}</span>}
            {drug.freq_per_day && <span className="rounded border border-[#E2E1DC] bg-[#F4F3EF] px-2 py-0.5 font-mono text-[10px] text-[#1A1A1A]">{drug.freq_per_day}×/day</span>}
            {drug.route && <span className="rounded border border-[#E2E1DC] bg-[#F4F3EF] px-2 py-0.5 font-mono text-[10px] text-[#1A1A1A]">{drug.route}</span>}
            {drug.duration_days && <span className="rounded border border-[#E2E1DC] bg-[#F4F3EF] px-2 py-0.5 font-mono text-[10px] text-[#1A1A1A]">{drug.duration_days} days</span>}
          </div>

          {ambiguous && drug.norm_candidates.length > 0 && (
            <div className="mt-3">
              <p className="text-[11px] font-medium text-[#8B5E00]">Select the drug shown in the prescription:</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {drug.norm_candidates.map((candidate) => (
                  <button
                    key={candidate}
                    type="button"
                    onClick={() => onConfirm?.(drug.id, candidate)}
                    className="rounded-md border border-[#D8B15B] bg-white px-2.5 py-1.5 text-xs capitalize text-[#8B5E00] hover:bg-[#FFF2D1]"
                  >
                    {candidate}
                  </button>
                ))}
              </div>
            </div>
          )}

          {unmatched && (
            <div className="mt-3 space-y-2 border-t border-[#E8C4C4] pt-3">
              <p className="text-xs text-[#8B1A1A]">
                The antibiotic catalog could not identify this line. Confirm a catalog generic only after checking the source, or exclude it if it is not an antibiotic.
              </p>
              <div className="flex flex-col gap-2 sm:flex-row">
                <input
                  value={manualGeneric}
                  onChange={(event) => setManualGeneric(event.target.value)}
                  placeholder="Confirmed antibiotic generic"
                  className="min-w-0 flex-1 rounded-md border border-[#D9A4A4] bg-white px-2.5 py-1.5 text-xs text-[#1A1A1A] outline-none focus:border-[#8B1A1A]"
                />
                <button
                  type="button"
                  disabled={!manualGeneric.trim()}
                  onClick={() => onConfirm?.(drug.id, manualGeneric.trim())}
                  className="rounded-md border border-[#D9A4A4] bg-white px-3 py-1.5 text-xs font-medium text-[#8B1A1A] disabled:opacity-40"
                >
                  Confirm antibiotic
                </button>
                <button
                  type="button"
                  onClick={() => onExclude?.(drug.id)}
                  className="rounded-md border border-[#C8C7C0] bg-white px-3 py-1.5 text-xs font-medium text-[#1A1A1A] hover:bg-[#F4F3EF]"
                >
                  Not an antibiotic
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
