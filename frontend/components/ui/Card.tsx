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
}) => {
  return (
    <div
      className={`bg-[#1e2235] border border-[#2d3148] rounded-xl shadow-lg relative overflow-hidden ${className}`}
      {...props}
    >
      {(title || subtitle || action) && (
        <div className="px-6 py-4 border-b border-[#2d3148] flex items-center justify-between gap-4">
          <div>
            {title && <h3 className="text-base font-semibold text-slate-100">{title}</h3>}
            {subtitle && <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      )}
      <div className={noPadding ? '' : 'p-6'}>{children}</div>
    </div>
  )
}
