import React from 'react'
import type {
  EvaluationStatus,
  NormStatus,
  Outcome,
  Severity,
  SIR,
} from '@/types/stewardship'

export type BadgeVariant =
  | Severity
  | Outcome
  | EvaluationStatus
  | NormStatus
  | SIR
  | 'pharmacist'
  | 'doctor'
  | 'default'
  | 'info'

interface BadgeProps {
  variant?: BadgeVariant | string
  children: React.ReactNode
  size?: 'sm' | 'md'
  className?: string
}

export const Badge: React.FC<BadgeProps> = ({
  variant = 'default',
  children,
  size = 'md',
  className = '',
}) => {
  const sizeStyles = {
    sm: 'text-[11px] px-2 py-0.5 font-medium',
    md: 'text-xs px-2.5 py-1 font-medium',
  }

  const getVariantStyles = (v: string): string => {
    switch (v.toUpperCase()) {
      // Severity
      case 'HIGH':
        return 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
      case 'MODERATE':
        return 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
      case 'LOW':
        return 'bg-sky-500/15 text-sky-400 border border-sky-500/30'
      case 'INFO':
        return 'bg-indigo-500/15 text-indigo-400 border border-indigo-500/30'
      // Outcome / EvaluationStatus
      case 'FLAG':
      case 'FLAGGED':
        return 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
      case 'PASS':
      case 'OK':
        return 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
      case 'CANNOT_ASSESS':
        return 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
      case 'INCOMPLETE':
        return 'bg-orange-500/15 text-orange-400 border border-orange-500/30'
      // NormStatus
      case 'ACCEPTED':
      case 'CONFIRMED':
        return 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
      case 'AMBIGUOUS':
        return 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
      case 'NO_MATCH':
        return 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
      // SIR
      case 'S':
        return 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
      case 'I':
      case 'SDD':
        return 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
      case 'R':
        return 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
      // Roles
      case 'PHARMACIST':
        return 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30'
      case 'DOCTOR':
        return 'bg-sky-500/15 text-sky-400 border border-sky-500/30'
      default:
        return 'bg-slate-800 text-slate-300 border border-slate-700'
    }
  }

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full capitalize whitespace-nowrap ${sizeStyles[size]} ${getVariantStyles(
        variant
      )} ${className}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current opacity-80" />
      {children}
    </span>
  )
}
