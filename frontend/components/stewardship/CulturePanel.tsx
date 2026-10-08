'use client'

import React from 'react'
import { AlertTriangle, FlaskConical } from 'lucide-react'
import type { CultureStatus, SIR, Specimen } from '@/types/stewardship'
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

const SIR_LABELS: Record<SIR, string> = {
  S: 'Susceptible',
  I: 'Intermediate',
  R: 'Resistant',
  SDD: 'Susceptible-dose-dependent',
}

const STATUS: Record<CultureStatus, { label: string; variant: string; empty: string }> = {
  NOT_SENT: { label: 'Not sent', variant: 'default', empty: 'No culture was sent.' },
  PENDING: { label: 'Pending', variant: 'AMBIGUOUS', empty: 'Result pending.' },
  NO_GROWTH: { label: 'No growth', variant: 'ACCEPTED', empty: 'No growth reported.' },
  GROWTH_NO_AST: {
    label: 'Growth, no AST',
    variant: 'AMBIGUOUS',
    empty: 'Growth reported; susceptibility testing not yet available.',
  },
  FINAL: { label: 'Final', variant: 'ACCEPTED', empty: 'Final report with no isolates listed.' },
  CONTAMINATED: {
    label: 'Contaminated',
    variant: 'R',
    empty: 'Specimen reported as contaminated; consider repeating the culture.',
  },
}

const same = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase()

/**
 * The laboratory report for one specimen, with the patient's current antibiotics marked.
 * It only restates the report: which drug to step down to is decided by the culture rules
 * (C3-C9) and shown as findings, not inferred here.
 */
export const CulturePanel: React.FC<CulturePanelProps> = ({ specimen, currentAntibiotics = [] }) => {
  const specimenLabel = SPECIMEN_LABELS[specimen.specimen_type] ?? specimen.specimen_type
  const status = STATUS[specimen.status]

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 rounded-lg border border-[#E2E1DC] bg-[#F4F3EF] px-4 py-3">
        <FlaskConical className="h-4 w-4 text-[#3730A3]" />
        <div>
          <p className="text-sm font-semibold text-[#1A1A1A]">{specimenLabel} culture</p>
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
          <Badge variant={status.variant} size="sm">{status.label}</Badge>
        </div>
      </div>

      {specimen.isolates.map((isolate) => {
        const resultFor = (drug: string) =>
          isolate.susceptibilities.find((s) => same(s.agent, drug))?.result
        const resistant = currentAntibiotics.filter((drug) => resultFor(drug) === 'R')

        return (
          <div key={isolate.id} className="overflow-hidden rounded-xl border border-[#E2E1DC]">
            <div className="flex flex-wrap items-center gap-3 border-b border-[#E2E1DC] bg-white px-5 py-3">
              <div>
                <p className="text-base font-semibold italic text-[#1A1A1A]">{isolate.organism}</p>
                {isolate.probable_contaminant && (
                  <span className="text-xs text-[#8B5E00]">Probable contaminant</span>
                )}
              </div>
              {resistant.length > 0 && (
                <div className="ml-auto flex items-center gap-2 rounded-lg border border-[#D9A4A4] bg-[#FDF2F2] px-3 py-1.5">
                  <AlertTriangle className="h-4 w-4 text-[#8B1A1A]" />
                  <span className="text-xs font-semibold text-[#8B1A1A]">
                    Resistant to current {resistant.join(', ')}
                  </span>
                </div>
              )}
            </div>

            {isolate.susceptibilities.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[#E2E1DC] bg-[#FAFAF8]">
                      {['Antibiotic', 'Result', 'Interpretation', 'For this patient'].map((h, i) => (
                        <th
                          key={h}
                          className={`px-5 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-[#6B6A65] ${
                            i === 2 ? 'hidden sm:table-cell' : i === 3 ? 'hidden md:table-cell' : ''
                          }`}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#E2E1DC]">
                    {isolate.susceptibilities.map((sus) => {
                      const isCurrent = currentAntibiotics.some((drug) => same(drug, sus.agent))
                      return (
                        <tr key={sus.agent} className={isCurrent ? 'bg-[#F7F6FF]' : 'hover:bg-[#FAFAF8]'}>
                          <td className="px-5 py-3">
                            <div className="flex items-center gap-2">
                              <span className="capitalize text-[#1A1A1A]">{sus.agent}</span>
                              {isCurrent && (
                                <span className="rounded border border-[#D8D5F0] bg-white px-1.5 py-0.5 text-xs text-[#3730A3]">
                                  Current
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="px-5 py-3">
                            <Badge variant={sus.result} size="sm">{sus.result}</Badge>
                          </td>
                          <td className="hidden px-5 py-3 text-xs text-[#6B6A65] sm:table-cell">
                            {SIR_LABELS[sus.result] ?? sus.result}
                          </td>
                          <td className="hidden px-5 py-3 text-xs md:table-cell">
                            {isCurrent && sus.result === 'R' && (
                              <span className="flex items-center gap-1.5 text-[#8B1A1A]">
                                <AlertTriangle className="h-3.5 w-3.5" /> Not covered; review
                              </span>
                            )}
                            {isCurrent && (sus.result === 'I' || sus.result === 'SDD') && (
                              <span className="text-[#8B5E00]">Not treated as susceptible; review dose or drug</span>
                            )}
                            {isCurrent && sus.result === 'S' && <span className="text-[#1A6B3C]">Covered</span>}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="bg-white px-5 py-3 text-xs text-[#6B6A65]">No susceptibility results reported.</p>
            )}

            {resistant.length > 0 && (
              <div className="border-t border-[#E8D5A7] bg-[#FFF9EB] px-5 py-3">
                <p className="mb-1 text-xs font-medium text-[#8B5E00]">Antibiotic review recommended</p>
                <p className="text-xs text-[#6B6A65]">
                  {resistant.join(', ')} may not cover <em>{isolate.organism}</em>. See the culture
                  findings for a guideline option the organism is susceptible to.
                </p>
              </div>
            )}
          </div>
        )
      })}

      {specimen.isolates.length === 0 && (
        <p className="py-6 text-center text-sm text-[#6B6A65]">{status.empty}</p>
      )}
    </div>
  )
}
