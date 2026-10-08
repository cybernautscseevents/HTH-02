'use client'

import React from 'react'
import { Bell, User, Shield, Stethoscope } from 'lucide-react'

interface TopBarProps {
  onMenuClick: () => void
  role: 'doctor' | 'pharmacist'
  onRoleChange: (role: 'doctor' | 'pharmacist') => void
}

export const TopBar: React.FC<TopBarProps> = ({ onMenuClick, role, onRoleChange }) => {
  return (
    <header className="h-16 bg-[#1a1d2e] border-b border-[#2d3148] px-4 sm:px-6 flex items-center justify-between sticky top-0 z-30 shadow-sm backdrop-blur-md">
      {/* Left section */}
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuClick}
          className="md:hidden p-2 rounded-xl text-slate-400 hover:text-slate-100 hover:bg-[#2d3148] transition-colors"
          aria-label="Toggle Navigation"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        {/* Status pills */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-950/40 border border-emerald-500/30 text-emerald-400 text-xs">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="font-medium hidden sm:inline">Engine Active</span>
          </div>

          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#141724] border border-[#2d3148] text-xs">
            <Shield className="w-3.5 h-3.5 text-indigo-400" />
            <span className="text-slate-300 font-mono text-[11px]">ICMR/NCDC Ruleset v1.0</span>
          </div>
        </div>
      </div>

      {/* Right section */}
      <div className="flex items-center gap-2.5 sm:gap-4">
        {/* Role switcher for demo */}
        <div className="flex items-center gap-1 p-1 rounded-xl bg-[#141724] border border-[#2d3148]">
          <button
            onClick={() => onRoleChange('doctor')}
            className={`px-2.5 py-1 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-all ${
              role === 'doctor'
                ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30 font-semibold shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
            title="Switch to Doctor view"
          >
            <Stethoscope className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Doctor</span>
          </button>
          <button
            onClick={() => onRoleChange('pharmacist')}
            className={`px-2.5 py-1 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-all ${
              role === 'pharmacist'
                ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-semibold shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
            title="Switch to Pharmacist view"
          >
            <Shield className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Pharmacist</span>
          </button>
        </div>

        {/* User avatar */}
        <div className="hidden sm:flex items-center gap-2 pl-2 border-l border-[#2d3148]">
          <div className="text-right">
            <p className="text-xs font-semibold text-slate-200">
              {role === 'pharmacist' ? 'Dr. Priya Mehta' : 'Dr. Suresh Kumar'}
            </p>
            <p className="text-[10px] text-slate-400 font-mono">
              {role === 'pharmacist' ? 'Pharmacist · ID-0042' : 'Physician · ID-0031'}
            </p>
          </div>
          <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-600 to-indigo-400 text-white font-semibold text-xs flex items-center justify-center shadow-md shrink-0">
            {role === 'pharmacist' ? 'PM' : 'SK'}
          </div>
        </div>

        {/* Notifications */}
        <div className="relative">
          <button
            className="p-2 rounded-xl text-slate-400 hover:text-slate-100 hover:bg-[#2d3148] transition-colors relative"
            title="Notifications"
          >
            <Bell className="w-4 h-4" />
            <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-rose-500 ring-2 ring-[#1a1d2e]" />
          </button>
        </div>
      </div>
    </header>
  )
}
