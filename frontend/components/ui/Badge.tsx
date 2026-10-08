import React from 'react'
import type { EvaluationStatus, NormStatus, Outcome, Severity, SIR } from '@/types/stewardship'

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
  const sizes = {
    sm: 'px-2 py-0.5 text-[10px]',
    md: 'px-2.5 py-1 text-[11px]',
  }
  const styles = (value: string) => {
    switch (value.toUpperCase()) {
      case 'HIGH':
      case 'FLAG':
      case 'FLAGGED':
      case 'NO_MATCH':
      case 'R':
        return 'border-[#D9A4A4] bg-[#FDF2F2] text-[#8B1A1A]'
      case 'MODERATE':
      case 'CANNOT_ASSESS':
      case 'AMBIGUOUS':
      case 'I':
      case 'SDD':
        return 'border-[#E8D5A7] bg-[#FFF9EB] text-[#8B5E00]'
      case 'LOW':
      case 'INFO':
        return 'border-[#B9C9E8] bg-[#F2F6FD] text-[#294F85]'
      case 'PASS':
      case 'OK':
      case 'ACCEPTED':
      case 'CONFIRMED':
      case 'S':
        return 'border-[#A9CFB7] bg-[#F0FBF4] text-[#1A6B3C]'
      case 'INCOMPLETE':
        return 'border-[#E9BE91] bg-[#FFF5EB] text-[#934B13]'
      case 'PHARMACIST':
        return 'border-[#C7C3E8] bg-[#F4F2FC] text-[#3730A3]'
      case 'DOCTOR':
        return 'border-[#B9C9E8] bg-[#F2F6FD] text-[#294F85]'
      default:
        return 'border-[#E2E1DC] bg-[#F4F3EF] text-[#6B6A65]'
    }
  }

  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border font-medium capitalize ${sizes[size]} ${styles(variant)} ${className}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-75" />
      {children}
    </span>
  )
}
