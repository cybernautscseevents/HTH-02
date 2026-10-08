'use client'

import React, { useState } from 'react'
import { Sidebar } from '@/components/layout/Sidebar'
import { TopBar } from '@/components/layout/TopBar'

export default function ShellLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [role, setRole] = useState<'doctor' | 'pharmacist'>('pharmacist')

  return (
    <div className="min-h-screen bg-[#0f1117] flex overflow-hidden">
      {/* Sidebar */}
      <Sidebar
        mobileOpen={mobileOpen}
        setMobileOpen={setMobileOpen}
        timeoutCount={5}
        pendingCount={8}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
        <TopBar
          onMenuClick={() => setMobileOpen(true)}
          role={role}
          onRoleChange={setRole}
        />
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 bg-[#0f1117]">
          <div className="max-w-7xl mx-auto space-y-6">
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}
