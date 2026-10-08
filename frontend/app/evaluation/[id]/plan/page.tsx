'use client'

import React, { use, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, CheckCircle2, Download, Loader2, Printer } from 'lucide-react'
import { getEpisode, getEvaluation, getEvaluationReviews, getLatestTreatmentPlan, signTreatmentPlan } from '@/lib/api'
import type { DrugOrder, Episode, EvaluationReport, Finding, MedicationDisposition, PlanItemRequest, Review, Route, TreatmentPlan } from '@/types/stewardship'
import { WorkflowStepper } from '@/components/stewardship/WorkflowStepper'
import { useSession } from '@/lib/auth'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'

const DISPOSITIONS: { value: MedicationDisposition; label: string }[] = [
  { value: 'CONTINUE', label: 'Continue unchanged' },
  { value: 'MODIFY', label: 'Change regimen' },
  { value: 'SWITCH', label: 'Switch antibiotic' },
  { value: 'STOP', label: 'Stop antibiotic' },
  { value: 'REQUEST_INFO', label: 'Request information' },
  { value: 'ESCALATE', label: 'Escalate' },
]

type Draft = PlanItemRequest

export default function TreatmentPlanPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const { user } = useSession()
  const [episode, setEpisode] = useState<Episode | null>(null)
  const [evaluation, setEvaluation] = useState<EvaluationReport | null>(null)
  const [reviews, setReviews] = useState<Review[]>([])
  const [plan, setPlan] = useState<TreatmentPlan | null>(null)
  const [supersedesId, setSupersedesId] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [attested, setAttested] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const idempotencyKey = useRef(crypto.randomUUID())

  useEffect(() => {
    Promise.all([getEvaluation(id), getLatestTreatmentPlan(id), getEvaluationReviews(id)])
      .then(async ([report, existing, recordedReviews]) => {
        const ep = await getEpisode(report.episode_id)
        setEvaluation(report)
        setEpisode(ep)
        setReviews(recordedReviews)
        setPlan(existing)
        const orders = treatmentPlanOrders(ep, report)
        setDrafts(Object.fromEntries(orders.map((order) => [order.id, initialDraft(order)])))
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Could not load the treatment plan.'))
      .finally(() => setLoading(false))
  }, [id])

  const orders = useMemo(
    () => (episode && evaluation ? treatmentPlanOrders(episode, evaluation) : []),
    [episode, evaluation]
  )
  const update = (orderId: string, patch: Partial<Draft>) => setDrafts((current) => ({ ...current, [orderId]: { ...current[orderId], ...patch } }))

  const sign = async () => {
    if (!evaluation || !user) return
    setSaving(true)
    setError(null)
    try {
      const signed = await signTreatmentPlan(evaluation.id, {
        phase: evaluation.trigger === 'TIMEOUT_DUE' ? 'ANTIBIOTIC_TIMEOUT_48H' : 'INITIAL',
        items: orders.map((order) => drafts[order.id]),
        reviewer: user.name,
        reviewer_role: user.role === 'pharmacist' ? 'PHARMACIST' : 'PHYSICIAN',
        idempotency_key: idempotencyKey.current,
        supersedes_id: supersedesId,
      })
      setPlan(signed)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not sign the plan.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="flex justify-center py-24"><Loader2 className="h-7 w-7 animate-spin text-[#3730A3]" /></div>
  if (!episode || !evaluation) return <div className="rounded-md border border-[#D9A4A4] bg-[#FDF2F2] p-4 text-[#8B1A1A]">{error ?? 'Evaluation not found.'}</div>

  return (
    <div className="space-y-6 animate-fade-in print:max-w-none">
      <header className="border-b border-[#E2E1DC] pb-4"><p className="text-xs font-medium uppercase tracking-wider text-[#6B6A65]">Pharmacist sign-off</p><h1 className="mt-1 text-2xl font-medium text-[#1A1A1A]">Final antibiotic treatment plan</h1><p className="mt-1 text-sm text-[#6B6A65]">Reconcile every antibiotic into one structured, auditable plan.</p></header>
      <WorkflowStepper current={5} links={{ 1: '/upload', 3: `/evaluation/${evaluation.id}`, 4: `/evaluation/${evaluation.id}` }} back={{ href: `/evaluation/${evaluation.id}`, label: 'Back to findings' }} />
      {plan ? <SignedPlan plan={plan} onRevise={() => { setSupersedesId(plan.id); setPlan(null); setAttested(false); idempotencyKey.current = crypto.randomUUID() }} /> : (
        <>
          <div className="rounded-md border border-[#E8D5A7] bg-[#FFF9EB] p-4 text-sm text-[#6B6A65]"><strong className="text-[#8B5E00]">Clinical responsibility remains with the signer.</strong> RxGuard validates completeness and consistency but does not apply changes to the prescribing system.</div>
          <section className="space-y-3">
            {orders.map((order) => (
              <PlanOrderEditor
                key={order.id}
                order={order}
                draft={drafts[order.id]}
                findings={findingsForOrder(evaluation.findings, order)}
                reviews={reviews}
                update={(patch) => update(order.id, patch)}
              />
            ))}
          </section>
          {error && <div className="rounded-md border border-[#D9A4A4] bg-[#FDF2F2] p-3 text-sm text-[#8B1A1A]">{error}</div>}
          <Card title="Sign-off" subtitle="The signed structured regimen is immutable and becomes the source of truth for this review.">
            <label className="flex items-start gap-3 text-sm text-[#1A1A1A]"><input type="checkbox" checked={attested} onChange={(event) => setAttested(event.target.checked)} className="mt-1" /><span>I have reviewed every antibiotic disposition and confirm that the structured plan reflects my intended clinical action.</span></label>
            <div className="mt-4 flex flex-wrap gap-2"><Button disabled={!attested || !orders.length} isLoading={saving} onClick={sign}>Sign final plan</Button><Link href={`/evaluation/${evaluation.id}`}><Button variant="outline">Back to findings</Button></Link></div>
          </Card>
        </>
      )}
    </div>
  )
}

function treatmentPlanOrders(episode: Episode, evaluation: EvaluationReport): DrugOrder[] {
  const evaluatedOrderIds = new Set(
    evaluation.findings.flatMap((finding) =>
      finding.order_id && finding.rule_id !== 'R0_IDENTIFIED' ? [finding.order_id] : []
    )
  )
  return episode.orders.filter((order) => order.generic && evaluatedOrderIds.has(order.id))
}

function findingsForOrder(findings: Finding[], order: DrugOrder): Finding[] {
  const generic = order.generic?.toLowerCase()
  return findings.filter((finding) => {
    if (finding.outcome === 'PASS') return false
    if (finding.order_id === order.id) return true
    return Boolean(
      generic &&
      finding.rule_id.startsWith('DDI_INTERACTION:') &&
      finding.rule_id.toLowerCase().includes(generic)
    )
  })
}

function reviewForFinding(reviews: Review[], finding: Finding): Review | undefined {
  return [...reviews].reverse().find(
    (review) =>
      review.finding_rule_id === finding.rule_id &&
      (review.order_id ?? null) === (finding.order_id ?? null)
  )
}

function reviewLabel(action: Review['action']): string {
  return {
    ACCEPT: 'Agreed',
    MODIFY: 'Modified',
    REMOVE: 'Removed',
    OVERRIDE: 'Overridden',
    ESCALATE: 'Escalated',
  }[action]
}

function friendlyRule(ruleId: string): string {
  if (ruleId.startsWith('DDI_INTERACTION:')) return 'Drug interaction'
  return ruleId.replaceAll('_', ' ')
}

function initialDraft(order: DrugOrder): Draft {
  return {
    source_order_id: order.id,
    disposition: 'CONTINUE',
    final_regimen: {
      generic: order.generic ?? '',
      dose_mg: order.dose_mg ?? 0,
      freq_per_day: order.freq_per_day ?? 0,
      route: order.route ?? 'PO',
      total_duration_days: order.duration_days ?? 0,
      course_started_at: order.started_at,
    },
    reason_code: null,
    rationale: null,
  }
}

function PlanOrderEditor({
  order,
  draft,
  findings,
  reviews,
  update,
}: {
  order: DrugOrder
  draft: Draft
  findings: Finding[]
  reviews: Review[]
  update: (patch: Partial<Draft>) => void
}) {
  if (!draft) return null
  const resolved = ['CONTINUE', 'MODIFY', 'SWITCH'].includes(draft.disposition)
  const reviewedCount = findings.filter((finding) => reviewForFinding(reviews, finding)).length
  const regimen = draft.final_regimen
  const setRegimen = (patch: Partial<NonNullable<Draft['final_regimen']>>) => update({ final_regimen: { ...(regimen ?? initialDraft(order).final_regimen!), ...patch } })
  const selectDisposition = (disposition: MedicationDisposition) => update({
    disposition,
    final_regimen: ['CONTINUE', 'MODIFY', 'SWITCH'].includes(disposition) ? (regimen ?? initialDraft(order).final_regimen) : null,
    reason_code: disposition === 'CONTINUE' ? null : draft.reason_code,
    rationale: disposition === 'CONTINUE' ? null : draft.rationale,
  })
  return (
    <Card
      title={order.generic ?? order.raw_text}
      subtitle={`Original: ${formatOrder(order)}`}
      action={findings.length > 0 ? <span className="rounded-full border border-[#E8D5A7] bg-[#FFF9EB] px-2 py-1 text-xs font-medium text-[#8B5E00]">{reviewedCount}/{findings.length} reviewed</span> : undefined}
    >
      {findings.length > 0 && (
        <details className="mb-3 rounded-md border border-[#E2E1DC] bg-[#FAFAF8] text-xs">
          <summary className="cursor-pointer px-3 py-2 font-medium text-[#4A4945]">
            Review context · {findings.length} {findings.length === 1 ? 'finding' : 'findings'}
          </summary>
          <div className="space-y-2 border-t border-[#E2E1DC] px-3 py-2">
            {findings.map((finding) => {
              const review = reviewForFinding(reviews, finding)
              return (
                <div key={`${finding.rule_id}:${finding.order_id ?? ''}`} className="grid gap-1 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
                  <div>
                    <span className={`mr-2 font-medium ${finding.outcome === 'FLAG' ? 'text-[#8B1A1A]' : 'text-[#8B5E00]'}`}>{friendlyRule(finding.rule_id)}</span>
                    <span className="text-[#6B6A65]">{finding.message}</span>
                  </div>
                  <span className="whitespace-nowrap text-[#6B6A65]">
                    {review ? `${reviewLabel(review.action)}${review.reason_code ? ` · ${review.reason_code.replaceAll('_', ' ').toLowerCase()}` : ''}` : 'Not reviewed'}
                  </span>
                  {review?.note && <p className="text-[#6B6A65] sm:col-span-2">Note: {review.note}</p>}
                </div>
              )
            })}
          </div>
        </details>
      )}
      <label className="block max-w-sm text-xs font-medium text-[#4A4945]">
        Final decision
        <select
          value={draft.disposition}
          onChange={(event) => selectDisposition(event.target.value as MedicationDisposition)}
          className="mt-1 w-full rounded-md border border-[#C8C7C0] bg-white px-3 py-2 text-sm text-[#1A1A1A]"
        >
          {DISPOSITIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      {draft.disposition === 'CONTINUE' && regimen && <p className="mt-3 rounded-md bg-[#F4F3EF] px-3 py-2 text-xs text-[#4A4945]">Final regimen unchanged: {formatRegimen(regimen)}</p>}
      {resolved && draft.disposition !== 'CONTINUE' && regimen && <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5"><Field label="Generic" value={regimen.generic} disabled={draft.disposition !== 'SWITCH'} onChange={(value) => setRegimen({ generic: value })} /><NumberField label="Dose (mg)" value={regimen.dose_mg} onChange={(value) => setRegimen({ dose_mg: value })} /><NumberField label="Times per day" value={regimen.freq_per_day} onChange={(value) => setRegimen({ freq_per_day: value })} /><label className="text-xs text-[#6B6A65]">Route<select value={regimen.route} onChange={(event) => setRegimen({ route: event.target.value as Route })} className="mt-1 w-full rounded-md border border-[#C8C7C0] bg-white px-3 py-2 text-sm"><option>PO</option><option>IV</option><option>IM</option></select></label><NumberField label="Total days" value={regimen.total_duration_days} onChange={(value) => setRegimen({ total_duration_days: value })} /></div>}
      {draft.disposition === 'REQUEST_INFO' && <div className="mt-4"><Field label="Information required (comma separated)" value={(draft.requested_inputs ?? []).join(', ')} onChange={(value) => update({ requested_inputs: value.split(',').map((item) => item.trim()).filter(Boolean) })} /></div>}
      {draft.disposition === 'ESCALATE' && <div className="mt-4 grid gap-3 sm:grid-cols-2"><Field label="Escalate to" value={draft.escalation_destination ?? ''} onChange={(value) => update({ escalation_destination: value })} /><label className="text-xs text-[#6B6A65]">Urgency<select value={draft.escalation_urgency ?? 'ROUTINE'} onChange={(event) => update({ escalation_urgency: event.target.value as 'ROUTINE' | 'URGENT' })} className="mt-1 w-full rounded-md border border-[#C8C7C0] bg-white px-3 py-2 text-sm"><option value="ROUTINE">Routine</option><option value="URGENT">Urgent</option></select></label></div>}
      {draft.disposition !== 'CONTINUE' && <div className="mt-4 grid gap-3 sm:grid-cols-2"><Field label="Reason code" value={draft.reason_code ?? ''} onChange={(value) => update({ reason_code: value })} /><Field label="Clinical rationale" value={draft.rationale ?? ''} onChange={(value) => update({ rationale: value })} /></div>}
    </Card>
  )
}

function SignedPlan({ plan, onRevise }: { plan: TreatmentPlan; onRevise: () => void }) {
  const download = () => {
    const blob = new Blob([JSON.stringify(plan, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${plan.id}.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-5">
      <div className={`rounded-[8px] border p-4 ${plan.status === 'READY' ? 'border-[#A9CFB7] bg-[#F0FBF4]' : 'border-[#E8D5A7] bg-[#FFF9EB]'}`}>
        <div className="flex items-start gap-3">
          {plan.status === 'READY' ? <CheckCircle2 className="h-5 w-5 text-[#1A6B3C]" /> : <AlertTriangle className="h-5 w-5 text-[#8B5E00]" />}
          <div>
            <h2 className="font-medium text-[#1A1A1A]">{plan.status === 'READY' ? 'Signed treatment plan' : 'Signed review · action required'}</h2>
            <p className="mt-1 text-xs text-[#6B6A65]">{plan.reviewer} · {new Date(plan.signed_at).toLocaleString('en-IN')} · Version {plan.version}</p>
          </div>
        </div>
      </div>

      <section className="space-y-3">
        <div>
          <h2 className="text-base font-medium text-[#1A1A1A]">Complete final medication list</h2>
          <p className="mt-1 text-xs text-[#6B6A65]">Signed antibiotic decisions plus recognized non-antibiotics carried forward unchanged.</p>
        </div>
        {plan.items.map((item) => (
          <Card
            key={item.source_order_id}
            title={item.final_regimen?.generic ?? item.before.generic}
            action={<span className="rounded border border-[#E2E1DC] bg-[#F4F3EF] px-2 py-1 text-xs font-medium">ANTIBIOTIC · {item.disposition.replace('_', ' ')}</span>}
          >
            <p className="text-sm text-[#6B6A65]">Before: {formatRegimen(item.before)}</p>
            {item.final_regimen && <p className="mt-2 text-sm font-medium text-[#1A1A1A]">Final: {formatRegimen(item.final_regimen)}</p>}
            {item.disposition === 'STOP' && <p className="mt-2 text-sm font-medium text-[#8B1A1A]">Final: stopped and excluded from active medicines.</p>}
            {item.rationale && <p className="mt-2 text-xs text-[#6B6A65]">Rationale: {item.rationale}</p>}
            {item.requested_inputs.length > 0 && <p className="mt-2 text-xs text-[#8B5E00]">Required: {item.requested_inputs.join(', ')}</p>}
          </Card>
        ))}
        {plan.other_medications.map((medication) => (
          <Card
            key={medication.source_order_id ?? medication.generic}
            title={medication.generic}
            action={<span className="rounded border border-[#A9CFB7] bg-[#F0FBF4] px-2 py-1 text-xs font-medium text-[#1A6B3C]">NON-ANTIBIOTIC · CONTINUE UNCHANGED</span>}
          >
            <p className="text-sm font-medium text-[#1A1A1A]">Final: {formatRegimen(medication)}</p>
          </Card>
        ))}
      </section>

      <Card title="Plan summary" subtitle={plan.narrative.disclaimer}>
        <p className="text-sm leading-relaxed text-[#1A1A1A]">{plan.narrative.text}</p>
        <p className="mt-2 font-mono text-xs text-[#6B6A65]">{plan.narrative.source} · {plan.narrative.generator}</p>
      </Card>
      <div className="flex flex-wrap gap-2 print:hidden">
        <Button leftIcon={<Download className="h-4 w-4" />} onClick={download}>Export JSON</Button>
        <Button variant="outline" leftIcon={<Printer className="h-4 w-4" />} onClick={() => window.print()}>Print plan</Button>
        <Link href="/audit"><Button variant="ghost">View audit log</Button></Link>
        <Button variant="ghost" onClick={onRevise}>Create revised plan</Button>
      </div>
    </div>
  )
}

function Field({ label, value, onChange, disabled = false }: { label: string; value: string; onChange: (value: string) => void; disabled?: boolean }) { return <label className="text-xs text-[#6B6A65]">{label}<input value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded-md border border-[#C8C7C0] bg-white px-3 py-2 text-sm disabled:bg-[#F4F3EF]" /></label> }
function NumberField({ label, value, onChange, disabled = false }: { label: string; value: number; onChange: (value: number) => void; disabled?: boolean }) { return <label className="text-xs text-[#6B6A65]">{label}<input type="number" min="0" step="any" value={value} disabled={disabled} onChange={(event) => onChange(Number(event.target.value))} className="mt-1 w-full rounded-md border border-[#C8C7C0] bg-white px-3 py-2 text-sm disabled:bg-[#F4F3EF]" /></label> }
function formatOrder(order: DrugOrder) { return `${order.dose_mg ?? '—'} mg · ${order.route ?? '—'} · ${order.freq_per_day ?? '—'} times/day · ${order.duration_days ?? '—'} days` }
function formatRegimen(regimen: { generic: string; dose_mg?: number | null; route?: Route | null; freq_per_day?: number | null; total_duration_days?: number | null }) { return `${regimen.generic} · ${regimen.dose_mg ?? '—'} mg · ${regimen.route ?? '—'} · ${regimen.freq_per_day ?? '—'} times/day · ${regimen.total_duration_days ?? '—'} days total` }
