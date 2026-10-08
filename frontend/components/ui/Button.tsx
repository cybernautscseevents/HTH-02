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
  const base =
    'inline-flex items-center justify-center rounded-md font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-[#3730A3]/30 focus:ring-offset-2 focus:ring-offset-[#FAFAF8] disabled:cursor-not-allowed disabled:opacity-45'
  const sizes = {
    sm: 'gap-1.5 px-3 py-1.5 text-xs',
    md: 'gap-2 px-4 py-2 text-sm',
    lg: 'gap-2.5 px-5 py-2.5 text-sm',
  }
  const variants = {
    primary: 'bg-[#1A1A1A] text-white hover:bg-[#2D2D2D]',
    danger: 'border border-[#D9A4A4] bg-[#FDF2F2] text-[#8B1A1A] hover:bg-[#F8E4E4]',
    success: 'border border-[#A9CFB7] bg-[#F0FBF4] text-[#1A6B3C] hover:bg-[#E3F5E9]',
    warning: 'border border-[#E8D5A7] bg-[#FFF9EB] text-[#8B5E00] hover:bg-[#FFF2D1]',
    ghost: 'bg-transparent text-[#6B6A65] hover:bg-[#F4F3EF] hover:text-[#1A1A1A]',
    outline: 'border border-[#C8C7C0] bg-white text-[#1A1A1A] hover:bg-[#F4F3EF]',
    secondary: 'border border-[#E2E1DC] bg-[#F4F3EF] text-[#1A1A1A] hover:bg-[#EEEEE9]',
  }

  return (
    <button
      className={`${base} ${sizes[size]} ${variants[variant]} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? <Loader2 className="h-4 w-4 shrink-0 animate-spin" /> : leftIcon}
      {children}
      {!isLoading && rightIcon}
    </button>
  )
}
