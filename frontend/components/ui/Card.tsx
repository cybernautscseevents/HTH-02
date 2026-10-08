import React from 'react'

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  title?: string
  subtitle?: string
  action?: React.ReactNode
  noPadding?: boolean
}

export const Card: React.FC<CardProps> = ({
  title,
  subtitle,
  action,
  children,
  noPadding = false,
  className = '',
  ...props
}) => (
  <section
    className={`relative overflow-hidden rounded-[8px] border border-[#E2E1DC] bg-white shadow-[0_1px_3px_rgba(0,0,0,0.06)] ${className}`}
    {...props}
  >
    {(title || subtitle || action) && (
      <div className="flex items-center justify-between gap-4 border-b border-[#E2E1DC] px-5 py-4">
        <div>
          {title && <h3 className="text-sm font-medium text-[#1A1A1A]">{title}</h3>}
          {subtitle && <p className="mt-0.5 text-xs text-[#6B6A65]">{subtitle}</p>}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
    )}
    <div className={noPadding ? '' : 'p-5'}>{children}</div>
  </section>
)
