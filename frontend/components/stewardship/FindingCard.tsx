'use client'

import React, { useState } from 'react'
import { ChevronDown, ChevronUp, BookOpen, AlertTriangle, Info } from 'lucide-react'
import type { Finding, FindingView } from '@/types/stewardship'
import { Badge } from '@/components/ui/Badge'

interface FindingCardProps {
  finding: Finding
  orderText?: string
  /** Application-layer view of the same finding: action, explanation, retrieved passages. */
  view?: FindingView
  children?: React.ReactNode // slot for ReviewPanel
}

const SEVERITY_CONFIG = {
  HIGH: {
    border: 'border-l-rose-500',
    bg: 'bg-rose-500/5',
    icon: <AlertTriangle className="w-4 h-4 text-rose-400" />,
    label: 'HIGH',
  },
  MODERATE: {
    border: 'border-l-amber-500',
    bg: 'bg-amber-500/5',
    icon: <AlertTriangle className="w-4 h-4 text-amber-400" />,
    label: 'MODERATE',
  },
  LOW: {
    border: 'border-l-sky-500',
    bg: 'bg-sky-500/5',
    icon: <Info className="w-4 h-4 text-sky-400" />,
    label: 'LOW',
  },
  INFO: {
    border: 'border-l-indigo-500',
    bg: 'bg-indigo-500/5',
    icon: <Info className="w-4 h-4 text-indigo-400" />,
    label: 'INFO',
  },
}

const ACTION_LABELS: Record<string, string> = {
  switch: 'Switch antibiotic',
  stop: 'Stop antibiotic',
  adjust_dose: 'Adjust dose',
  adjust_duration: 'Adjust duration',
  send_culture: 'Send culture',
  confirm_drug: 'Confirm drug identity',
  provide_input: 'Provide missing information',
}

