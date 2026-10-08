'use client'

import React, { useState } from 'react'
import { AlertTriangle, BookOpen, ChevronDown, ChevronUp, Info } from 'lucide-react'
import type { Finding, FindingView } from '@/types/stewardship'
import { Badge } from '@/components/ui/Badge'

interface FindingCardProps {
  finding: Finding
  orderText?: string
  view?: FindingView
  children?: React.ReactNode
}

const SEVERITY = {
  HIGH: { border: 'border-l-[#8B1A1A]', tint: 'bg-[#FDF2F2]', icon: 'text-[#8B1A1A]' },
  MODERATE: { border: 'border-l-[#8B5E00]', tint: 'bg-[#FFF9EB]', icon: 'text-[#8B5E00]' },
  LOW: { border: 'border-l-[#3730A3]', tint: 'bg-[#F5F4FF]', icon: 'text-[#3730A3]' },
  INFO: { border: 'border-l-[#6B6A65]', tint: 'bg-[#FAFAF8]', icon: 'text-[#6B6A65]' },
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
  const config = SEVERITY[finding.severity]
  const Icon = finding.severity === 'HIGH' || finding.severity === 'MODERATE' ? AlertTriangle : Info
  const sources = finding.evidence.length + (view?.guideline_passages.length ?? 0)

  return (
    <article className={`overflow-hidden rounded-[8px] border border-[#E2E1DC] border-l-4 bg-white ${config.border}`}>
      <div className="p-4 sm:p-5">
        <div className="flex items-start gap-3">
          <div className={`rounded-md p-1.5 ${config.tint}`}><Icon className={`h-4 w-4 ${config.icon}`} /></div>
          <div className="min-w-0 flex-1">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge variant={finding.severity} size="sm">{finding.severity}</Badge>
              <Badge variant={finding.outcome} size="sm">{finding.outcome === 'CANNOT_ASSESS' ? 'Cannot assess' : finding.outcome}</Badge>
              <span className="rounded border border-[#E2E1DC] bg-[#F4F3EF] px-1.5 py-0.5 font-mono text-[10px] text-[#6B6A65]">{finding.rule_id}</span>
              {orderText && <span className="rounded border border-[#E2E1DC] bg-[#FAFAF8] px-1.5 py-0.5 text-[10px] text-[#6B6A65]">{orderText}</span>}
            </div>
            <p className="text-sm font-medium leading-relaxed text-[#1A1A1A]">{finding.message}</p>

            {finding.missing_inputs.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {finding.missing_inputs.map((input) => (
                  <span key={input} className="rounded border border-[#E8D5A7] bg-[#FFF9EB] px-2 py-0.5 text-[11px] text-[#8B5E00]">
                    Needed: {input.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {view?.ddi && (
          <div className="ml-0 mt-4 space-y-1.5 rounded-md border border-[#E2E1DC] bg-[#FAFAF8] px-4 py-3 text-xs sm:ml-10">
            {view.ddi.status === 'INTERACTION_FOUND' && (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[10px] font-medium uppercase tracking-[0.06em] text-[#8B1A1A]">Interaction reported</span>
                  <span className="font-mono text-[#1A1A1A]">{view.ddi.drug_a} + {view.ddi.drug_b}</span>
                  <span className="rounded border border-[#E8D5A7] bg-[#FFF9EB] px-1.5 py-0.5 text-[10px] text-[#8B5E00]">Severity: {view.ddi.severity}</span>
                </div>
                {(view.ddi.mechanism || view.ddi.description) && (
                  <p className="leading-relaxed text-[#1A1A1A]">{view.ddi.mechanism || view.ddi.description}</p>
                )}
              </>
            )}
            {view.ddi.status === 'CANNOT_ASSESS' && (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[10px] font-medium uppercase tracking-[0.06em] text-[#8B5E00]">Interaction could not be assessed</span>
                  {view.ddi.drug_a && (
                    <span className="font-mono text-[#1A1A1A]">{view.ddi.drug_b ? `${view.ddi.drug_a} + ${view.ddi.drug_b}` : view.ddi.drug_a}</span>
                  )}
                </div>
                {view.ddi.reason && <p className="leading-relaxed text-[#1A1A1A]">{view.ddi.reason}</p>}
              </>
            )}
            {view.ddi.status === 'NO_INTERACTION_REPORTED_BY_SOURCE' && (
              <p className="text-[#6B6A65]">
                No interaction reported by {view.ddi.source} for{' '}
                <span className="font-mono text-[#1A1A1A]">{view.ddi.drug_a} + {view.ddi.drug_b}</span> (not a guarantee of safety).
              </p>
            )}
            <p className="font-mono text-[10px] text-[#8B8982]">
              {view.ddi.source}{view.ddi.source_version ? ` ${view.ddi.source_version}` : ''}
            </p>
          </div>
        )}

        {(view?.action || finding.suggestion) && (
          <div className="ml-0 mt-4 rounded-md border border-[#D8D5F0] bg-[#F7F6FF] px-4 py-3 sm:ml-10">
            <p className="text-[10px] font-medium uppercase tracking-[0.06em] text-[#3730A3]">
              {view?.suggestion_action ? ACTION_LABELS[view.suggestion_action] ?? 'Recommended action' : 'Recommended action'}
            </p>
            <p className="mt-1 text-sm leading-relaxed text-[#1A1A1A]">{view?.action ?? finding.suggestion?.detail}</p>
          </div>
        )}

        {view?.explanation && !view.ddi && <p className="ml-0 mt-3 text-xs leading-relaxed text-[#6B6A65] sm:ml-10">{view.explanation}</p>}

        {sources > 0 && (
          <div className="ml-0 mt-3 sm:ml-10">
            <button onClick={() => setEvidenceOpen(!evidenceOpen)} className="flex items-center gap-1.5 text-xs font-medium text-[#6B6A65] hover:text-[#1A1A1A]">
              <BookOpen className="h-3.5 w-3.5" /> Guideline evidence ({sources})
              {evidenceOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            </button>
            {evidenceOpen && (
              <div className="mt-2 space-y-2">
                {finding.evidence.map((evidence, index) => (
                  <div key={`${evidence.source_id}-${index}`} className="rounded-md border border-[#E2E1DC] bg-[#FAFAF8] p-3 text-xs">
                    <p className="font-medium text-[#1A1A1A]">{evidence.title}</p>
                    {evidence.page && <p className="mt-0.5 text-[#6B6A65]">Page {evidence.page}</p>}
                    {evidence.quote && <blockquote className="mt-2 border-l-2 border-[#C8C7C0] pl-2 italic text-[#6B6A65]">“{evidence.quote}”</blockquote>}
                    <p className="mt-1 font-mono text-[10px] text-[#8B8982]">{evidence.source_id}</p>
                  </div>
                ))}
                {view?.guideline_passages.map((passage, index) => (
                  <div key={`${passage.document}-${index}`} className="rounded-md border border-[#E2E1DC] bg-[#FAFAF8] p-3 text-xs text-[#6B6A65]">
                    <p>{passage.text}</p>
                    <p className="mt-1 font-mono text-[10px]">{passage.document} · {passage.section}{passage.page ? ` · ${passage.page}` : ''}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      {children && <div className="border-t border-[#E2E1DC] bg-[#FAFAF8] px-4 py-4 sm:px-5">{children}</div>}
    </article>
  )
}
