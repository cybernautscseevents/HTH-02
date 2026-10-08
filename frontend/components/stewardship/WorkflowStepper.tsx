import React from 'react'
import { Check } from 'lucide-react'

const STEPS = [
  { title: 'Prescription', detail: 'Upload or type' },
  { title: 'Clinical context', detail: 'Patient and culture' },
  { title: 'Rule analysis', detail: 'NCDC evaluation' },
  { title: 'Review', detail: 'Decide and audit' },
]

export function WorkflowStepper({ current }: { current: 1 | 2 | 3 | 4 }) {
  return (
    <nav aria-label="Evaluation workflow" className="rounded-[8px] border border-[#E2E1DC] bg-white px-4 py-3 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <ol className="grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-0">
        {STEPS.map((step, index) => {
          const number = index + 1
          const complete = number < current
          const active = number === current
          return (
            <li key={step.title} className="relative flex items-center gap-2.5 sm:pr-5">
              {index < STEPS.length - 1 && (
                <span className="absolute left-7 right-0 top-3 hidden h-px bg-[#E2E1DC] sm:block" />
              )}
              <span
                className={`relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[10px] font-semibold ${
                  complete
                    ? 'border-[#1A6B3C] bg-[#1A6B3C] text-white'
                    : active
                    ? 'border-[#1A1A1A] bg-[#1A1A1A] text-white'
                    : 'border-[#C8C7C0] bg-white text-[#6B6A65]'
                }`}
              >
                {complete ? <Check className="h-3.5 w-3.5" /> : number}
              </span>
              <span className="relative z-10 min-w-0 bg-white pr-2">
                <span className={`block truncate text-xs font-medium ${active ? 'text-[#1A1A1A]' : 'text-[#6B6A65]'}`}>
                  {step.title}
                </span>
                <span className="hidden text-[10px] text-[#8B8982] lg:block">{step.detail}</span>
              </span>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
