import React from 'react'
import { Check } from 'lucide-react'

const STEPS = [
  { title: 'Prescription', detail: 'Upload or type' },
  { title: 'Clinical context', detail: 'Patient and culture' },
  { title: 'Rule analysis', detail: 'NCDC evaluation' },
  { title: 'Finding review', detail: 'Record decisions' },
  { title: 'Final plan', detail: 'Reconcile and sign' },
]

export function WorkflowStepper({ current }: { current: 1 | 2 | 3 | 4 | 5 }) {
  const active = STEPS[current - 1]
  return (
    <nav aria-label="Evaluation workflow" className="rounded-[8px] border border-[#E2E1DC] bg-white px-4 py-3 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      <div className="sm:hidden">
        <div className="flex items-center justify-between"><span className="text-xs font-medium text-[#1A1A1A]">Step {current} of 5 · {active.title}</span><span className="text-xs text-[#6B6A65]">{active.detail}</span></div>
        <div className="mt-2 grid grid-cols-5 gap-1">{STEPS.map((step, index) => <span key={step.title} className={`h-1.5 rounded-full ${index < current ? 'bg-[#1A1A1A]' : 'bg-[#E2E1DC]'}`} />)}</div>
      </div>
      <ol className="hidden grid-cols-5 gap-0 sm:grid">
        {STEPS.map((step, index) => {
          const number = index + 1
          const complete = number < current
          const selected = number === current
          return (
            <li key={step.title} className="relative flex items-center gap-2 pr-3">
              {index < STEPS.length - 1 && <span className="absolute left-7 right-0 top-3 h-px bg-[#E2E1DC]" />}
              <span className={`relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold ${complete ? 'border-[#1A6B3C] bg-[#1A6B3C] text-white' : selected ? 'border-[#1A1A1A] bg-[#1A1A1A] text-white' : 'border-[#C8C7C0] bg-white text-[#6B6A65]'}`}>{complete ? <Check className="h-3.5 w-3.5" /> : number}</span>
              <span className="relative z-10 min-w-0 bg-white pr-2"><span className={`block truncate text-xs font-medium ${selected ? 'text-[#1A1A1A]' : 'text-[#6B6A65]'}`}>{step.title}</span><span className="hidden text-xs text-[#8B8982] lg:block">{step.detail}</span></span>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
