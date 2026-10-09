'use client'

import React from 'react'
import { ArrowLeftRight, Bell, BookOpenCheck, LogOut } from 'lucide-react'
import { otherUser, ROLE_STYLE, switchUser, type DemoUser } from '@/lib/auth'

interface TopBarProps {
  onMenuClick: () => void
  user: DemoUser
  onSignOut: () => void
  rulesetVersion?: string | null
}

export const TopBar: React.FC<TopBarProps> = ({
  onMenuClick,
  user,
  onSignOut,
  rulesetVersion,
}) => (
  <header className="sticky top-0 z-30 flex h-[52px] items-center justify-between border-b border-[#E2E1DC] bg-white px-4 shadow-[0_1px_2px_rgba(0,0,0,0.03)] sm:px-6">
    <div className="flex items-center gap-3">
      <button
        onClick={onMenuClick}
        className="rounded p-1.5 text-[#6B6A65] transition-colors hover:bg-[#F4F3EF] hover:text-[#1A1A1A] md:hidden"
        aria-label="Toggle navigation"
      >
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1.5 rounded border border-[#E2E1DC] bg-[#F4F3EF] px-2 py-0.5 text-xs font-medium text-[#1A6B3C]">
          <span className="h-1.5 w-1.5 rounded-full bg-[#1A6B3C]" />
          <span className="hidden sm:inline">Engine live</span>
        </div>
        {rulesetVersion && (
          <div className="hidden items-center gap-1.5 rounded border border-[#E2E1DC] bg-[#FAFAF8] px-2 py-0.5 text-xs text-[#6B6A65] sm:flex">
            <BookOpenCheck className="h-3 w-3 text-[#1A1A1A]" />
            <span className="max-w-52 truncate font-mono">{rulesetVersion}</span>
          </div>
        )}
      </div>
    </div>

    <div className="flex items-center gap-2.5 sm:gap-3">
      <div className="hidden items-center gap-2 border-l border-[#E2E1DC] pl-3 sm:flex">
        <div className="text-right">
          <p className="flex items-center justify-end gap-1.5 text-xs font-medium text-[#1A1A1A]">
            {user.name}
            <span className={`rounded border px-1.5 text-[10px] font-semibold uppercase tracking-wider ${ROLE_STYLE[user.role].tag}`}>
              {ROLE_STYLE[user.role].label}
            </span>
          </p>
          <p className="font-mono text-xs text-[#6B6A65]">
            {user.badge}
          </p>
        </div>
        <div className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-medium text-white ${user.role === 'doctor' ? 'bg-[#0F6B5C]' : 'bg-[#3730A3]'}`}>
          {user.initials}
        </div>
      </div>

      <button
        onClick={() => switchUser(user)}
        className="flex items-center gap-1.5 rounded-md border border-[#E2E1DC] px-2 py-1 text-xs font-medium text-[#6B6A65] hover:bg-[#F4F3EF] hover:text-[#1A1A1A]"
        title={`Switch to ${otherUser(user).name}`}
      >
        <ArrowLeftRight className="h-3.5 w-3.5" />
        <span className="hidden lg:inline">Switch to {ROLE_STYLE[otherUser(user).role].label.toLowerCase()}</span>
      </button>

      <button onClick={onSignOut} className="rounded p-1.5 text-[#6B6A65] hover:bg-[#F4F3EF] hover:text-[#1A1A1A]" title="Sign out" aria-label="Sign out">
        <LogOut className="h-4 w-4" />
      </button>

      <button className="relative rounded p-1.5 text-[#6B6A65] hover:bg-[#F4F3EF] hover:text-[#1A1A1A]" title="Notifications">
        <Bell className="h-4 w-4" />
      </button>
    </div>
  </header>
)
