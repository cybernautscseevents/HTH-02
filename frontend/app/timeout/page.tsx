'use client'

import React, { useEffect, useState } from 'react'
import { Loader2, Clock } from 'lucide-react'
import { getTimeoutDue } from '@/lib/api'
import type { TimeoutItem } from '@/types/stewardship'
import { TimeoutCard } from '@/components/stewardship/TimeoutCard'

export default function TimeoutPage() {
  const [items, setItems] = useState<TimeoutItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getTimeoutDue()
      .then(setItems)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const overdue = items.filter((i) => i.hours_elapsed > 72 && i.status === 'REVIEW_DUE')
  const due = items.filter((i) => i.hours_elapsed <= 72 && i.status === 'REVIEW_DUE')
  const reviewed = items.filter((i) => i.status === 'REVIEWED')

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-100">48-Hour Antimicrobial Review</h1>
        <p className="text-sm text-slate-400 mt-0.5">
          Prescriptions requiring review per antibiotic stewardship time-out guidelines
        </p>
      </div>

      {/* Context box */}
      <div className="p-4 rounded-xl border border-amber-500/20 bg-amber-500/5">
        <div className="flex items-start gap-3">
          <Clock className="w-5 h-5 text-amber-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-amber-300">Why 48-hour reviews?</p>
            <p className="text-xs text-slate-400 mt-1 leading-relaxed">
              ICMR/NCDC guidelines recommend reassessing empiric antibiotic therapy 48–72 hours
              after initiation, once culture results are typically available. This helps identify
              opportunities for de-escalation, confirms appropriateness, and reduces resistance risk.
            </p>
          </div>
        </div>
      </div>

      {loading && (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-indigo-400" />
        </div>
      )}

      {!loading && (
        <div className="space-y-6">
          {/* Overdue */}
          {overdue.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-rose-400 uppercase tracking-wide">
                  Overdue ({overdue.length})
                </h2>
                <div className="h-px flex-1 bg-rose-500/20" />
              </div>
              {overdue.map((item) => (
                <TimeoutCard key={item.episode_id} item={item} />
              ))}
            </div>
          )}

          {/* Due */}
          {due.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-amber-400 uppercase tracking-wide">
                  Review Due ({due.length})
                </h2>
                <div className="h-px flex-1 bg-amber-500/20" />
              </div>
              {due.map((item) => (
                <TimeoutCard key={item.episode_id} item={item} />
              ))}
            </div>
          )}

          {/* Empty state */}
          {overdue.length === 0 && due.length === 0 && (
            <div className="text-center py-16">
              <Clock className="w-10 h-10 mx-auto mb-3 text-emerald-500/50" />
              <p className="text-slate-300 font-medium">No reviews pending</p>
              <p className="text-sm text-slate-400 mt-1">
                All prescriptions are within the review window.
              </p>
            </div>
          )}

          {/* Reviewed */}
          {reviewed.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
                  Completed ({reviewed.length})
                </h2>
                <div className="h-px flex-1 bg-[#2d3148]" />
              </div>
              {reviewed.map((item) => (
                <TimeoutCard key={item.episode_id} item={item} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
