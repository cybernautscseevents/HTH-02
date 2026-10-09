'use client'

import React, { useEffect, useState } from 'react'
import { Globe2, Loader2 } from 'lucide-react'
import { getSurveillance } from '@/lib/api'
import type { SurveillanceRow } from '@/types/stewardship'

interface NationalSusceptibilityPanelProps {
  antibiotics: string[]
  /** Organisms from this episode's cultures; when present, only their rows are shown. */
  organisms: string[]
}

const PREVIEW_ROWS = 6

/**
 * ICMR AMRSN 2023 network surveillance, shown next to the culture as context. It is national
 * tertiary-care data, not this hospital's antibiogram, and no rule reads it.
 */
export function NationalSusceptibilityPanel({ antibiotics, organisms }: NationalSusceptibilityPanelProps) {
  const [rows, setRows] = useState<SurveillanceRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const drugKey = antibiotics.join('|')

  useEffect(() => {
    let live = true
    getSurveillance(drugKey ? drugKey.split('|') : [])
      .then((r) => live && setRows(r))
      .catch((e) => live && setError(e instanceof Error ? e.message : 'Could not load surveillance data.'))
    return () => {
      live = false
    }
  }, [drugKey])

  const wanted = new Set(organisms.map((o) => o.trim().toLowerCase()))
  const matches = (r: SurveillanceRow) => wanted.size === 0 || wanted.has(r.organism.toLowerCase())

  return (
    <section className="rounded-[8px] border border-[#E2E1DC] bg-white p-4">
      <div className="flex items-start gap-2">
        <Globe2 className="mt-0.5 h-4 w-4 shrink-0 text-[#3730A3]" />
        <div>
          <p className="text-sm font-medium text-[#1A1A1A]">National susceptibility (ICMR AMRSN 2023)</p>
          <p className="mt-0.5 text-xs text-[#6B6A65]">
            Network surveillance from Indian tertiary-care hospitals: advisory context only, not this hospital&apos;s
            antibiogram, and never used by the rules.{' '}
            {wanted.size > 0 ? 'Filtered to the organisms in this culture.' : 'No organism reported yet, so all organisms are listed.'}
          </p>
        </div>
      </div>

      {error && <p className="mt-3 text-xs text-[#8B1A1A]">{error}</p>}
      {!rows && !error && antibiotics.length > 0 && (
        <Loader2 className="mt-3 h-4 w-4 animate-spin text-[#6B6A65]" />
      )}
      {antibiotics.length === 0 && <p className="mt-3 text-xs text-[#6B6A65]">No antibiotics prescribed.</p>}

      {rows &&
        antibiotics.map((drug) => {
          const drugRows = rows
            .filter((r) => r.generic === drug && matches(r))
            .sort((a, b) => b.tested_count - a.tested_count)
          const shown = expanded[drug] ? drugRows : drugRows.slice(0, PREVIEW_ROWS)
          return (
            <div key={drug} className="mt-4">
              <p className="text-xs font-medium uppercase tracking-wider text-[#6B6A65]">{drug}</p>
              {drugRows.length === 0 ? (
                <p className="mt-1 text-xs text-[#6B6A65]">
                  No national surveillance row for {drug}
                  {wanted.size > 0 ? ' with this organism' : ''}.
                </p>
              ) : (
                <div className="mt-1 overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-[#6B6A65]">
                        <th className="py-1 pr-3 font-normal">Organism</th>
                        <th className="py-1 pr-3 font-normal">Specimen</th>
                        <th className="py-1 pr-3 text-right font-normal">Susceptible</th>
                        <th className="py-1 pr-3 text-right font-normal">Isolates</th>
                        <th className="py-1 font-normal">Source</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#F0EFEA]">
                      {shown.map((r, i) => {
                        const pct = r.susceptibility_percent ?? (100 * r.susceptible_count) / r.tested_count
                        return (
                          <tr key={`${r.organism}-${r.specimen}-${r.context}-${i}`} title={r.summary}>
                            <td className="py-1.5 pr-3 italic text-[#1A1A1A]">{r.organism}</td>
                            <td className="py-1.5 pr-3 text-[#6B6A65]">
                              {r.specimen}
                              {r.context ? ` · ${r.context}` : ''}
                            </td>
                            <td
                              className={`py-1.5 pr-3 text-right tabular-nums font-medium ${
                                pct >= 80 ? 'text-[#1A6B3C]' : pct >= 50 ? 'text-[#8B5E00]' : 'text-[#8B1A1A]'
                              }`}
                            >
                              {pct.toFixed(0)}%
                            </td>
                            <td className="py-1.5 pr-3 text-right tabular-nums text-[#6B6A65]">
                              {r.susceptible_count}/{r.tested_count}
                              {r.limited_evidence && <span className="ml-1 text-[#8B5E00]">limited</span>}
                            </td>
                            <td className="py-1.5 whitespace-nowrap text-[#6B6A65]">
                              {r.source_section}, p. {r.source_page}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                  {drugRows.length > PREVIEW_ROWS && (
                    <button
                      onClick={() => setExpanded((e) => ({ ...e, [drug]: !e[drug] }))}
                      className="mt-1 text-xs font-medium text-[#3730A3] hover:underline"
                    >
                      {expanded[drug] ? 'Show fewer' : `Show all ${drugRows.length} rows`}
                    </button>
                  )}
                </div>
              )}
            </div>
          )
        })}
    </section>
  )
}
