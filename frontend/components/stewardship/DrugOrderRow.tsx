'use client'

import React from 'react'
import { CheckCircle2, AlertTriangle, XCircle, HelpCircle } from 'lucide-react'
import type { ExtractedDrug } from '@/types/stewardship'
import { Badge } from '@/components/ui/Badge'

interface DrugOrderRowProps {
  drug: ExtractedDrug
  onConfirm?: (id: string, confirmed: string) => void
}

const ROUTE_LABELS: Record<string, string> = {
  PO: 'Oral',
  IV: 'IV',
  IM: 'IM',
}

export const DrugOrderRow: React.FC<DrugOrderRowProps> = ({ drug, onConfirm }) => {
  const isAmbiguous = drug.norm_status === 'AMBIGUOUS'
  const isNoMatch = drug.norm_status === 'NO_MATCH'
  const confidencePct = Math.round(drug.confidence * 100)

  return (
    <div
      className={`p-4 rounded-xl border transition-all ${
        isAmbiguous
          ? 'border-amber-500/30 bg-amber-500/5'
          : isNoMatch
          ? 'border-rose-500/30 bg-rose-500/5'
          : 'border-[#2d3148] bg-[#1e2235]'
      }`}
    >
      <div className="flex items-start gap-3">
        {/* Status icon */}
        <div className="mt-0.5 shrink-0">
          {drug.norm_status === 'ACCEPTED' || drug.norm_status === 'CONFIRMED' ? (
            <CheckCircle2 className="w-5 h-5 text-emerald-400" />
          ) : isAmbiguous ? (
            <AlertTriangle className="w-5 h-5 text-amber-400" />
          ) : (
            <XCircle className="w-5 h-5 text-rose-400" />
          )}
        </div>

        <div className="flex-1 min-w-0">
          {/* Drug name header */}
          <div className="flex flex-wrap items-center gap-2 mb-1">
            {drug.generic ? (
              <span className="text-sm font-semibold text-slate-100 capitalize">{drug.generic}</span>
            ) : (
              <span className="text-sm font-semibold text-slate-400 italic">Unknown drug</span>
            )}
            <Badge variant={drug.norm_status} size="sm">
              {drug.norm_status === 'ACCEPTED'
                ? 'Matched'
                : drug.norm_status === 'CONFIRMED'
                ? 'Confirmed'
                : drug.norm_status === 'AMBIGUOUS'
                ? 'Ambiguous'
                : 'No match'}
            </Badge>

            {/* Confidence pill */}
            <span
              className={`text-[11px] font-mono px-2 py-0.5 rounded-full border ${
                drug.confidence >= 0.85
                  ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20'
                  : drug.confidence >= 0.6
                  ? 'bg-amber-500/10 text-amber-300 border-amber-500/20'
                  : 'bg-rose-500/10 text-rose-300 border-rose-500/20'
              }`}
            >
              {confidencePct}% confidence
            </span>
          </div>

          {/* Raw text → normalized */}
          <p className="text-xs text-slate-400">
            <span className="font-mono text-slate-500">&ldquo;{drug.raw_text}&rdquo;</span>
          </p>

          {/* Drug details chips */}
          <div className="flex flex-wrap gap-1.5 mt-2">
            {drug.dose_mg && (
              <span className="text-[11px] px-2 py-0.5 rounded bg-[#141724] border border-[#2d3148] text-slate-300 font-mono">
                {drug.dose_mg >= 1000 ? `${drug.dose_mg / 1000} g` : `${drug.dose_mg} mg`}
              </span>
            )}
            {drug.freq_per_day && (
              <span className="text-[11px] px-2 py-0.5 rounded bg-[#141724] border border-[#2d3148] text-slate-300">
                {drug.freq_per_day}×/day
              </span>
            )}
            {drug.route && (
              <span className="text-[11px] px-2 py-0.5 rounded bg-[#141724] border border-[#2d3148] text-slate-300">
                {ROUTE_LABELS[drug.route] ?? drug.route}
              </span>
            )}
            {drug.duration_days && (
              <span className="text-[11px] px-2 py-0.5 rounded bg-[#141724] border border-[#2d3148] text-slate-300">
                {drug.duration_days} days
              </span>
            )}
          </div>

          {/* Ambiguous: show candidates + confirmation UI */}
          {isAmbiguous && drug.norm_candidates.length > 0 && (
            <div className="mt-3 p-3 rounded-lg bg-amber-500/5 border border-amber-500/20">
              <div className="flex items-center gap-1.5 mb-2">
                <HelpCircle className="w-3.5 h-3.5 text-amber-400" />
                <span className="text-xs font-semibold text-amber-300">
                  Confirmation required — multiple matches found
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {drug.norm_candidates.map((candidate) => (
                  <button
                    key={candidate}
                    onClick={() => onConfirm?.(drug.id, candidate)}
                    className="text-xs px-2.5 py-1 rounded-lg border border-amber-500/30 text-amber-300 hover:bg-amber-500/20 transition-colors font-mono capitalize"
                  >
                    {candidate}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-[10px] text-amber-400/70">
                Select the correct drug to proceed with evaluation.
              </p>
            </div>
          )}

          {/* No match: manual entry needed */}
          {isNoMatch && (
            <div className="mt-3 p-3 rounded-lg bg-rose-500/5 border border-rose-500/20">
              <p className="text-xs text-rose-300">
                Drug could not be matched. Manual review required before evaluation.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
