'use client'

import React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  ClipboardList,
  Upload,
  Clock,
  FlaskConical,
  ScrollText,
  Shield,
  X,
  Activity,
} from 'lucide-react'

interface SidebarProps {
  mobileOpen: boolean
  setMobileOpen: (open: boolean) => void
  pendingCount?: number
  timeoutCount?: number
}

const navItems = [
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { name: 'New Prescription', href: '/episode/new', icon: ClipboardList },
  { name: 'Culture & Resistance', href: '/culture', icon: FlaskConical },
  { name: 'Audit Log', href: '/audit', icon: ScrollText },
]

export const Sidebar: React.FC<SidebarProps> = ({
  mobileOpen,
  setMobileOpen,
  pendingCount = 0,
  timeoutCount = 0,
}) => {
  const pathname = usePathname()

  const isActive = (href: string) => {
    if (href === '/dashboard') return pathname === '/dashboard'
    return pathname.startsWith(href)
  }

  return (
    <>
      {/* Mobile Backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm md:hidden transition-opacity"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-64 bg-[#1a1d2e] border-r border-[#2d3148] flex flex-col justify-between transition-transform duration-300 ease-in-out md:static md:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Brand & Navigation */}
        <div className="flex flex-col flex-1 min-h-0">
          {/* Logo */}
          <div className="h-16 px-6 flex items-center justify-between border-b border-[#2d3148] shrink-0">
            <Link
              href="/dashboard"
              className="flex items-center gap-3 text-slate-100 group"
              onClick={() => setMobileOpen(false)}
            >
              <div className="w-9 h-9 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400 group-hover:scale-105 transition-transform">
                <Shield className="w-5 h-5" />
              </div>
              <div className="flex flex-col">
                <div className="flex items-center gap-1.5 font-bold text-lg tracking-tight text-slate-100">
                  RxGuard
                  <span className="text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                    v1.0
                  </span>
                </div>
                <span className="text-[10px] text-slate-400">Stewardship Copilot</span>
              </div>
            </Link>

            <button
              onClick={() => setMobileOpen(false)}
              className="p-1 rounded-lg text-slate-400 hover:text-slate-200 md:hidden"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Nav items */}
          <div className="px-3 py-4 space-y-6 overflow-y-auto flex-1">
            {/* Main nav */}
            <div>
              <p className="px-3 text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2">
                Clinical Workflow
              </p>
              <nav className="space-y-1">
                {navItems.map((item) => {
                  const active = isActive(item.href)
                  const Icon = item.icon
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setMobileOpen(false)}
                      className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                        active
                          ? 'bg-indigo-600/15 text-indigo-300 border-l-4 border-indigo-500 shadow-sm'
                          : 'text-slate-400 hover:text-slate-100 hover:bg-[#1e2235]'
                      }`}
                    >
                      <Icon className={`w-4 h-4 ${active ? 'text-indigo-400' : 'text-slate-400'}`} />
                      <span>{item.name}</span>
                    </Link>
                  )
                })}

                {/* 48-hour Review — special with badge */}
                <Link
                  href="/timeout"
                  onClick={() => setMobileOpen(false)}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                    isActive('/timeout')
                      ? 'bg-indigo-600/15 text-indigo-300 border-l-4 border-indigo-500 shadow-sm'
                      : 'text-slate-400 hover:text-slate-100 hover:bg-[#1e2235]'
                  }`}
                >
                  <Clock
                    className={`w-4 h-4 ${isActive('/timeout') ? 'text-indigo-400' : 'text-slate-400'}`}
                  />
                  <span className="flex-1">48-Hour Reviews</span>
                  {timeoutCount > 0 && (
                    <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30">
                      {timeoutCount}
                    </span>
                  )}
                </Link>
              </nav>
            </div>

            {/* System section */}
            <div>
              <p className="px-3 text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2">
                System
              </p>
              <div className="px-3 py-2.5 rounded-xl bg-[#141724] border border-[#2d3148] space-y-2">
                <div className="flex items-center gap-2">
                  <Activity className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="text-xs text-slate-300">Stewardship Engine</span>
                  <span className="ml-auto text-[10px] text-emerald-400 font-mono">Active</span>
                </div>
                <div className="text-[10px] text-slate-500 font-mono">
                  Ruleset v1.0.0 · ICMR/NCDC 2023
                </div>
              </div>
              {/* Image OCR is kept for later work and is not part of the typed-prescription demo. */}
              <Link
                href="/upload"
                onClick={() => setMobileOpen(false)}
                className="mt-2 flex items-center gap-2 px-3 py-2 rounded-xl text-xs text-slate-500 hover:text-slate-300 hover:bg-[#1e2235]"
              >
                <Upload className="w-3.5 h-3.5" />
                <span>Image OCR (experimental)</span>
              </Link>
            </div>
          </div>
        </div>

        {/* Safety disclaimer footer */}
        <div className="p-3 border-t border-[#2d3148] shrink-0">
          <div className="px-3 py-2.5 rounded-xl bg-amber-500/5 border border-amber-500/20">
            <p className="text-[10px] text-amber-300/80 leading-relaxed">
              ⚠ This system provides recommendations only. All clinical decisions require pharmacist review.
            </p>
          </div>
        </div>
      </aside>
    </>
  )
}
