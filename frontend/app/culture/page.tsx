'use client'

import React, { useEffect, useState } from 'react'
import { Loader2, FlaskConical } from 'lucide-react'
import { getEpisode } from '@/lib/api'
import { MOCK_EPISODE } from '@/lib/mock-data'
import type { Episode } from '@/types/stewardship'
import { CulturePanel } from '@/components/stewardship/CulturePanel'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'

// In a real app this would fetch all episodes with culture results.
// For demo, we show the mock episode's culture data.
const DEMO_EPISODES = [MOCK_EPISODE]

export default function CulturePage() {
  const [episodes] = useState<Episode[]>(DEMO_EPISODES)
  const [loading] = useState(false)

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Culture & Resistance</h1>
        <p className="text-sm text-slate-400 mt-0.5">
          Microbiological specimen results and susceptibility data for active episodes
        </p>
      </div>

      {loading && (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-indigo-400" />
        </div>
      )}

      {!loading && episodes.length === 0 && (
        <div className="text-center py-16 text-slate-400">
          <FlaskConical className="w-10 h-10 mx-auto mb-3 text-slate-600" />
          <p>No culture results available.</p>
        </div>
      )}

      {episodes.map((episode) => {
        const currentAntibiotics = episode.orders
          .filter((o) => o.generic)
          .map((o) => o.generic as string)

        const finalSpecimens = episode.specimens.filter(
          (s) => s.status === 'FINAL' && s.isolates.length > 0
        )
        const pendingSpecimens = episode.specimens.filter((s) => s.status === 'PENDING')

        if (episode.specimens.length === 0) return null

        return (
          <Card
            key={episode.id}
            title={`Patient ${episode.patient.id}`}
            subtitle={`Episode ${episode.id} · ${episode.setting} · ${episode.diagnosis_text ?? 'No diagnosis'}`}
            action={
              <div className="flex items-center gap-2">
                {finalSpecimens.length > 0 && (
                  <Badge variant="ACCEPTED" size="sm">
                    {finalSpecimens.length} Final
                  </Badge>
                )}
                {pendingSpecimens.length > 0 && (
                  <Badge variant="AMBIGUOUS" size="sm">
                    {pendingSpecimens.length} Pending
                  </Badge>
                )}
              </div>
            }
          >
            <div className="space-y-6">
              {/* Current antibiotics */}
              <div>
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
                  Current antibiotics
                </p>
                <div className="flex flex-wrap gap-2">
                  {currentAntibiotics.map((ab) => (
                    <span
                      key={ab}
                      className="text-xs px-2.5 py-1 rounded-full bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 capitalize"
                    >
                      {ab}
                    </span>
                  ))}
                </div>
              </div>

              {/* Specimens */}
              {episode.specimens.map((specimen) => (
                <CulturePanel
                  key={specimen.id}
                  specimen={specimen}
                  currentAntibiotics={currentAntibiotics}
                />
              ))}
            </div>
          </Card>
        )
      })}
    </div>
  )
}
