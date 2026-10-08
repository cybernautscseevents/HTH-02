import React from 'react'
import Link from 'next/link'
import { ArrowLeft, Check } from 'lucide-react'

const STEPS = [
  { title: 'Prescription', detail: 'Upload or type' },
  { title: 'Clinical context', detail: 'Patient and culture' },
  { title: 'Rule analysis', detail: 'NCDC evaluation' },
  { title: 'Finding review', detail: 'Record decisions' },
  { title: 'Final plan', detail: 'Reconcile and sign' },
]

type StepNumber = 1 | 2 | 3 | 4 | 5

// `links` maps a step to the page that shows it; a step without a link is not clickable,
// because some steps (such as the clinical context of a saved episode) cannot be reopened.
// `back` is where the Back button goes; without it no Back button is shown.
export function WorkflowStepper({
  current,
  links = {},
  back,
}: {
  current: StepNumber
  links?: Partial<Record<StepNumber, string>>
  back?: { href: string; label: string }
}) {
  const active = STEPS[current - 1]
  return (
    <nav aria-label="Evaluation workflow" className="rounded-[8px] border border-[#E2E1DC] bg-white px-4 py-3 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
      {back && (
        <Link href={back.href} className="mb-3 inline-flex items-center gap-1.5 rounded-md text-xs font-medium text-[#6B6A65] hover:text-[#1A1A1A]">
          <ArrowLeft className="h-3.5 w-3.5" />
          {back.label}
        </Link>
      )}
      <div className="sm:hidden">
        <div className="flex items-center justify-between"><span className="text-xs font-medium text-[#1A1A1A]">Step {current} of 5 · {active.title}</span><span className="text-xs text-[#6B6A65]">{active.detail}</span></div>
        <div className="mt-2 grid grid-cols-5 gap-1">{STEPS.map((step, index) => <span key={step.title} className={`h-1.5 rounded-full ${index < current ? 'bg-[#1A1A1A]' : 'bg-[#E2E1DC]'}`} />)}</div>
      </div>
      <ol className="hidden grid-cols-5 gap-0 sm:grid">
        {STEPS.map((step, index) => {
          const number = (index + 1) as StepNumber
          const complete = number < current
          const selected = number === current
          const href = selected ? undefined : links[number]
          const content = (
            <>
              <span className={`relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold ${complete ? 'border-[#1A6B3C] bg-[#1A6B3C] text-white' : selected ? 'border-[#1A1A1A] bg-[#1A1A1A] text-white' : 'border-[#C8C7C0] bg-white text-[#6B6A65]'}`}>{complete ? <Check className="h-3.5 w-3.5" /> : number}</span>
              <span className="relative z-10 min-w-0 bg-white pr-2"><span className={`block truncate text-xs font-medium ${selected ? 'text-[#1A1A1A]' : href ? 'text-[#6B6A65] group-hover:text-[#1A1A1A] group-hover:underline' : 'text-[#6B6A65]'}`}>{step.title}</span><span className="hidden text-xs text-[#8B8982] lg:block">{step.detail}</span></span>
            </>
          )
          return (
            <li key={step.title} className="relative flex items-center gap-2 pr-3">
              {index < STEPS.length - 1 && <span className="absolute left-7 right-0 top-3 h-px bg-[#E2E1DC]" />}
              {href ? (
                <Link href={href} className="group relative flex min-w-0 items-center gap-2 rounded-md">{content}</Link>
              ) : (
                <span className="relative flex min-w-0 items-center gap-2" aria-current={selected ? 'step' : undefined}>{content}</span>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
