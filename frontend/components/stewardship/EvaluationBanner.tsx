'use client'

import React from 'react'
import { CheckCircle2, AlertTriangle, XCircle, Info } from 'lucide-react'
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
    bg: 'bg-rose-500/10',
    border: 'border-rose-500/30',
    icon: <AlertTriangle className="w-6 h-6 text-rose-400" />,
    titleColor: 'text-rose-400',
    label: 'FLAGGED',
    description: 'Clinical review required. Findings identified.',
  },
  OK: {
    bg: 'bg-emerald-500/10',
    border: 'border-emerald-500/30',
    icon: <CheckCircle2 className="w-6 h-6 text-emerald-400" />,
    titleColor: 'text-emerald-400',
    label: 'PASS',
    description: 'No issues identified. All checks passed.',
  },
  INCOMPLETE: {
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/30',
    icon: <XCircle className="w-6 h-6 text-amber-400" />,
    titleColor: 'text-amber-400',
    label: 'INCOMPLETE',
    description: 'Some checks could not run. Missing information required.',
  },
}

const TRIGGER_LABELS: Record<string, string> = {
  NEW_PRESCRIPTION: 'New Prescription',
  CULTURE_RESULT: 'Culture Result',
  LAB_UPDATE: 'Lab Update',
  TIMEOUT_DUE: '48-Hour Review',
  MANUAL: 'Manual',
}

export const EvaluationBanner: React.FC<EvaluationBannerProps> = ({
  status,
  findings,
  evaluatedAt,
  rulesetVersion,
  trigger,
}) => {
  const config = STATUS_CONFIG[status]
  const highCount = findings.filter((f) => f.severity === 'HIGH' && f.outcome === 'FLAG').length
  const moderateCount = findings.filter((f) => f.severity === 'MODERATE' && f.outcome === 'FLAG').length
  const cannotAssessCount = findings.filter((f) => f.outcome === 'CANNOT_ASSESS').length

  const date = new Date(evaluatedAt)
  const formattedDate = date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <div className={`rounded-xl border ${config.bg} ${config.border} p-5 animate-fade-in`}>
      <div className="flex items-start gap-4">
        <div className="shrink-0 mt-0.5">{config.icon}</div>

        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-3 mb-1">
            <h2 className={`text-xl font-bold tracking-wide ${config.titleColor}`}>
              {config.label}
            </h2>
            <span className="text-sm text-slate-400">{config.description}</span>
          </div>

          {/* Finding counts */}
          {status === 'FLAGGED' && (
            <div className="flex flex-wrap gap-2 mt-2">
              {highCount > 0 && (
                <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-rose-500/15 text-rose-400 border border-rose-500/30">
                  {highCount} HIGH
                </span>
              )}
              {moderateCount > 0 && (
                <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30">
                  {moderateCount} MODERATE
                </span>
              )}
              {cannotAssessCount > 0 && (
                <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-700 text-slate-300 border border-slate-600">
                  {cannotAssessCount} CANNOT ASSESS
                </span>
              )}
            </div>
          )}

          {/* Meta info */}
          <div className="flex flex-wrap gap-4 mt-3 text-xs text-slate-400">
            <span>
              Evaluated: <span className="text-slate-300">{formattedDate}</span>
            </span>
            <span>
              Trigger: <span className="text-slate-300">{TRIGGER_LABELS[trigger] ?? trigger}</span>
            </span>
            <span>
              Ruleset: <span className="text-slate-300 font-mono">v{rulesetVersion}</span>
            </span>
          </div>
        </div>

        {/* Safety notice */}
        <div className="hidden lg:flex items-start gap-1.5 px-3 py-2 rounded-lg bg-[#141724] border border-[#2d3148] shrink-0 max-w-xs">
          <Info className="w-3.5 h-3.5 text-indigo-400 mt-0.5 shrink-0" />
          <p className="text-[11px] text-slate-400 leading-relaxed">
            This system <strong className="text-slate-300">recommends</strong> — it does not automatically modify prescriptions.
            All changes require pharmacist approval.
          </p>
        </div>
      </div>
    </div>
  )
}
