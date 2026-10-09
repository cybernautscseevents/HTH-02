'use client'

import React, { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { use } from 'react'
import { Loader2, RefreshCw } from 'lucide-react'
import {
  evaluateEpisode,
  getEpisode,
  getEvaluation,
  getEvaluationReviews,
  getLatestTreatmentPlan,
  submitReview,
} from '@/lib/api'
import { COMORBIDITY_LABELS } from '@/types/stewardship'
import type {
  Episode,
  EvaluationReport,
  Finding,
  ReasonCode,
  Review,
  ReviewAction,
  TreatmentPlan,
} from '@/types/stewardship'
import { EvaluationBanner } from '@/components/stewardship/EvaluationBanner'
import { FindingCard } from '@/components/stewardship/FindingCard'
import { ReviewPanel } from '@/components/stewardship/ReviewPanel'
import { CulturePanel } from '@/components/stewardship/CulturePanel'
import { NationalSusceptibilityPanel } from '@/components/stewardship/NationalSusceptibilityPanel'
import { WhatIfPanel } from '@/components/stewardship/WhatIfPanel'
import { EvaluationChat } from '@/components/stewardship/EvaluationChat'
import { reviewerLabel, useSession } from '@/lib/auth'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { WorkflowStepper } from '@/components/stewardship/WorkflowStepper'
import { isRetired, reachableLinks, setChain, useChain } from '@/lib/workflow'

type Tab = 'findings' | 'whatif' | 'culture' | 'patient'

// How the syndrome was decided (backend SyndromeView.resolution).
const RESOLUTION_LABEL: Record<string, string> = {
  mapped_from_text: "from the prescriber's diagnosis",
  confirmed_from_diagnosis: "prescriber's diagnosis, confirmed by the reviewer",
  selected: 'selected by the reviewer',
}

export default function EvaluationPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id: evaluationId } = use(params)
  const [episode, setEpisode] = useState<Episode | null>(null)
  const [evaluation, setEvaluation] = useState<EvaluationReport | null>(null)
  const [reviews, setReviews] = useState<Review[]>([])
  const [treatmentPlan, setTreatmentPlan] = useState<TreatmentPlan | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [rerunning, setRerunning] = useState(false)
  const [activeTab, setActiveTab] = useState<Tab>('findings')
  const [patientOpen, setPatientOpen] = useState(false)
  const [retired, setRetired] = useState(false)
  const [chain] = useChain()

  const { user } = useSession()
  const REVIEWER = reviewerLabel(user)

  // An evaluation whose inputs were edited afterwards is never loaded, so none of it is shown or
  // acted on. Another tab can retire it while this one is open.
  useEffect(() => {
    const check = () => {
      if (!isRetired(evaluationId)) return
      setRetired(true)
      setEvaluation(null)
      setEpisode(null)
      setReviews([])
      setTreatmentPlan(null)
      setLoading(false)
    }
    check()
    window.addEventListener('storage', check)
    return () => window.removeEventListener('storage', check)
  }, [evaluationId])

  const loadData = useCallback(async () => {
    if (isRetired(evaluationId)) return
    try {
      const ev = await getEvaluation(evaluationId)
      const [ep, recordedReviews, recordedPlan] = await Promise.all([
        getEpisode(ev.episode_id),
        getEvaluationReviews(evaluationId),
        getLatestTreatmentPlan(evaluationId),
      ])
      setEpisode(ep)
      setEvaluation(ev)
      setReviews(recordedReviews)
      setTreatmentPlan(recordedPlan)
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : 'Could not load the evaluation.')
    } finally {
      setLoading(false)
      setRerunning(false)
    }
  }, [evaluationId])

  useEffect(() => {
    loadData()
  }, [loadData])

  const rerunEvaluation = async () => {
    if (!episode) return
    setRerunning(true)
    try {
      const next = await evaluateEpisode(episode.id)
      // Same inputs, new run: the workflow follows the new evaluation.
      if (chain.evaluationId === evaluationId) setChain({ evaluationId: next.id })
      window.location.assign(`/evaluation/${next.id}`)
    } finally {
      setRerunning(false)
    }
  }

  const handleReview = async (
    finding: Finding,
    action: ReviewAction,
    reasonCode?: ReasonCode,
    note?: string
  ) => {
    if (!evaluation || !episode) return
    await submitReview({
      episode_id: episode.id,
      evaluation_id: evaluation.id,
      finding_rule_id: finding.rule_id,
      order_id: finding.order_id,
      reviewer: REVIEWER,
      action,
      reason_code: reasonCode,
      note,
    })
    setReviews(await getEvaluationReviews(evaluation.id))
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <Loader2 className="h-7 w-7 animate-spin text-[#3730A3]" />
        <p className="text-sm text-[#6B6A65]">Loading stewardship evaluation...</p>
      </div>
    )
  }

  if (retired) {
    return (
      <div className="mx-auto max-w-md py-24 text-center">
        <p className="text-sm font-medium text-[#1A1A1A]">These results are out of date.</p>
        <p className="mt-2 text-sm text-[#6B6A65]">
          The prescription or clinical context was changed after this evaluation ran, so its findings, decisions and plan no
          longer apply. Run the analysis again from the updated inputs.
        </p>
        <Link href="/episode/new" className="mt-4 inline-block text-sm font-medium text-[#3730A3] hover:underline">
          Back to clinical context
        </Link>
      </div>
    )
  }

  if (!evaluation || !episode) {
    return (
      <div className="mx-auto max-w-md py-24 text-center">
        <p className="text-sm font-medium text-[#1A1A1A]">Evaluation not found.</p>
        <p className="mt-2 text-sm text-[#6B6A65]">
          {loadError ?? 'Unknown evaluation.'} Evaluations are held in the running backend, so a
          backend restart clears them. Enter the prescription again to create a new one.
        </p>
        <Link href="/upload" className="mt-4 inline-block text-sm font-medium text-[#3730A3] hover:underline">
          Start a new evaluation
        </Link>
      </div>
    )
  }

  const viewFor = (f: Finding) =>
    evaluation.items?.find((i) => i.rule_id === f.rule_id && (i.order_id ?? null) === (f.order_id ?? null))
  const orderMap = Object.fromEntries(episode.orders.map((o) => [o.id, o.generic ?? o.raw_text]))
  // Orders the antibiotic rules ran on; non-antibiotics only get R0, so they are left out.
  const antibioticOrderIds = new Set(
    evaluation.findings.flatMap((f) => (f.order_id && f.rule_id !== 'R0_IDENTIFIED' ? [f.order_id] : []))
  )
  const currentAntibiotics = episode.orders
    .filter((o) => o.generic && antibioticOrderIds.has(o.id))
    .map((o) => o.generic as string)
  const cultureOrganisms = [
    ...new Set(
      episode.specimens.flatMap((s) => s.isolates.filter((i) => !i.probable_contaminant).map((i) => i.organism))
    ),
  ]
  const cultureFindings = evaluation.findings.filter(
    (f) => /^C\d/.test(f.rule_id) && f.outcome !== 'PASS'
  )
  const reviewFor = (finding: Finding) =>
    [...reviews]
      .reverse()
      .find(
        (review) =>
          review.finding_rule_id === finding.rule_id &&
          (review.order_id ?? null) === (finding.order_id ?? null)
      )
  const actionable = evaluation.findings.filter((finding) => finding.outcome !== 'PASS')
  const remaining = actionable.filter((finding) => !reviewFor(finding)).length
  // A decision recorded after the plan was signed means the plan no longer reflects the review.
  const planIsCurrent =
    treatmentPlan != null && !reviews.some((review) => Date.parse(review.at) > Date.parse(treatmentPlan.signed_at))
  const inWorkflow = chain.evaluationId === evaluation.id
  const stageLinks = reachableLinks(4, remaining === 0 ? 4 : 3, {
    1: inWorkflow ? '/upload?back=1' : undefined,
    2: inWorkflow ? '/episode/new' : undefined,
    5: `/evaluation/${evaluation.id}/plan`,
  })

  const tabs: { key: Tab; label: string; count?: number }[] = [
    {
      key: 'findings',
      label: 'Findings',
      count: evaluation.findings.filter((f) => f.outcome !== 'PASS').length,
    },
    { key: 'whatif', label: 'What-if' },
    { key: 'culture', label: 'Culture & Resistance', count: episode.specimens.length },
    { key: 'patient', label: 'Patient Info' },
  ]

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col justify-between gap-3 border-b border-[#E2E1DC] pb-4 sm:flex-row sm:items-end">
        <div>
          <p className="font-mono text-xs text-[#6B6A65]">{episode.id} · {episode.patient.id}</p>
          <h1 className="mt-1 text-2xl font-medium tracking-[-0.02em] text-[#1A1A1A]">Review the evaluation</h1>
          <p className="mt-1 text-sm text-[#6B6A65]">
            {episode.diagnosis_text || 'Assess each non-pass finding and record a pharmacist decision.'}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          leftIcon={<RefreshCw className={`h-4 w-4 ${rerunning ? 'animate-spin' : ''}`} />}
          onClick={rerunEvaluation}
          disabled={rerunning}
        >
          Re-evaluate
        </Button>
      </div>

      <WorkflowStepper current={4} links={stageLinks} />

      <div className={`flex flex-col gap-3 rounded-md border px-4 py-3 text-xs sm:flex-row sm:items-center sm:justify-between ${
        remaining === 0
          ? 'border-[#A9CFB7] bg-[#F0FBF4] text-[#1A6B3C]'
          : 'border-[#E8D5A7] bg-[#FFF9EB] text-[#8B5E00]'
      }`}>
        <span>{remaining === 0
          ? planIsCurrent
            ? `Treatment plan signed by ${treatmentPlan?.reviewer}.`
            : treatmentPlan
              ? 'A decision changed after the plan was signed. Reconcile and sign the plan again.'
              : 'Finding review complete. Reconcile the final antibiotic regimen before sign-off.'
          : `${remaining} finding${remaining === 1 ? '' : 's'} still ${remaining === 1 ? 'requires' : 'require'} a pharmacist decision.`}</span>
        {remaining === 0 && (
          <Link href={`/evaluation/${evaluation.id}/plan`}>
            <Button size="sm" variant={planIsCurrent ? 'outline' : 'success'}>
              {planIsCurrent ? 'View signed plan' : 'Review final treatment plan'}
            </Button>
          </Link>
        )}
      </div>

      {evaluation.syndrome && (
        <p className="text-xs text-[#6B6A65]">
          Guideline syndrome: <span className="font-medium text-[#1A1A1A]">{evaluation.syndrome.name ?? 'Not recognised; syndrome-specific checks could not run'}</span>
          {RESOLUTION_LABEL[evaluation.syndrome.resolution] && (
            <span> · {RESOLUTION_LABEL[evaluation.syndrome.resolution]}</span>
          )}
        </p>
      )}

      {(evaluation.warnings ?? []).map((w) => (
        <div key={w} className="rounded-md border border-[#E8D5A7] bg-[#FFF9EB] p-3 text-sm text-[#8B5E00]">{w}</div>
      ))}

      {evaluation.culture && (
        <div className="rounded-md border border-[#E2E1DC] bg-white p-3 text-sm">
          <span className="text-[#6B6A65]">Culture: </span>
          <span className="text-[#1A1A1A]">{evaluation.culture.message}</span>
          {evaluation.culture.action && <span className="text-[#3730A3]"> {evaluation.culture.action}</span>}
        </div>
      )}

      {/* Summary: explains the results below; the rules decide, this text does not */}
      {evaluation.summary && (
        <div className="p-4 rounded-lg border border-[#2d3148] bg-[#141724] text-sm">
          <div className="mb-2 rounded-md border border-[#F1E3A6] bg-[#FFF8D6] px-3 py-2">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-semibold text-black uppercase tracking-wider">
                Summary
              </span>
              <span className="text-xs px-1.5 py-0.5 rounded bg-indigo-500/10 text-black border border-indigo-500/20">
                {evaluation.summary.generated_by === 'AI_WORDED'
                  ? `AI-worded${evaluation.summary.model ? ` (${evaluation.summary.model})` : ''}`
                  : 'Rule-based'}
              </span>
            </div>
            <p className="text-xs text-black">{evaluation.summary.notice}</p>
          </div>
          <p className="text-slate-200 leading-relaxed whitespace-pre-line">
            {evaluation.summary.text}
          </p>
          {evaluation.summary.sources.length > 0 && (
            <p className="mt-2 text-xs text-slate-400">
              Sources: {evaluation.summary.sources.join('; ')}
            </p>
          )}
          {evaluation.summary.fallback_reason && (
            <p className="mt-2 text-xs text-slate-500">
              AI wording was not used ({evaluation.summary.fallback_reason}); the rule-based summary
              is shown.
            </p>
          )}
        </div>
      )}

      <EvaluationChat key={evaluation.id} evaluationId={evaluation.id} />

      {/* Evaluation banner */}
      <EvaluationBanner
        status={evaluation.status}
        findings={evaluation.findings}
        evaluatedAt={evaluation.evaluated_at}
        rulesetVersion={evaluation.ruleset_version}
        trigger={evaluation.trigger}
      />

      {/* Tabs */}
      <div className="flex gap-1 overflow-x-auto border-b border-[#E2E1DC]">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2.5 text-sm font-medium transition-all border-b-2 -mb-px flex items-center gap-1.5 ${
              activeTab === tab.key
                ? 'border-[#1A1A1A] text-[#1A1A1A]'
                : 'border-transparent text-[#6B6A65] hover:text-[#1A1A1A]'
            }`}
          >
            {tab.label}
            {tab.count !== undefined && tab.count > 0 && (
              <span
                className={`text-xs font-bold px-1.5 py-0.5 rounded-full ${
                  activeTab === tab.key
                    ? 'bg-[#1A1A1A] text-white'
                    : 'bg-[#F4F3EF] text-[#6B6A65]'
                }`}
              >
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Findings tab */}
      {activeTab === 'findings' && (
        <div className="space-y-4">
          {evaluation.findings.length === 0 && (
            <div className="py-12 text-center text-sm text-[#6B6A65]">
              No findings generated.
            </div>
          )}
          {evaluation.findings.map((finding) => (
            <FindingCard
              key={`${finding.rule_id}-${finding.order_id ?? 'ep'}`}
              finding={finding}
              orderText={finding.order_id ? orderMap[finding.order_id] : undefined}
              view={viewFor(finding)}
            >
              {finding.outcome !== 'PASS' && (
                <ReviewPanel
                  finding={finding}
                  reviewer={REVIEWER}
                  review={reviewFor(finding)}
                  onSubmit={(action, reasonCode, note) =>
                    handleReview(finding, action, reasonCode, note)
                  }
                />
              )}
            </FindingCard>
          ))}
        </div>
      )}

      {activeTab === 'whatif' && <WhatIfPanel episode={episode} baseline={evaluation} />}

      {/* Culture tab */}
      {activeTab === 'culture' && (
        <div className="space-y-6">
          {cultureFindings.length > 0 && (
            <div className="space-y-3">
              <p className="text-xs font-medium uppercase tracking-wider text-[#6B6A65]">
                What the culture rules found
              </p>
              {cultureFindings.map((finding) => (
                <FindingCard
                  key={`${finding.rule_id}-${finding.order_id ?? 'ep'}`}
                  finding={finding}
                  orderText={finding.order_id ? orderMap[finding.order_id] : undefined}
                  view={viewFor(finding)}
                />
              ))}
            </div>
          )}
          {episode.specimens.length === 0 && (
            <div className="py-12 text-center text-sm text-[#6B6A65]">
              No culture specimens recorded for this episode.
            </div>
          )}
          {episode.specimens.map((specimen) => (
            <CulturePanel
              key={specimen.id}
              specimen={specimen}
              currentAntibiotics={currentAntibiotics}
            />
          ))}
          <NationalSusceptibilityPanel antibiotics={currentAntibiotics} organisms={cultureOrganisms} />
        </div>
      )}

      {/* Patient tab */}
      {activeTab === 'patient' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Card title="Patient">
            <dl className="space-y-3 text-sm">
              {[
                ['ID', episode.patient.id],
                ['Age', `${episode.patient.age_years} years`],
                ['Sex', episode.patient.sex === 'M' ? 'Male' : 'Female'],
                ['Weight', episode.patient.weight_kg ? `${episode.patient.weight_kg} kg` : '—'],
                ['Creatinine', episode.patient.serum_creatinine_mg_dl ? `${episode.patient.serum_creatinine_mg_dl} mg/dL` : '—'],
                ['Allergy Status', episode.patient.allergy_status],
                ['Known Allergies', episode.patient.allergies.join(', ') || '—'],
                [
                  'Comorbidities',
                  (episode.patient.comorbidities ?? []).map((c) => COMORBIDITY_LABELS[c]).join(', ') || '—',
                ],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4">
                  <dt className="shrink-0 text-[#6B6A65]">{k}</dt>
                  <dd className="text-right font-mono text-[#1A1A1A]">{v}</dd>
                </div>
              ))}
            </dl>
          </Card>
          <Card title="Episode">
            <dl className="space-y-3 text-sm">
              {[
                ['Episode ID', episode.id],
                ['Setting', episode.setting],
                ['Syndrome', episode.syndrome_code ?? '—'],
                ['Diagnosis', episode.diagnosis_text ?? '—'],
                ['Started', new Date(episode.started_at).toLocaleDateString('en-IN')],
                ['Drug orders', `${episode.orders.length}`],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4">
                  <dt className="shrink-0 text-[#6B6A65]">{k}</dt>
                  <dd className="text-right font-mono text-[#1A1A1A]">{v}</dd>
                </div>
              ))}
            </dl>
          </Card>
        </div>
      )}
    </div>
  )
}
