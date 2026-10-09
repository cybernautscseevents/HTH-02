'use client'

import React, { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { Activity, AlertTriangle, ArrowUpRight, CheckCircle2, ClipboardList, Clock, Loader2, RefreshCw, Stethoscope, XCircle } from 'lucide-react'
import { getAuditLog, getStats } from '@/lib/api'
import { useSession } from '@/lib/auth'
import { getPrescriberReviews, type PrescriberReview } from '@/lib/prescriberReview'
import type { AuditEntry, AwareTier, DashboardStats, EvaluationStatus, ReviewAction } from '@/types/stewardship'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'

const STATUS_ICON: Record<EvaluationStatus, React.ReactNode> = {
  FLAGGED: <AlertTriangle className="h-4 w-4 text-[#8B1A1A]" />,
  OK: <CheckCircle2 className="h-4 w-4 text-[#1A6B3C]" />,
  INCOMPLETE: <XCircle className="h-4 w-4 text-[#8B5E00]" />,
}

const AWARE_BARS: { tier: AwareTier; label: string; color: string }[] = [
  { tier: 'ACCESS', label: 'Access', color: '#1A6B3C' },
  { tier: 'WATCH', label: 'Watch', color: '#B7791F' },
  { tier: 'RESERVE', label: 'Reserve', color: '#8B1A1A' },
  { tier: 'NOT_CLASSIFIED', label: 'Not classified', color: '#A8A79F' },
]

const DECISIONS: { action: ReviewAction; label: string }[] = [
  { action: 'ACCEPT', label: 'Accepted' },
  { action: 'MODIFY', label: 'Modified' },
  { action: 'REMOVE', label: 'Removed' },
  { action: 'OVERRIDE', label: 'Overridden' },
  { action: 'ESCALATE', label: 'Escalated' },
]

// UN General Assembly Political Declaration on AMR (2024): at least 70% of human antibiotic use
// from the WHO Access group by 2030. The target is set on consumption; here it is read on orders.
const ACCESS_TARGET = 70

function ImpactPanel({ stats }: { stats: DashboardStats }) {
  const aware = stats.aware_order_counts ?? {}
  const orders = AWARE_BARS.reduce((n, { tier }) => n + (aware[tier] ?? 0), 0)
  const accessShare = orders ? Math.round((100 * (aware.ACCESS ?? 0)) / orders) : 0
  const decisions = stats.decision_counts ?? {}
  const decided = DECISIONS.reduce((n, { action }) => n + (decisions[action] ?? 0), 0)

  return (
    <section className="grid gap-3 lg:grid-cols-3">
      <div className="rounded-[8px] border border-[#E2E1DC] bg-white p-4 lg:col-span-2">
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-sm font-medium text-[#1A1A1A]">Antibiotic orders by WHO AWaRe tier</p>
          <p className="text-xs text-[#6B6A65]">{orders} order{orders === 1 ? '' : 's'}</p>
        </div>
        {orders === 0 ? (
          <p className="mt-4 text-xs text-[#6B6A65]">No antibiotic orders evaluated yet.</p>
        ) : (
          <>
            <div className="relative mt-4">
              <div className="flex h-3 overflow-hidden rounded-full bg-[#F4F3EF]">
                {AWARE_BARS.map(({ tier, color }) =>
                  aware[tier] ? (
                    <div key={tier} style={{ width: `${(100 * aware[tier]!) / orders}%`, background: color }} />
                  ) : null
                )}
              </div>
              <div className="absolute -top-1 h-5 w-px bg-[#1A1A1A]" style={{ left: `${ACCESS_TARGET}%` }} title={`${ACCESS_TARGET}% Access target`} />
            </div>
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[#6B6A65]">
              {AWARE_BARS.map(({ tier, label, color }) =>
                aware[tier] ? (
                  <span key={tier} className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full" style={{ background: color }} />
                    {label} <span className="tabular-nums text-[#1A1A1A]">{aware[tier]}</span>
                  </span>
                ) : null
              )}
            </div>
            <p className="mt-3 text-xs text-[#6B6A65]">
              <span className={`font-medium ${accessShare >= ACCESS_TARGET ? 'text-[#1A6B3C]' : 'text-[#8B5E00]'}`}>
                {accessShare}% Access
              </span>{' '}
              against the {ACCESS_TARGET}% target for 2030 (UN General Assembly declaration on AMR, 2024). The target is set on
              consumption; this shows prescribed orders.
            </p>
          </>
        )}
      </div>

      <div className="rounded-[8px] border border-[#E2E1DC] bg-white p-4">
        <p className="text-sm font-medium text-[#1A1A1A]">Stewardship actions</p>
        <dl className="mt-3 space-y-2 text-xs">
          {[
            ['De-escalations suggested from cultures', stats.de_escalation_suggested ?? 0],
            ['IV-to-oral switches suggested at the time-out review', stats.iv_to_oral_suggested ?? 0],
          ].map(([label, value]) => (
            <div key={label} className="flex justify-between gap-3">
              <dt className="text-[#6B6A65]">{label}</dt>
              <dd className="tabular-nums font-medium text-[#1A1A1A]">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-4 text-xs font-medium text-[#6B6A65]">Pharmacist decisions ({decided})</p>
        {decided === 0 ? (
          <p className="mt-2 text-xs text-[#6B6A65]">No decisions recorded yet.</p>
        ) : (
          <dl className="mt-2 space-y-1.5 text-xs">
            {DECISIONS.filter(({ action }) => decisions[action]).map(({ action, label }) => (
              <div key={action} className="flex justify-between gap-3">
                <dt className="text-[#6B6A65]">{label}</dt>
                <dd className="tabular-nums text-[#1A1A1A]">{decisions[action]}</dd>
              </div>
            ))}
          </dl>
        )}
        <p className="mt-3 text-[11px] text-[#6B6A65]">The engine suggests; every change is a pharmacist decision.</p>
      </div>
    </section>
  )
}

interface SignedPlanRow {
  planId: string
  evaluationId: string
  episodeId: string
  reviewer: string
  signedAt: string
  version: number
}

/** The latest pharmacist-signed plan per evaluation, newest first. */
function pharmacistPlans(entries: AuditEntry[]): SignedPlanRow[] {
  const latest = new Map<string, SignedPlanRow>()
  for (const entry of entries) {
    if (entry.entity !== 'treatment_plan' || !entry.action.startsWith('treatment_plan.')) continue
    const p = entry.payload as { id: string; evaluation_id: string; episode_id: string; reviewer: string; reviewer_role: string; signed_at: string; version: number }
    if (p.reviewer_role === 'PHYSICIAN') continue
    const row = { planId: p.id, evaluationId: p.evaluation_id, episodeId: p.episode_id, reviewer: p.reviewer, signedAt: p.signed_at, version: p.version }
    const current = latest.get(row.evaluationId)
    if (!current || Date.parse(row.signedAt) > Date.parse(current.signedAt)) latest.set(row.evaluationId, row)
  }
  return [...latest.values()].sort((a, b) => Date.parse(b.signedAt) - Date.parse(a.signedAt))
}

function SignedPlansCard({ plans, reviews, patients, forDoctor }: { plans: SignedPlanRow[]; reviews: Record<string, PrescriberReview>; patients: Map<string, string>; forDoctor: boolean }) {
  const awaiting = plans.filter((plan) => !reviews[plan.planId]).length
  return (
    <Card
      title={forDoctor ? 'Plans awaiting your review' : 'Prescriber review of signed plans'}
      subtitle={forDoctor ? 'Final plans signed by pharmacy. Approve them or send them back with a comment.' : 'Where each plan you signed stands with the prescriber.'}
      action={<span className="rounded-full border border-[#9FD3C7] bg-[#E8F6F2] px-2 py-0.5 text-xs font-medium text-[#0F6B5C]">{awaiting} awaiting</span>}
      noPadding
    >
      {plans.length === 0 ? (
        <p className="px-6 py-8 text-center text-xs text-[#6B6A65]">No plans signed by pharmacy yet.</p>
      ) : (
        <div className="divide-y divide-[#E2E1DC]">
          {plans.map((plan) => {
            const review = reviews[plan.planId]
            const status = !review
              ? { label: 'Awaiting review', style: 'border-[#E2E1DC] bg-[#F4F3EF] text-[#6B6A65]' }
              : review.decision === 'APPROVED'
                ? { label: 'Approved', style: 'border-[#9FD3C7] bg-[#E8F6F2] text-[#0F6B5C]' }
                : { label: 'Changes requested', style: 'border-[#E8D5A7] bg-[#FFF9EB] text-[#8B5E00]' }
            return (
              <div key={plan.planId} className="flex flex-col gap-3 px-5 py-4 hover:bg-[#FAFAF8] sm:flex-row sm:items-center">
                <div className="flex min-w-0 flex-1 items-center gap-3">
                  <Stethoscope className="h-4 w-4 shrink-0 text-[#0F6B5C]" />
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-sm font-medium text-[#1A1A1A]">{patients.get(plan.evaluationId) ?? plan.episodeId}</span>
                      <span className={`rounded border px-1.5 py-0.5 text-xs font-medium ${status.style}`}>{status.label}</span>
                    </div>
                    <p className="mt-0.5 truncate text-xs text-[#6B6A65]">Signed by {plan.reviewer} · version {plan.version} · {new Date(plan.signedAt).toLocaleString('en-IN')}</p>
                  </div>
                </div>
                <Link href={`/evaluation/${plan.evaluationId}/plan`}><Button variant="outline" size="sm">{forDoctor && !review ? 'Review plan' : 'Open plan'}</Button></Link>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}

export default function DashboardPage() {
  const { user } = useSession()
  const forDoctor = user?.role === 'doctor'
  const [plans, setPlans] = useState<SignedPlanRow[]>([])
  const [planReviews, setPlanReviews] = useState<Record<string, PrescriberReview>>({})
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setError(null)
      const [nextStats, audit] = await Promise.all([getStats(), getAuditLog().catch(() => [])])
      setStats(nextStats)
      setPlans(pharmacistPlans(audit))
      setPlanReviews(getPrescriberReviews())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load dashboard data.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  if (loading) return <div className="flex justify-center py-24"><Loader2 className="h-7 w-7 animate-spin text-[#3730A3]" /></div>

  const patients = new Map((stats?.recent_evaluations ?? []).map((e) => [e.evaluation_id, e.patient_id]))
  // Evaluations live in backend memory while the audit log persists, so keep only plans that can still be opened.
  const openPlans = plans.filter((plan) => patients.has(plan.evaluationId))

  const metrics = [
    { label: 'Evaluated episodes', value: stats?.total_reviewed ?? 0, icon: ClipboardList, color: 'text-[#3730A3]' },
    { label: 'Flagged', value: stats?.flagged_count ?? 0, icon: AlertTriangle, color: 'text-[#8B1A1A]' },
    { label: 'Decisions pending', value: stats?.pending_review_count ?? 0, icon: Activity, color: 'text-[#8B5E00]' },
    { label: 'High severity', value: stats?.high_severity_count ?? 0, icon: AlertTriangle, color: 'text-[#8B1A1A]' },
    { label: '48-hour reviews', value: stats?.timeout_due_count ?? 0, icon: Clock, color: 'text-[#8B5E00]' },
  ]

  return (
    <div className="space-y-6 animate-fade-in">
      <header className="flex flex-col justify-between gap-3 border-b border-[#E2E1DC] pb-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-[#6B6A65]">{forDoctor ? 'Prescriber workspace' : 'Stewardship pharmacy'}</p>
          <h1 className="mt-1 text-2xl font-medium text-[#1A1A1A]">{forDoctor ? 'Prescriber dashboard' : 'Stewardship review queue'}</h1>
          <p className="mt-1 text-sm text-[#6B6A65]">
            {forDoctor
              ? 'Review the final plans pharmacy has signed, or run a prescription review yourself.'
              : 'Follow prescriptions from intake through deterministic analysis and pharmacist review.'}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" leftIcon={<RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />} onClick={() => { setRefreshing(true); load() }}>Refresh</Button>
          <Link href="/upload"><Button size="sm" leftIcon={<ClipboardList className="h-4 w-4" />}>Start review</Button></Link>
        </div>
      </header>

      {error && <div className="rounded-md border border-[#D9A4A4] bg-[#FDF2F2] px-4 py-3 text-sm text-[#8B1A1A]">{error}</div>}

      {forDoctor && <SignedPlansCard plans={openPlans} reviews={planReviews} patients={patients} forDoctor />}

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {metrics.map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="rounded-[8px] border border-[#E2E1DC] bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,0.04)]">
            <Icon className={`h-4 w-4 ${color}`} />
            <p className="mt-3 text-2xl font-medium tabular-nums text-[#1A1A1A]">{value}</p>
            <p className="mt-0.5 text-xs text-[#6B6A65]">{label}</p>
          </div>
        ))}
      </section>

      {stats && <ImpactPanel stats={stats} />}

      {!forDoctor && <SignedPlansCard plans={openPlans} reviews={planReviews} patients={patients} forDoctor={false} />}

      <Card title="Recent evaluations" subtitle="Latest episodes processed by the rule engine" action={<Link href="/audit" className="flex items-center gap-1 text-xs font-medium text-[#3730A3]">Audit log <ArrowUpRight className="h-3.5 w-3.5" /></Link>} noPadding>
        {(stats?.recent_evaluations.length ?? 0) === 0 ? (
          <div className="px-6 py-12 text-center"><p className="text-sm font-medium text-[#1A1A1A]">No evaluations yet</p><p className="mt-1 text-xs text-[#6B6A65]">Start a review to populate this workspace.</p></div>
        ) : (
          <div className="divide-y divide-[#E2E1DC]">
            {stats?.recent_evaluations.map((evaluation) => (
              <div key={evaluation.evaluation_id} className="flex flex-col gap-3 px-5 py-4 hover:bg-[#FAFAF8] sm:flex-row sm:items-center">
                <div className="flex min-w-0 flex-1 items-center gap-3">
                  {STATUS_ICON[evaluation.status]}
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-sm font-medium text-[#1A1A1A]">{evaluation.patient_id}</span><Badge variant={evaluation.status} size="sm">{evaluation.status}</Badge></div>
                    <p className="mt-0.5 truncate font-mono text-xs text-[#6B6A65]">{evaluation.evaluation_id}</p>
                  </div>
                </div>
                <div className="flex items-center justify-between gap-4 sm:justify-end">
                  <div className="text-right text-xs text-[#6B6A65]">{evaluation.high_count} high · {evaluation.moderate_count} moderate<br />{new Date(evaluation.evaluated_at).toLocaleString('en-IN')}</div>
                  <Link href={`/evaluation/${evaluation.evaluation_id}`}><Button variant="outline" size="sm">Review</Button></Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <section className="grid gap-3 sm:grid-cols-3">
        {[
          { href: '/upload', icon: ClipboardList, title: 'New prescription', detail: 'Upload an image or enter a typed prescription.' },
          { href: '/timeout', icon: Clock, title: '48-hour reviews', detail: `${stats?.timeout_due_count ?? 0} episodes currently due.` },
          { href: '/culture', icon: Activity, title: 'Culture results', detail: 'Review susceptibility data alongside therapy.' },
        ].map(({ href, icon: Icon, title, detail }) => (
          <Link key={href} href={href} className="rounded-[8px] border border-[#E2E1DC] bg-white p-4 transition hover:border-[#C8C7C0] hover:shadow-sm">
            <Icon className="h-4 w-4 text-[#3730A3]" /><p className="mt-3 text-sm font-medium text-[#1A1A1A]">{title}</p><p className="mt-1 text-xs text-[#6B6A65]">{detail}</p>
          </Link>
        ))}
      </section>
    </div>
  )
}
