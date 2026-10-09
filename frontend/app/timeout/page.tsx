'use client'

import React, { useEffect, useState } from 'react'
import { Clock, Loader2 } from 'lucide-react'
import { getTimeoutConfig, getTimeoutDue } from '@/lib/api'
import type { TimeoutConfig, TimeoutItem } from '@/types/stewardship'
import { TimeoutCard } from '@/components/stewardship/TimeoutCard'

export default function TimeoutPage() {
  const [items, setItems] = useState<TimeoutItem[]>([])
  const [timeoutConfig, setTimeoutConfig] = useState<TimeoutConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        const [nextItems, nextConfig] = await Promise.all([getTimeoutDue(), getTimeoutConfig()])
        if (!active) return
        setItems(nextItems)
        setTimeoutConfig(nextConfig)
        setError(null)
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : 'Could not load the review queue.')
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    const refresh = window.setInterval(load, 5_000)
    return () => {
      active = false
      window.clearInterval(refresh)
    }
  }, [])

  const overdue = items.filter((item) => item.hours_elapsed > 72 && item.status === 'REVIEW_DUE')
  const due = items.filter((item) => item.hours_elapsed <= 72 && item.status === 'REVIEW_DUE')
  const reviewed = items.filter((item) => item.status === 'REVIEWED')

  return (
    <div className="space-y-6 animate-fade-in">
      <header className="border-b border-[#E2E1DC] pb-4">
        <p className="text-xs font-medium uppercase tracking-wider text-[#6B6A65]">Scheduled reassessment</p>
        <h1 className="mt-1 text-2xl font-medium text-[#1A1A1A]">Antimicrobial re-reviews</h1>
        <p className="mt-1 text-sm text-[#6B6A65]">Reassess empiric therapy when culture and clinical response data should be available.</p>
      </header>

      <div className="flex items-start gap-3 rounded-[8px] border border-[#E8D5A7] bg-[#FFF9EB] p-4">
        <Clock className="mt-0.5 h-4 w-4 shrink-0 text-[#8B5E00]" />
        <div>
          <p className="text-sm font-medium text-[#8B5E00]">{timeoutConfig?.demo_mode ? 'Time-compressed demo queue' : 'Why this queue exists'}</p>
          <p className="mt-1 text-xs leading-relaxed text-[#6B6A65]">
            {timeoutConfig?.demo_mode
              ? `For this demo, re-review becomes available ${timeoutConfig.review_due_after_minutes} minute${timeoutConfig.review_due_after_minutes === 1 ? '' : 's'} after the first antibiotic dose. Clinical guidance remains 48–72 hours; RxGuard reruns the same rules without changing therapy automatically.`
              : 'NCDC guidance recommends reviewing empiric antibiotics after 48–72 hours. RxGuard reruns the rules; a clinician still decides whether therapy changes.'}
          </p>
        </div>
      </div>

      {loading && <div className="flex justify-center py-16"><Loader2 className="h-7 w-7 animate-spin text-[#3730A3]" /></div>}
      {error && <div className="rounded-md border border-[#D9A4A4] bg-[#FDF2F2] px-4 py-3 text-sm text-[#8B1A1A]">{error}</div>}
      {!loading && !error && (
        <div className="space-y-6">
          {overdue.length > 0 && <Queue title="Overdue" count={overdue.length} color="text-[#8B1A1A]" items={overdue} />}
          {due.length > 0 && <Queue title="Due now" count={due.length} color="text-[#8B5E00]" items={due} />}
          {overdue.length === 0 && due.length === 0 && <div className="rounded-[8px] border border-dashed border-[#C8C7C0] bg-white py-16 text-center"><Clock className="mx-auto h-8 w-8 text-[#1A6B3C]" /><p className="mt-3 text-sm font-medium text-[#1A1A1A]">No reviews pending</p><p className="mt-1 text-xs text-[#6B6A65]">The queue refreshes automatically; active prescriptions appear when the configured interval is reached.</p></div>}
          {reviewed.length > 0 && <Queue title="Completed" count={reviewed.length} color="text-[#6B6A65]" items={reviewed} />}
        </div>
      )}
    </div>
  )
}

function Queue({ title, count, color, items }: { title: string; count: number; color: string; items: TimeoutItem[] }) {
  return <section className="space-y-3"><div className="flex items-center gap-3"><h2 className={`text-xs font-medium uppercase tracking-wider ${color}`}>{title} ({count})</h2><div className="h-px flex-1 bg-[#E2E1DC]" /></div>{items.map((item) => <TimeoutCard key={item.episode_id} item={item} />)}</section>
}
