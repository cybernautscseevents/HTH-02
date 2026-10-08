'use client'

import React, { useState } from 'react'
import type { AuditEntry } from '@/types/stewardship'

interface AuditTableProps {
  entries: AuditEntry[]
}

const ACTION_STYLES: Record<string, string> = {
  'review.ACCEPT': 'text-emerald-400',
  'review.MODIFY': 'text-indigo-400',
  'review.OVERRIDE': 'text-rose-400',
  'review.ESCALATE': 'text-amber-400',
  'evaluation.created': 'text-sky-400',
}

function formatAction(action: string): string {
  const parts = action.split('.')
  if (parts.length < 2) return action
  const [, verb] = parts
  const labels: Record<string, string> = {
    ACCEPT: 'Accepted suggestion',
    MODIFY: 'Modified plan',
    OVERRIDE: 'Overrode with reason',
    ESCALATE: 'Escalated',
    created: 'Evaluation created',
  }
  return labels[verb] ?? verb
}

function formatEntity(entity: string, entityId: string): string {
  if (entity === 'finding') {
    const parts = entityId.split(':')
    return parts[1] ?? entityId
  }
  if (entity === 'evaluation') return entityId
  return `${entity}:${entityId}`
}

export const AuditTable: React.FC<AuditTableProps> = ({ entries }) => {
  const [filter, setFilter] = useState('')

  const filtered = entries.filter((e) => {
    const q = filter.toLowerCase()
    return (
      e.actor.toLowerCase().includes(q) ||
      e.action.toLowerCase().includes(q) ||
      e.entity_id.toLowerCase().includes(q) ||
      JSON.stringify(e.payload).toLowerCase().includes(q)
    )
  })

  return (
    <div className="space-y-4">
      {/* Filter */}
      <input
        type="text"
        placeholder="Search by actor, action, entity..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        className="w-full bg-[#1e2235] border border-[#2d3148] rounded-xl px-4 py-2.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
      />

      {/* Table */}
      <div className="rounded-xl border border-[#2d3148] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#2d3148] bg-[#141724]">
                <th className="text-left px-5 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wide">
                  Timestamp
                </th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wide">
                  Actor
                </th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wide">
                  Decision
                </th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wide hidden md:table-cell">
                  Finding / Entity
                </th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wide hidden lg:table-cell">
                  Reason
                </th>
                <th className="text-left px-5 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wide hidden xl:table-cell">
                  Note
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#2d3148]">
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-5 py-8 text-center text-slate-400 text-sm">
                    No audit entries found.
                  </td>
                </tr>
              )}
              {filtered.map((entry, i) => {
                const date = new Date(entry.at)
                const timestamp = date.toLocaleString('en-IN', {
                  day: '2-digit',
                  month: 'short',
                  year: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })
                const payload = entry.payload as Record<string, string>

                return (
                  <tr key={i} className="hover:bg-[#2d3148]/30 transition-colors">
                    <td className="px-5 py-3 whitespace-nowrap">
                      <span className="text-xs font-mono text-slate-300">{timestamp}</span>
                    </td>
                    <td className="px-5 py-3">
                      <span className="text-slate-200 text-xs">{entry.actor}</span>
                    </td>
                    <td className="px-5 py-3">
                      <span
                        className={`text-xs font-semibold ${ACTION_STYLES[entry.action] ?? 'text-slate-300'}`}
                      >
                        {formatAction(entry.action)}
                      </span>
                    </td>
                    <td className="px-5 py-3 hidden md:table-cell">
                      <span className="text-xs font-mono text-slate-400">
                        {formatEntity(entry.entity, entry.entity_id)}
                      </span>
                    </td>
                    <td className="px-5 py-3 hidden lg:table-cell">
                      <span className="text-xs text-slate-400">
                        {payload.reason_code
                          ? payload.reason_code.replace(/_/g, ' ')
                          : '—'}
                      </span>
                    </td>
                    <td className="px-5 py-3 hidden xl:table-cell max-w-xs">
                      <span className="text-xs text-slate-400 line-clamp-2">{payload.note ?? '—'}</span>
                    </td>
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
