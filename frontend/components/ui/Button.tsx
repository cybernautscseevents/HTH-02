import React from 'react'
import { Loader2 } from 'lucide-react'

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'danger' | 'ghost' | 'success' | 'outline' | 'secondary' | 'warning'
  size?: 'sm' | 'md' | 'lg'
  isLoading?: boolean
  leftIcon?: React.ReactNode
  rightIcon?: React.ReactNode
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  isLoading = false,
  leftIcon,
  rightIcon,
  className = '',
  disabled,
  ...props
}) => {
  const baseStyles =
    'inline-flex items-center justify-center font-medium rounded-lg transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-[#0f1117] disabled:opacity-50 disabled:cursor-not-allowed select-none'

  const sizeStyles = {
    sm: 'text-xs px-3 py-1.5 gap-1.5',
    md: 'text-sm px-4 py-2 gap-2',
    lg: 'text-base px-5 py-2.5 gap-2.5',
  }

  const variantStyles = {
    primary: 'bg-[#6366f1] hover:bg-[#4f46e5] text-white shadow-sm hover:shadow-indigo-500/20 focus:ring-[#6366f1]',
    danger: 'bg-[#ef4444] hover:bg-[#dc2626] text-white shadow-sm hover:shadow-red-500/20 focus:ring-[#ef4444]',
    success: 'bg-[#10b981] hover:bg-[#059669] text-white shadow-sm hover:shadow-emerald-500/20 focus:ring-[#10b981]',
    warning: 'bg-amber-500 hover:bg-amber-600 text-white shadow-sm hover:shadow-amber-500/20 focus:ring-amber-500',
    ghost: 'bg-transparent hover:bg-[#2d3148]/60 text-slate-300 hover:text-white focus:ring-slate-500',
    outline: 'bg-transparent border border-[#2d3148] hover:border-slate-500 text-slate-200 hover:text-white hover:bg-[#1a1d2e] focus:ring-indigo-500',
    secondary: 'bg-[#2d3148] hover:bg-[#3b4263] text-slate-100 focus:ring-slate-400',
  }

  return (
    <button
      className={`${baseStyles} ${sizeStyles[size]} ${variantStyles[variant]} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? <Loader2 className="w-4 h-4 animate-spin shrink-0" /> : leftIcon}
      {children}
      {!isLoading && rightIcon}
    </button>
  )
}
