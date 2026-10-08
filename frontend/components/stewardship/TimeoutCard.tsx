'use client'

import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import { AlertTriangle, CheckCircle2, Clock } from 'lucide-react'
import type { TimeoutItem } from '@/types/stewardship'
import { evaluateEpisode } from '@/lib/api'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'

export const TimeoutCard: React.FC<{ item: TimeoutItem }> = ({ item }) => {
  const router = useRouter()
  const [opening, setOpening] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const due = item.status === 'REVIEW_DUE'
  const overdue = item.hours_elapsed > 72

  const openReview = async () => {
    setOpening(true)
    setError(null)
    try {
      const evaluation = await evaluateEpisode(item.episode_id, 'TIMEOUT_DUE')
      router.push(`/evaluation/${evaluation.id}`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not start the review.')
      setOpening(false)
    }
  }

  return (
    <article className={`rounded-[8px] border bg-white p-4 ${overdue && due ? 'border-[#D9A4A4]' : 'border-[#E2E1DC]'}`}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        <div className={`rounded-md p-2 ${due ? 'bg-[#FFF9EB] text-[#8B5E00]' : 'bg-[#F0FBF4] text-[#1A6B3C]'}`}>{due ? <Clock className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}</div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-sm font-medium text-[#1A1A1A]">{item.patient_id}</span><Badge variant={due ? 'CANNOT_ASSESS' : 'OK'}>{due ? 'Review due' : 'Reviewed'}</Badge><span className="text-xs text-[#6B6A65]">{item.setting}</span></div>
          <p className="mt-2 text-xs text-[#1A1A1A]"><span className="text-[#6B6A65]">Antibiotics:</span> {item.antibiotic_name}</p>
          <div className="mt-2 flex flex-wrap gap-3 font-mono text-xs text-[#6B6A65]"><span>Started {new Date(item.started_at).toLocaleString('en-IN')}</span><span className={overdue ? 'text-[#8B1A1A]' : 'text-[#8B5E00]'}>{item.hours_elapsed} hours elapsed</span></div>
          {overdue && due && <p className="mt-2 flex items-center gap-1.5 text-xs text-[#8B1A1A]"><AlertTriangle className="h-3.5 w-3.5" />Outside the recommended 48–72 hour review window.</p>}
          {error && <p className="mt-2 text-xs text-[#8B1A1A]">{error}</p>}
        </div>
        {due ? (
          <Button variant="warning" size="sm" isLoading={opening} onClick={openReview}>Start 48-hour review</Button>
        ) : item.evaluation_id ? (
          <Button variant="outline" size="sm" onClick={() => router.push(`/evaluation/${item.evaluation_id}/plan`)}>View signed plan</Button>
        ) : null}
      </div>
    </article>
  )
}
