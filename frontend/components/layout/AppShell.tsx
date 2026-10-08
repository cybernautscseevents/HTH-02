'use client'

import React, { useEffect, useState } from 'react'
import { getHealth, getStats } from '@/lib/api'
import { Sidebar } from '@/components/layout/Sidebar'
import { TopBar } from '@/components/layout/TopBar'

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [role, setRole] = useState<'doctor' | 'pharmacist'>('pharmacist')
  const [pendingCount, setPendingCount] = useState(0)
  const [timeoutCount, setTimeoutCount] = useState(0)
  const [rulesetVersion, setRulesetVersion] = useState<string | null>(null)

  useEffect(() => {
    getStats()
      .then((stats) => {
        setPendingCount(stats.pending_review_count)
        setTimeoutCount(stats.timeout_due_count)
      })
      .catch(() => {
        setPendingCount(0)
        setTimeoutCount(0)
      })
    getHealth()
      .then((health) => setRulesetVersion(health.ruleset_version))
      .catch(() => setRulesetVersion(null))
  }, [])

  return (
    <div className="flex min-h-screen overflow-hidden bg-[#FAFAF8]">
      <Sidebar
        mobileOpen={mobileOpen}
        setMobileOpen={setMobileOpen}
        timeoutCount={timeoutCount}
        pendingCount={pendingCount}
        rulesetVersion={rulesetVersion}
      />
      <div className="flex h-screen min-w-0 flex-1 flex-col overflow-hidden">
        <TopBar
          onMenuClick={() => setMobileOpen(true)}
          role={role}
          onRoleChange={setRole}
          rulesetVersion={rulesetVersion}
        />
        <main className="flex-1 overflow-y-auto bg-[#FAFAF8] p-4 sm:p-6 lg:p-8">
          <div className="mx-auto max-w-7xl space-y-6">{children}</div>
        </main>
      </div>
    </div>
  )
}
