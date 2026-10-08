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
          <p className="text-xs font-medium uppercase tracking-wider text-[#6B6A65]">Governance</p>
          <h1 className="mt-1 text-2xl font-medium text-[#1A1A1A]">Audit log</h1>
          <p className="mt-1 text-sm text-[#6B6A65]">
            Append-only record of pharmacist decisions and system events.
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

      <div className="rounded-[8px] border border-[#E2E1DC] bg-white p-4">
        <div className="flex items-start gap-3">
          <ScrollText className="mt-0.5 h-4 w-4 shrink-0 text-[#3730A3]" />
          <p className="text-xs leading-relaxed text-[#6B6A65]">
            Every approval, modification, removal, override, escalation, and evaluation is retained. Entries cannot be edited or deleted.
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
            <span className="text-xs text-[#6B6A65]">{entries.length} entries total</span>
          </div>
          <AuditTable entries={entries} />
        </>
      )}
    </div>
  )
}
