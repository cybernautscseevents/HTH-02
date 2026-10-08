'use client'

import React, { useEffect, useState } from 'react'
import { Loader2, ScrollText, Download } from 'lucide-react'
import { getAuditLog } from '@/lib/api'
import type { AuditEntry } from '@/types/stewardship'
import { AuditTable } from '@/components/stewardship/AuditTable'
import { Button } from '@/components/ui/Button'

export default function AuditPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getAuditLog()
      .then(setEntries)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Page header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Audit Log</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            Append-only clinical audit trail — all pharmacist decisions and system events
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          leftIcon={<Download className="w-4 h-4" />}
          onClick={() => {
            const json = JSON.stringify(entries, null, 2)
            const blob = new Blob([json], { type: 'application/json' })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `rxguard-audit-${new Date().toISOString().split('T')[0]}.json`
            a.click()
            URL.revokeObjectURL(url)
          }}
        >
          Export JSON
        </Button>
      </div>

      {/* Info box */}
      <div className="p-4 rounded-xl border border-[#2d3148] bg-[#1e2235]">
        <div className="flex items-start gap-3">
          <ScrollText className="w-4 h-4 text-indigo-400 mt-0.5 shrink-0" />
          <p className="text-xs text-slate-400 leading-relaxed">
            This log records every pharmacist review decision (Accept, Modify, Override) and all
            system-generated evaluation events. Entries are append-only and cannot be edited or
            deleted, ensuring a trustworthy clinical audit trail.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-indigo-400" />
        </div>
      ) : (
        <>
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-400">
              {entries.length} entries total
            </span>
          </div>
          <AuditTable entries={entries} />
        </>
      )}
    </div>
  )
}
