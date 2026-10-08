'use client'

import React, { useEffect, useState } from 'react'
import Link from 'next/link'
import { FlaskConical, Loader2, Plus } from 'lucide-react'
import { getEpisode, getEpisodes } from '@/lib/api'
import type { Episode, EvaluationReport } from '@/types/stewardship'
import { AddCultureForm } from '@/components/stewardship/AddCultureForm'
import { CulturePanel } from '@/components/stewardship/CulturePanel'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'

export default function CulturePage() {
  const [episodes, setEpisodes] = useState<Episode[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Episode whose "add culture" form is open, and the re-evaluation each saved culture produced.
  const [adding, setAdding] = useState<string | null>(null)
  const [reevaluated, setReevaluated] = useState<Record<string, EvaluationReport>>({})

  useEffect(() => {
    // Every episode, not only those with a culture: results usually arrive days after the
    // prescription, so a culture is most often added here, to an episode that has none yet.
    getEpisodes()
      .then(setEpisodes)
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Could not load episodes.'))
      .finally(() => setLoading(false))
  }, [])

  const handleAdded = async (episodeId: string, report: EvaluationReport) => {
    setAdding(null)
    setReevaluated((prev) => ({ ...prev, [episodeId]: report }))
    try {
      const updated = await getEpisode(episodeId)
      setEpisodes((prev) => prev.map((episode) => (episode.id === episodeId ? updated : episode)))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Saved, but could not reload the episode.')
    }
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <header className="border-b border-[#E2E1DC] pb-4">
        <p className="text-xs font-medium uppercase tracking-wider text-[#6B6A65]">Microbiology</p>
        <h1 className="mt-1 text-2xl font-medium text-[#1A1A1A]">Culture and resistance</h1>
        <p className="mt-1 text-sm text-[#6B6A65]">
          Add a culture result when the laboratory reports it; the episode is re-evaluated against it. Susceptibility
          results are shown beside each patient’s active antibiotics.
        </p>
      </header>

      {loading && <div className="flex justify-center py-16"><Loader2 className="h-7 w-7 animate-spin text-[#3730A3]" /></div>}
      {error && <div className="rounded-md border border-[#D9A4A4] bg-[#FDF2F2] px-4 py-3 text-sm text-[#8B1A1A]">{error}</div>}
      {!loading && !error && episodes.length === 0 && (
        <div className="rounded-[8px] border border-dashed border-[#C8C7C0] bg-white py-16 text-center">
          <FlaskConical className="mx-auto h-8 w-8 text-[#8B8982]" />
          <p className="mt-3 text-sm font-medium text-[#1A1A1A]">No episodes yet</p>
          <p className="mt-1 text-xs text-[#6B6A65]">
            Start a new evaluation first; its culture results can then be added here.
          </p>
        </div>
      )}

      {episodes.map((episode) => {
        const current = episode.orders.flatMap((order) => order.generic ? [order.generic] : [])
        const finalCount = episode.specimens.filter((specimen) => specimen.status === 'FINAL').length
        const pendingCount = episode.specimens.filter((specimen) => specimen.status === 'PENDING').length
        const report = reevaluated[episode.id]
        return (
          <Card
            key={episode.id}
            title={`Patient ${episode.patient.id}`}
            subtitle={`${episode.id} · ${episode.setting} · ${episode.diagnosis_text ?? 'No diagnosis recorded'}`}
            action={
              <div className="flex items-center gap-2">
                {finalCount > 0 && <Badge variant="ACCEPTED">{finalCount} final</Badge>}
                {pendingCount > 0 && <Badge variant="AMBIGUOUS">{pendingCount} pending</Badge>}
                {adding !== episode.id && (
                  <Button size="sm" variant="outline" leftIcon={<Plus className="h-3.5 w-3.5" />} onClick={() => setAdding(episode.id)}>
                    Add culture result
                  </Button>
                )}
              </div>
            }
          >
            <div className="space-y-6">
              <div><p className="mb-2 text-xs font-medium uppercase tracking-wider text-[#6B6A65]">Current antibiotics</p><div className="flex flex-wrap gap-2">{current.length ? current.map((drug) => <span key={drug} className="rounded border border-[#D8D5F0] bg-[#F7F6FF] px-2 py-1 text-xs capitalize text-[#3730A3]">{drug}</span>) : <span className="text-xs text-[#6B6A65]">None identified</span>}</div></div>
              {adding === episode.id && (
                <AddCultureForm
                  episodeId={episode.id}
                  onAdded={(r) => handleAdded(episode.id, r)}
                  onCancel={() => setAdding(null)}
                />
              )}
              {report && (
                <div className="rounded-md border border-[#B7D9C4] bg-[#F1F8F4] px-4 py-3 text-sm text-[#1A6B3C]">
                  Culture saved and the episode re-evaluated
                  {report.culture ? `: ${report.culture.message}` : '.'}{' '}
                  <Link href={`/evaluation/${report.id}`} className="font-medium underline">
                    Open the evaluation
                  </Link>
                </div>
              )}
              {episode.specimens.length === 0 && adding !== episode.id && (
                <p className="text-xs text-[#6B6A65]">No culture recorded for this episode.</p>
              )}
              {episode.specimens.map((specimen) => <CulturePanel key={specimen.id} specimen={specimen} currentAntibiotics={current} />)}
            </div>
          </Card>
        )
      })}
    </div>
  )
}
