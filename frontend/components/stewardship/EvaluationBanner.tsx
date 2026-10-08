'use client'

import React from 'react'
import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'
import type { EvaluationStatus, Finding } from '@/types/stewardship'

interface EvaluationBannerProps {
  status: EvaluationStatus
  findings: Finding[]
  evaluatedAt: string
  rulesetVersion: string
  trigger: string
}

const STATUS_CONFIG = {
  FLAGGED: {
    box: 'border-[#D9A4A4] bg-[#FDF2F2]',
    icon: AlertTriangle,
    color: 'text-[#8B1A1A]',
    label: 'Review required',
    description: 'The rules identified findings that need a clinical decision.',
  },
  OK: {
    box: 'border-[#A9CFB7] bg-[#F0FBF4]',
    icon: CheckCircle2,
    color: 'text-[#1A6B3C]',
    label: 'Checks passed',
    description: 'No stewardship concerns were identified.',
  },
  INCOMPLETE: {
    box: 'border-[#E8D5A7] bg-[#FFF9EB]',
    icon: XCircle,
    color: 'text-[#8B5E00]',
    label: 'Information required',
    description: 'Some checks could not run because clinical information is missing.',
  },
}

const TRIGGERS: Record<string, string> = {
  NEW_PRESCRIPTION: 'New prescription',
  CULTURE_RESULT: 'Culture result',
  LAB_UPDATE: 'Lab update',
  TIMEOUT_DUE: '48-hour review',
  MANUAL: 'Manual review',
}

export const EvaluationBanner: React.FC<EvaluationBannerProps> = ({
  status,
  findings,
  evaluatedAt,
  rulesetVersion,
  trigger,
}) => {
  const config = STATUS_CONFIG[status]
  const Icon = config.icon
  const flags = findings.filter((finding) => finding.outcome === 'FLAG').length
  const incomplete = findings.filter((finding) => finding.outcome === 'CANNOT_ASSESS').length

  return (
    <section className={`rounded-[8px] border p-4 sm:p-5 ${config.box}`}>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${config.color}`} />
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className={`text-base font-medium ${config.color}`}>{config.label}</h2>
              {flags > 0 && <span className="rounded border border-[#D9A4A4] bg-white/70 px-2 py-0.5 text-xs font-medium text-[#8B1A1A]">{flags} flagged</span>}
              {incomplete > 0 && <span className="rounded border border-[#E8D5A7] bg-white/70 px-2 py-0.5 text-xs font-medium text-[#8B5E00]">{incomplete} incomplete</span>}
            </div>
            <p className="mt-1 text-sm text-[#6B6A65]">{config.description}</p>
            <p className="mt-2 font-mono text-xs text-[#6B6A65]">
              {new Date(evaluatedAt).toLocaleString('en-IN')} · {TRIGGERS[trigger] ?? trigger} · ruleset {rulesetVersion}
            </p>
          </div>
        </div>
        <div className="flex max-w-sm items-start gap-2 rounded-md border border-[#E2E1DC] bg-white/70 px-3 py-2">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#3730A3]" />
          <p className="text-xs leading-relaxed text-[#6B6A65]">
            RxGuard recommends; it never changes a prescription automatically. A clinician must apply every approved change.
          </p>
        </div>
      </div>
    </section>
  )
}
