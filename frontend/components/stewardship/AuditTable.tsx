'use client'

import React, { useState } from 'react'
import type { AuditEntry } from '@/types/stewardship'
import { ROLE_STYLE, type Role } from '@/lib/auth'

interface AuditTableProps { entries: AuditEntry[] }

const ACTION_STYLES: Record<string, string> = {
  'review.ACCEPT': 'text-[#1A6B3C]',
  'review.MODIFY': 'text-[#8B5E00]',
  'review.REMOVE': 'text-[#8B1A1A]',
  'review.OVERRIDE': 'text-[#8B1A1A]',
  'review.ESCALATE': 'text-[#934B13]',
  'evaluation.created': 'text-[#3730A3]',
  'treatment_plan.signed': 'text-[#1A6B3C]',
  'treatment_plan.superseded': 'text-[#8B5E00]',
  'plan_review.APPROVED': 'text-[#0F6B5C]',
  'plan_review.CHANGES_REQUESTED': 'text-[#8B5E00]',
}

const LABELS: Record<string, string> = {
  ACCEPT: 'Approved', MODIFY: 'Modified', REMOVE: 'Removed', OVERRIDE: 'Overridden', ESCALATE: 'Escalated', created: 'Evaluation created', signed: 'Treatment plan signed', superseded: 'Treatment plan revised', APPROVED: 'Prescriber approved plan', CHANGES_REQUESTED: 'Prescriber requested changes',
}

function formatAction(action: string) {
  return LABELS[action.split('.')[1]] ?? action
}

/** Actor name and role. Reviews carry the role in the actor ("Name (Pharmacist)"); plans carry it in the payload. */
function actorRole(entry: AuditEntry): { name: string; role: Role | null } {
  const match = entry.actor.match(/^(.*) \((Pharmacist|Physician)\)$/)
  const label = match?.[2] ?? (entry.payload.reviewer_role === 'PHYSICIAN' ? 'Physician' : entry.payload.reviewer_role === 'PHARMACIST' ? 'Pharmacist' : null)
  const role = label === 'Physician' ? 'doctor' : label === 'Pharmacist' ? 'pharmacist' : null
  return { name: match?.[1] ?? entry.actor, role }
}

function formatEntity(entry: AuditEntry) {
  if (entry.entity === 'finding') return entry.entity_id.split(':')[1] ?? entry.entity_id
  return entry.entity_id
}

export const AuditTable: React.FC<AuditTableProps> = ({ entries }) => {
  const [filter, setFilter] = useState('')
  const filtered = entries.filter((entry) => JSON.stringify(entry).toLowerCase().includes(filter.toLowerCase()))

  return (
    <div className="space-y-3">
      <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Search actor, decision, rule, or note" className="w-full rounded-md border border-[#C8C7C0] bg-white px-3 py-2 text-sm outline-none focus:border-[#3730A3]" />
      <div className="overflow-hidden rounded-[8px] border border-[#E2E1DC] bg-white">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-[#E2E1DC] bg-[#F4F3EF] text-left text-xs font-medium uppercase tracking-wider text-[#6B6A65]">
              <tr><th className="px-4 py-3">Time</th><th className="px-4 py-3">Actor</th><th className="px-4 py-3">Decision</th><th className="hidden px-4 py-3 md:table-cell">Rule / entity</th><th className="hidden px-4 py-3 lg:table-cell">Reason</th><th className="hidden px-4 py-3 xl:table-cell">Note</th></tr>
            </thead>
            <tbody className="divide-y divide-[#E2E1DC]">
              {filtered.length === 0 && <tr><td colSpan={6} className="px-4 py-10 text-center text-sm text-[#6B6A65]">No matching audit entries.</td></tr>}
              {filtered.map((entry, index) => {
                const payload = entry.payload as Record<string, string | null>
                const actor = actorRole(entry)
                return (
                  <tr key={`${entry.at}-${index}`} className="hover:bg-[#FAFAF8]">
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-[#6B6A65]">{new Date(entry.at).toLocaleString('en-IN')}</td>
                    <td className="px-4 py-3 text-xs text-[#1A1A1A]">
                      {actor.name}
                      {actor.role && <span className={`ml-1.5 whitespace-nowrap rounded border px-1.5 text-[10px] font-semibold uppercase tracking-wider ${ROLE_STYLE[actor.role].tag}`}>{ROLE_STYLE[actor.role].label}</span>}
                    </td>
                    <td className={`px-4 py-3 text-xs font-medium ${ACTION_STYLES[entry.action] ?? 'text-[#1A1A1A]'}`}>{formatAction(entry.action)}</td>
                    <td className="hidden px-4 py-3 font-mono text-xs text-[#6B6A65] md:table-cell">{formatEntity(entry)}</td>
                    <td className="hidden px-4 py-3 text-xs text-[#6B6A65] lg:table-cell">{payload.reason_code?.replace(/_/g, ' ') ?? '—'}</td>
                    <td className="hidden max-w-xs px-4 py-3 text-xs text-[#6B6A65] xl:table-cell">{payload.note ?? '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
