'use client'

import React from 'react'
import Link from 'next/link'
import { Clock, AlertTriangle, CheckCircle2 } from 'lucide-react'
import type { TimeoutItem } from '@/types/stewardship'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'

interface TimeoutCardProps {
  item: TimeoutItem
}

const SETTING_LABELS: Record<string, string> = {
  OPD: 'Outpatient',
  WARD: 'Ward',
  ICU: 'ICU',
}

export const TimeoutCard: React.FC<TimeoutCardProps> = ({ item }) => {
  const isReviewDue = item.status === 'REVIEW_DUE'
  const started = new Date(item.started_at)
  const formattedStart = started.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })

  const hoursDisplay =
    item.hours_elapsed < 72
      ? `${item.hours_elapsed}h elapsed`
      : `${Math.floor(item.hours_elapsed / 24)}d ${item.hours_elapsed % 24}h elapsed`

  return (
    <div
      className={`rounded-xl border overflow-hidden transition-all ${
        isReviewDue
          ? 'border-amber-500/30 bg-amber-500/5'
          : 'border-[#2d3148] bg-[#1e2235]'
      }`}
    >
      <div className="px-5 py-4">
        <div className="flex items-start gap-4">
          {/* Icon */}
          <div className="shrink-0 mt-0.5">
            {isReviewDue ? (
              <Clock className="w-5 h-5 text-amber-400" />
            ) : (
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
            )}
          </div>

          <div className="flex-1 min-w-0">
            {/* Patient + setting */}
            <div className="flex flex-wrap items-center gap-2 mb-1">
              <span className="text-sm font-semibold text-slate-100 font-mono">
                {item.patient_id}
              </span>
              <Badge variant={isReviewDue ? 'CANNOT_ASSESS' : 'OK'} size="sm">
                {isReviewDue ? 'REVIEW DUE' : 'REVIEWED'}
              </Badge>
              <span className="text-xs text-slate-400">{SETTING_LABELS[item.setting] ?? item.setting}</span>
            </div>

            {/* Antibiotic */}
            <p className="text-xs text-slate-300 mb-2">
              <span className="text-slate-500">Antibiotics: </span>
              {item.antibiotic_name}
            </p>

            {/* Time info */}
            <div className="flex flex-wrap gap-3 text-xs text-slate-400">
              <span>
                Started: <span className="text-slate-300">{formattedStart}</span>
              </span>
              <span
                className={`font-semibold ${
                  item.hours_elapsed > 72 ? 'text-rose-400' : 'text-amber-400'
                }`}
              >
                {hoursDisplay}
              </span>
            </div>

            {/* Overdue warning */}
            {item.hours_elapsed > 72 && isReviewDue && (
              <div className="mt-2 flex items-center gap-1.5 text-xs text-rose-300">
                <AlertTriangle className="w-3.5 h-3.5" />
                <span>Review is overdue — {Math.floor((item.hours_elapsed - 48) / 24)}d beyond 48-hour window</span>
              </div>
            )}
          </div>

          {/* Action */}
          <div className="shrink-0">
            {isReviewDue ? (
              <Link href={`/evaluation/${item.episode_id}`}>
                <Button variant="warning" size="sm">
                  Review now
                </Button>
              </Link>
            ) : (
              <Link href={`/evaluation/${item.episode_id}`}>
                <Button variant="ghost" size="sm">
                  View
                </Button>
              </Link>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
