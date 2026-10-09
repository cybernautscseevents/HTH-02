'use client'

import React, { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Loader2 } from 'lucide-react'
import { getHealth, getStats } from '@/lib/api'
import { useSession } from '@/lib/auth'
import { Sidebar } from '@/components/layout/Sidebar'
import { TopBar } from '@/components/layout/TopBar'

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const router = useRouter()
  const { user, ready, logout } = useSession()
  const [pendingCount, setPendingCount] = useState(0)
  const [timeoutCount, setTimeoutCount] = useState(0)
  const [rulesetVersion, setRulesetVersion] = useState<string | null>(null)

  useEffect(() => {
    if (ready && !user) router.replace('/login')
  }, [ready, user, router])

  useEffect(() => {
    if (!user) return
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
  }, [user])

  if (!ready || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#FAFAF8]">
        <Loader2 className="h-6 w-6 animate-spin text-[#3730A3]" />
      </div>
    )
  }

  return (
    <div className="flex min-h-screen overflow-hidden bg-[#FAFAF8]">
      <Sidebar
        mobileOpen={mobileOpen}
        setMobileOpen={setMobileOpen}
        timeoutCount={timeoutCount}
        pendingCount={pendingCount}
        rulesetVersion={rulesetVersion}
        role={user.role}
      />
      <div className="flex h-screen min-w-0 flex-1 flex-col overflow-hidden">
        <TopBar
          onMenuClick={() => setMobileOpen(true)}
          user={user}
          onSignOut={() => {
            logout()
            router.replace('/login')
          }}
          rulesetVersion={rulesetVersion}
        />
        <main className="flex-1 overflow-y-auto bg-[#FAFAF8] p-4 sm:p-6 lg:p-8">
          <div className="mx-auto max-w-7xl space-y-6">{children}</div>
        </main>
      </div>
    </div>
  )
}