export const FindingCard: React.FC<FindingCardProps> = ({ finding, orderText, view, children }) => {
  const [evidenceOpen, setEvidenceOpen] = useState(false)
  const config = SEVERITY_CONFIG[finding.severity]

  const isCannotAssess = finding.outcome === 'CANNOT_ASSESS'

  return (
    <div
      className={`rounded-xl border border-[#2d3148] border-l-4 ${config.border} ${config.bg} overflow-hidden animate-fade-in`}
    >
      {/* Header */}
      <div className="px-5 py-4">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 shrink-0">{config.icon}</div>
          <div className="flex-1 min-w-0">
            {/* Rule ID + Outcome badges */}
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <Badge variant={finding.severity} size="sm">
                {config.label}
              </Badge>
              <Badge variant={finding.outcome} size="sm">
                {finding.outcome === 'CANNOT_ASSESS' ? 'Cannot Assess' : finding.outcome}
              </Badge>
              <span className="text-[10px] font-mono text-slate-500 px-1.5 py-0.5 rounded bg-[#141724] border border-[#2d3148]">
                {finding.rule_id}
              </span>
              {orderText && (
                <span className="text-[10px] text-slate-400 px-1.5 py-0.5 rounded bg-[#141724] border border-[#2d3148]">
                  Drug: {orderText}
                </span>
              )}
            </div>

            {/* Main message */}
            <p className="text-sm font-semibold text-slate-100 leading-snug">{finding.message}</p>

            {/* Missing inputs warning */}
            {finding.missing_inputs.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {finding.missing_inputs.map((input) => (
                  <span
                    key={input}
                    className="text-[11px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/30"
                  >
                    Waiting for: {input.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* DDI Details Panel */}
        {view?.ddi && (
          <div className="mt-4 ml-7 px-4 py-3 rounded-lg bg-[#141724] border border-[#2d3148] space-y-2">
            {view.ddi.status === 'INTERACTION_FOUND' && (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[11px] font-semibold text-rose-400 uppercase tracking-wide">
                    DDI detected
                  </span>
                  <span className="text-xs font-mono text-slate-200">
                    {view.ddi.drug_a} + {view.ddi.drug_b}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20">
                    Severity: {view.ddi.severity}
                  </span>
                </div>
                {(view.ddi.mechanism || view.ddi.description) && (
                  <div>
                    <span className="text-[10px] text-slate-400 font-semibold uppercase">Why / Mechanism: </span>
                    <span className="text-xs text-slate-300">{view.ddi.mechanism || view.ddi.description}</span>
                  </div>
                )}
                <div className="text-[11px] text-slate-400">
                  <span className="font-semibold uppercase text-[10px]">Source: </span>
                  {view.ddi.source}{view.ddi.source_version ? ` (${view.ddi.source_version})` : ''}
                </div>
                <div className="text-xs text-indigo-300 font-medium">
                  Action: Review by pharmacist/clinician
                </div>
              </>
            )}

            {view.ddi.status === 'CANNOT_ASSESS' && (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[11px] font-semibold text-amber-400 uppercase tracking-wide">
                    DDI could not be assessed
                  </span>
                  {view.ddi.drug_a && (
                    <span className="text-xs font-mono text-slate-200">
                      {view.ddi.drug_b ? `${view.ddi.drug_a} + ${view.ddi.drug_b}` : view.ddi.drug_a}
                    </span>
                  )}
                </div>
                {view.ddi.reason && (
                  <div>
                    <span className="text-[10px] text-slate-400 font-semibold uppercase">Reason: </span>
                    <span className="text-xs text-slate-300">{view.ddi.reason}</span>
                  </div>
                )}
                <div className="text-xs text-amber-300 font-medium">
                  Manual clinical review required
                </div>
              </>
            )}

            {view.ddi.status === 'NO_INTERACTION_REPORTED_BY_SOURCE' && (
              <div className="text-xs text-slate-400">
                <span className="text-emerald-400 font-medium">No interaction reported</span> by {view.ddi.source} for{' '}
                <span className="font-mono text-slate-300">{view.ddi.drug_a} + {view.ddi.drug_b}</span> (not guaranteed safe).
              </div>
            )}
          </div>
        )}

        {/* What to do (for non-DDI findings) */}
        {view?.action && !view?.ddi && (
          <div className="mt-4 ml-7 px-4 py-3 rounded-lg bg-indigo-500/10 border border-indigo-500/30">
            <span className="text-[11px] font-semibold text-indigo-300 uppercase tracking-wide">
              Action
            </span>
            <p className="text-sm text-slate-100 mt-1 leading-relaxed">{view.action}</p>
          </div>
        )}

        {/* Why */}
        {view?.explanation && !view?.ddi && (
          <p className="mt-3 ml-7 text-xs text-slate-400 leading-relaxed">{view.explanation}</p>
        )}

        {/* Suggestion box */}
        {finding.suggestion && !isCannotAssess && !view?.action && (
          <div className="mt-4 ml-7 px-4 py-3 rounded-lg bg-[#141724] border border-[#2d3148]">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-[11px] font-semibold text-indigo-400 uppercase tracking-wide">
                Suggested Action
              </span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                {ACTION_LABELS[finding.suggestion.action] ?? finding.suggestion.action}
              </span>
              {finding.suggestion.drug && (
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                  → {finding.suggestion.drug}
                </span>
              )}
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">{finding.suggestion.detail}</p>

            <p className="mt-2 text-[10px] text-slate-500 italic">
              This is a recommendation only. A pharmacist must review and approve any changes.
            </p>
          </div>
        )}

        {/* Evidence toggle */}
        {(finding.evidence.length > 0 || (view?.guideline_passages.length ?? 0) > 0) && (
          <div className="mt-3 ml-7">
            <button
              onClick={() => setEvidenceOpen(!evidenceOpen)}
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
            >
              <BookOpen className="w-3.5 h-3.5" />
              <span>Guideline source ({finding.evidence.length + (view?.guideline_passages.length ?? 0)})</span>
              {evidenceOpen ? (
                <ChevronUp className="w-3.5 h-3.5" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5" />
              )}
            </button>

            {evidenceOpen && (
              <div className="mt-2 space-y-2">
                {finding.evidence.map((ev, i) => (
                  <div
                    key={i}
                    className="px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2d3148] text-xs"
                  >
                    <p className="text-slate-200 font-medium">{ev.title}</p>
                    {ev.page && (
                      <p className="text-slate-400 mt-0.5">Page {ev.page}</p>
                    )}
                    {ev.quote && (
                      <p className="mt-1.5 text-slate-400 italic border-l-2 border-indigo-500/40 pl-2">
                        &ldquo;{ev.quote}&rdquo;
                      </p>
                    )}
                    <p className="mt-1 text-[10px] text-slate-500 font-mono">{ev.source_id}</p>
                  </div>
                ))}
                {view?.guideline_passages.map((p, i) => (
                  <div
                    key={`p${i}`}
                    className="px-3 py-2 rounded-lg bg-[#0f1117] border border-[#2d3148] text-xs"
                  >
                    <p className="text-slate-400">Related guideline text</p>
                    <p className="text-slate-300 mt-1">{p.text}</p>
                    <p className="mt-1 text-[10px] text-slate-500">
                      {p.document}, section {p.section}
                      {p.page ? `, ${p.page}` : ''}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Review panel slot */}
      {children && (
        <div className="border-t border-[#2d3148] bg-[#0f1117]/40 px-5 py-4">
          {children}
        </div>
      )}
    </div>
  )
}
