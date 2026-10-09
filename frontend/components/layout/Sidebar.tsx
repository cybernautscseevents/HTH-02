'use client'

import React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Activity, Clock, FlaskConical, LayoutDashboard, ScrollText, ShieldCheck, Upload, X } from 'lucide-react'

interface SidebarProps {
  mobileOpen: boolean
  setMobileOpen: (open: boolean) => void
  pendingCount?: number
  timeoutCount?: number
  rulesetVersion?: string | null
}

const navItems = [
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { name: 'New review', href: '/upload', icon: Upload },
  { name: 'Culture & resistance', href: '/culture', icon: FlaskConical },
  { name: 'Audit log', href: '/audit', icon: ScrollText },
]

export const Sidebar: React.FC<SidebarProps> = ({
  mobileOpen,
  setMobileOpen,
  pendingCount = 0,
  timeoutCount = 0,
  rulesetVersion = null,
}) => {
  const pathname = usePathname()
  const isActive = (href: string) =>
    href === '/dashboard' ? pathname === href : pathname.startsWith(href)

  return (
    <>
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/35 backdrop-blur-[1px] transition-opacity md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-64 flex-col justify-between border-r border-[#E2E1DC] bg-[#F4F3EF] transition-transform duration-300 ease-in-out md:static md:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex h-16 shrink-0 items-center justify-between border-b border-[#E2E1DC] px-6">
            <Link href="/dashboard" className="group flex items-center gap-2.5" onClick={() => setMobileOpen(false)}>
              <div className="flex h-8 w-8 items-center justify-center rounded-md bg-[#1A1A1A] text-white">
                <ShieldCheck className="h-4 w-4" />
              </div>
              <div>
                <div className="flex items-center gap-1.5 text-xl font-medium tracking-[-0.03em] text-[#1A1A1A]">
                  RxGuard
                  <span className="rounded border border-[#E2E1DC] bg-white px-1.5 py-0.5 text-xs font-medium tracking-normal text-[#6B6A65]">NCDC</span>
                </div>
                <p className="text-xs leading-none text-[#6B6A65]">Stewardship workspace</p>
              </div>
            </Link>
            <button onClick={() => setMobileOpen(false)} className="rounded p-1 text-[#6B6A65] hover:bg-[#EEEEE9] hover:text-[#1A1A1A] md:hidden" aria-label="Close navigation">
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
            <section>
              <div className="mb-2 flex items-center justify-between px-3">
                <p className="text-xs font-medium uppercase tracking-wider text-[#6B6A65]">Clinical workflow</p>
                {pendingCount > 0 && <span className="rounded border border-[#E2E1DC] bg-white px-1.5 text-xs font-mono text-[#6B6A65]">{pendingCount} open</span>}
              </div>
              <nav className="space-y-0.5">
                {navItems.map((item) => {
                  const active = isActive(item.href)
                  const Icon = item.icon
                  return (
                    <Link key={item.href} href={item.href} onClick={() => setMobileOpen(false)} className={`flex items-center gap-3 rounded-md px-3 py-2 text-xs font-medium transition-all ${active ? 'border-l-[3px] border-[#1A1A1A] bg-[#EEEEE9] pl-[9px] text-[#1A1A1A]' : 'text-[#6B6A65] hover:bg-[#EEEEE9] hover:text-[#1A1A1A]'}`}>
                      <Icon className="h-4 w-4" />
                      <span>{item.name}</span>
                    </Link>
                  )
                })}
                <Link href="/timeout" onClick={() => setMobileOpen(false)} className={`flex items-center gap-3 rounded-md px-3 py-2 text-xs font-medium transition-all ${isActive('/timeout') ? 'border-l-[3px] border-[#1A1A1A] bg-[#EEEEE9] pl-[9px] text-[#1A1A1A]' : 'text-[#6B6A65] hover:bg-[#EEEEE9] hover:text-[#1A1A1A]'}`}>
                  <Clock className="h-4 w-4" />
                  <span className="flex-1">Antimicrobial re-reviews</span>
                  {timeoutCount > 0 && <span className="rounded-full border border-[#D8B15B] bg-[#FFF8E6] px-1.5 py-0.5 text-xs font-semibold text-[#8B5E00]">{timeoutCount}</span>}
                </Link>
              </nav>
            </section>

            <section>
              <p className="mb-2 px-3 text-xs font-medium uppercase tracking-wider text-[#6B6A65]">System</p>
              <div className="rounded-md border border-[#E2E1DC] bg-white p-3">
                <div className="flex items-center gap-2 text-xs text-[#1A1A1A]">
                  <Activity className="h-3.5 w-3.5 text-[#1A6B3C]" />
                  <span>Deterministic engine</span>
                  <span className="ml-auto font-mono text-xs text-[#1A6B3C]">LIVE</span>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-[#6B6A65]">
                  {rulesetVersion ? `Ruleset ${rulesetVersion}` : 'NCDC rule pack'} · Every finding is traceable to a rule and source.
                </p>
              </div>
            </section>
          </div>
        </div>

        <div className="border-t border-[#E2E1DC] p-3">
          <div className="rounded-md border border-[#E8D5A7] bg-[#FFF9EB] px-3 py-2.5">
            <p className="text-xs leading-relaxed text-[#8B5E00]">Decision support only. A pharmacist or clinician must approve every treatment change.</p>
          </div>
        </div>
      </aside>
    </>
  )
}
