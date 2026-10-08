'use client'

import React, { useEffect, useState } from 'react'
import { FlaskConical, Loader2 } from 'lucide-react'
import { getEpisodes } from '@/lib/api'
import type { Episode } from '@/types/stewardship'
import { CulturePanel } from '@/components/stewardship/CulturePanel'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'

export default function CulturePage() {
  const [episodes, setEpisodes] = useState<Episode[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getEpisodes(true)
      .then(setEpisodes)
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Could not load culture results.'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-6 animate-fade-in">
      <header className="border-b border-[#E2E1DC] pb-4">
        <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-[#6B6A65]">Microbiology</p>
        <h1 className="mt-1 text-2xl font-medium text-[#1A1A1A]">Culture and resistance</h1>
        <p className="mt-1 text-sm text-[#6B6A65]">Susceptibility results are shown beside each patient’s active antibiotics.</p>
      </header>

      {loading && <div className="flex justify-center py-16"><Loader2 className="h-7 w-7 animate-spin text-[#3730A3]" /></div>}
      {error && <div className="rounded-md border border-[#D9A4A4] bg-[#FDF2F2] px-4 py-3 text-sm text-[#8B1A1A]">{error}</div>}
      {!loading && !error && episodes.length === 0 && (
        <div className="rounded-[8px] border border-dashed border-[#C8C7C0] bg-white py-16 text-center">
          <FlaskConical className="mx-auto h-8 w-8 text-[#8B8982]" />
          <p className="mt-3 text-sm font-medium text-[#1A1A1A]">No culture results available</p>
          <p className="mt-1 text-xs text-[#6B6A65]">Culture data added during clinical context will appear here.</p>
        </div>
      )}

      {episodes.map((episode) => {
        const current = episode.orders.flatMap((order) => order.generic ? [order.generic] : [])
        const finalCount = episode.specimens.filter((specimen) => specimen.status === 'FINAL').length
        const pendingCount = episode.specimens.filter((specimen) => specimen.status === 'PENDING').length
        return (
          <Card key={episode.id} title={`Patient ${episode.patient.id}`} subtitle={`${episode.id} · ${episode.setting} · ${episode.diagnosis_text ?? 'No diagnosis recorded'}`} action={<div className="flex gap-2">{finalCount > 0 && <Badge variant="ACCEPTED">{finalCount} final</Badge>}{pendingCount > 0 && <Badge variant="AMBIGUOUS">{pendingCount} pending</Badge>}</div>}>
            <div className="space-y-6">
              <div><p className="mb-2 text-[10px] font-medium uppercase tracking-[0.06em] text-[#6B6A65]">Current antibiotics</p><div className="flex flex-wrap gap-2">{current.length ? current.map((drug) => <span key={drug} className="rounded border border-[#D8D5F0] bg-[#F7F6FF] px-2 py-1 text-xs capitalize text-[#3730A3]">{drug}</span>) : <span className="text-xs text-[#6B6A65]">None identified</span>}</div></div>
              {episode.specimens.map((specimen) => <CulturePanel key={specimen.id} specimen={specimen} currentAntibiotics={current} />)}
            </div>
          </Card>
        )
      })}
    </div>
  )
}
