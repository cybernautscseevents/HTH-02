'use client'

import React from 'react'
import { AlertTriangle, FlaskConical, ArrowRight } from 'lucide-react'
import type { Specimen } from '@/types/stewardship'
import { Badge } from '@/components/ui/Badge'

interface CulturePanelProps {
  specimen: Specimen
  currentAntibiotics?: string[]
}

const SPECIMEN_LABELS: Record<string, string> = {
  urine: 'Urine',
  blood: 'Blood',
  sputum: 'Sputum',
  pus: 'Pus/Wound',
  csf: 'Cerebrospinal Fluid',
}

const SIR_LABELS: Record<string, string> = {
  S: 'Susceptible',
  I: 'Intermediate',
  R: 'Resistant',
  SDD: 'Susceptible-Dose-Dependent',
}

export const CulturePanel: React.FC<CulturePanelProps> = ({ specimen, currentAntibiotics = [] }) => {
  const specimenLabel = SPECIMEN_LABELS[specimen.specimen_type] ?? specimen.specimen_type

  return (
    <div className="space-y-4">
      {/* Specimen header */}
      <div className="flex items-center gap-3 px-4 py-3 rounded-lg border border-[#E2E1DC] bg-[#F4F3EF]">
        <FlaskConical className="w-4 h-4 text-indigo-400" />
        <div>
          <p className="text-sm font-semibold text-[#1A1A1A]">{specimenLabel} Culture</p>
          <p className="text-xs text-[#6B6A65]">
            Specimen {specimen.id}
            {specimen.collected_at && (
              <> · Collected {new Date(specimen.collected_at).toLocaleDateString('en-IN')}</>
            )}
            {specimen.reported_at && (
              <> · Reported {new Date(specimen.reported_at).toLocaleDateString('en-IN')}</>
            )}
          </p>
        </div>
        <div className="ml-auto">
          <Badge variant={specimen.status === 'FINAL' ? 'ACCEPTED' : 'AMBIGUOUS'} size="sm">
            {specimen.status.replace('_', ' ')}
          </Badge>
        </div>
      </div>

      {/* Isolates */}
      {specimen.isolates.map((isolate) => {
        const resistantToCurrentAb = currentAntibiotics.some((ab) => {
          const sus = isolate.susceptibilities.find(
            (s) => s.agent.toLowerCase() === ab.toLowerCase()
          )
          return sus?.result === 'R'
        })

        return (
          <div key={isolate.id} className="rounded-xl border border-[#E2E1DC] overflow-hidden">
            {/* Organism header */}
            <div className="px-5 py-3 border-b border-[#E2E1DC] bg-white flex items-center gap-3">
              <div>
                <p className="text-base font-semibold text-[#1A1A1A] italic">{isolate.organism}</p>
                {isolate.probable_contaminant && (
                  <span className="text-xs text-amber-300">Probable contaminant</span>
                )}
              </div>

              {resistantToCurrentAb && (
                <div className="ml-auto flex items-center gap-2 px-3 py-1.5 rounded-lg bg-rose-500/10 border border-rose-500/30">
                  <AlertTriangle className="w-4 h-4 text-rose-400" />
                  <span className="text-xs font-semibold text-rose-300">
                    Resistant to current antibiotic
                  </span>
                </div>
              )}
            </div>

            {/* Susceptibility table */}
            {isolate.susceptibilities.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[#2d3148] bg-[#141724]">
                      <th className="text-left px-5 py-2.5 text-xs font-semibold text-[#6B6A65] uppercase tracking-wide">
                        Antibiotic
                      </th>
                      <th className="text-left px-5 py-2.5 text-xs font-semibold text-[#6B6A65] uppercase tracking-wide">
                        Result
                      </th>
                      <th className="text-left px-5 py-2.5 text-xs font-semibold text-[#6B6A65] uppercase tracking-wide hidden sm:table-cell">
                        Interpretation
                      </th>
                      <th className="text-left px-5 py-2.5 text-xs font-semibold text-[#6B6A65] uppercase tracking-wide hidden md:table-cell">
                        Status
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#E2E1DC]">
                    {isolate.susceptibilities.map((sus) => {
                      const isCurrent = currentAntibiotics.some(
                        (ab) => ab.toLowerCase() === sus.agent.toLowerCase()
                      )
                      return (
                        <tr
                          key={sus.agent}
                          className={`transition-colors ${isCurrent ? 'bg-indigo-500/5' : 'hover:bg-[#2d3148]/30'}`}
                        >
                          <td className="px-5 py-3">
                            <div className="flex items-center gap-2">
                              <span className="text-[#1A1A1A] capitalize">{sus.agent}</span>
                              {isCurrent && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                                  Current
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="px-5 py-3">
                            <Badge variant={sus.result} size="sm">
                              {sus.result}
                            </Badge>
                          </td>
                          <td className="px-5 py-3 hidden sm:table-cell">
                            <span className="text-xs text-[#6B6A65]">
                              {SIR_LABELS[sus.result] ?? sus.result}
                            </span>
                          </td>
                          <td className="px-5 py-3 hidden md:table-cell">
                            {sus.result === 'R' && isCurrent ? (
                              <div className="flex items-center gap-1.5 text-xs text-rose-300">
                                <AlertTriangle className="w-3.5 h-3.5" />
                                Review recommended
                              </div>
                            ) : sus.result === 'S' && !isCurrent ? (
                              <div className="flex items-center gap-1.5 text-xs text-emerald-300">
                                <ArrowRight className="w-3.5 h-3.5" />
                                Step-down option
                              </div>
                            ) : null}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Step-down suggestion */}
            {resistantToCurrentAb && (
              <div className="px-5 py-3 bg-amber-500/5 border-t border-amber-500/20">
                <p className="mb-1 text-xs font-medium text-[#8B5E00]">Antibiotic review recommended</p>
                <p className="text-xs text-[#6B6A65]">
                  The current antibiotic may not adequately cover{' '}
                  <em>{isolate.organism}</em>. Review the susceptibility report and consider
                  switching to an agent marked Susceptible (S).
                </p>
                <p className="mt-1.5 text-[10px] text-slate-500 italic">
                  Suggested action — requires pharmacist review before any change.
                </p>
              </div>
            )}
          </div>
        )
      })}

      {specimen.isolates.length === 0 && (
        <div className="text-center py-6 text-[#6B6A65] text-sm">
          {specimen.status === 'NO_GROWTH'
            ? 'No growth after 48 hours'
            : 'Results pending...'}
        </div>
      )}
    </div>
  )
}
