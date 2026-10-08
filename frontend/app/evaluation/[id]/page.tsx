'use client'

import React, { useCallback, useEffect, useState } from 'react'
import { use } from 'react'
import { Loader2, RefreshCw } from 'lucide-react'
import {
  evaluateEpisode,
  getEpisode,
  getEvaluation,
  getEvaluationReviews,
  submitReview,
} from '@/lib/api'
import type {
  Episode,
  EvaluationReport,
  Finding,
  ReasonCode,
  Review,
  ReviewAction,
} from '@/types/stewardship'
import { EvaluationBanner } from '@/components/stewardship/EvaluationBanner'
import { FindingCard } from '@/components/stewardship/FindingCard'
import { ReviewPanel } from '@/components/stewardship/ReviewPanel'
import { CulturePanel } from '@/components/stewardship/CulturePanel'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { WorkflowStepper } from '@/components/stewardship/WorkflowStepper'

type Tab = 'findings' | 'culture' | 'patient'

export default function EvaluationPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id: evaluationId } = use(params)
  const [episode, setEpisode] = useState<Episode | null>(null)
  const [evaluation, setEvaluation] = useState<EvaluationReport | null>(null)
  const [reviews, setReviews] = useState<Review[]>([])
  const [loading, setLoading] = useState(true)
  const [rerunning, setRerunning] = useState(false)
  const [activeTab, setActiveTab] = useState<Tab>('findings')
  const [patientOpen, setPatientOpen] = useState(false)

  const REVIEWER = 'Dr. Priya Mehta (Pharmacist)'

  const loadData = useCallback(async () => {
    try {
      const ev = await getEvaluation(evaluationId)
      const [ep, recordedReviews] = await Promise.all([
        getEpisode(ev.episode_id),
        getEvaluationReviews(evaluationId),
      ])
      setEpisode(ep)
      setEvaluation(ev)
      setReviews(recordedReviews)
    } catch (e) {
      console.error('Failed to load evaluation:', e)
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

  if (!evaluation || !episode) {
    return (
      <div className="py-24 text-center text-[#6B6A65]">Evaluation not found.</div>
    )
  }

  const viewFor = (f: Finding) =>
    evaluation.items?.find((i) => i.rule_id === f.rule_id && (i.order_id ?? null) === (f.order_id ?? null))
  const orderMap = Object.fromEntries(episode.orders.map((o) => [o.id, o.generic ?? o.raw_text]))
  const currentAntibiotics = episode.orders
    .filter((o) => o.generic)
    .map((o) => o.generic as string)
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

  const tabs: { key: Tab; label: string; count?: number }[] = [
    {
      key: 'findings',
      label: 'Findings',
      count: evaluation.findings.filter((f) => f.outcome !== 'PASS').length,
    },
    { key: 'culture', label: 'Culture & Resistance', count: episode.specimens.length },
    { key: 'patient', label: 'Patient Info' },
  ]

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col justify-between gap-3 border-b border-[#E2E1DC] pb-4 sm:flex-row sm:items-end">
        <div>
          <p className="font-mono text-[11px] text-[#6B6A65]">{episode.id} · {episode.patient.id}</p>
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

      <WorkflowStepper current={4} />

      <div className={`rounded-md border px-3 py-2 text-xs ${
        remaining === 0
          ? 'border-[#A9CFB7] bg-[#F0FBF4] text-[#1A6B3C]'
          : 'border-[#E8D5A7] bg-[#FFF9EB] text-[#8B5E00]'
      }`}>
        {remaining === 0
          ? 'Review complete. Decisions are preserved in the audit log.'
          : `${remaining} finding${remaining === 1 ? '' : 's'} still ${remaining === 1 ? 'requires' : 'require'} a pharmacist decision.`}
      </div>

      {evaluation.syndrome && (
        <p className="text-xs text-[#6B6A65]">
          Guideline syndrome: <span className="font-medium text-[#1A1A1A]">{evaluation.syndrome.name ?? 'Not recognised; syndrome-specific checks could not run'}</span>
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
                className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
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

      {/* Culture tab */}
      {activeTab === 'culture' && (
        <div className="space-y-6">
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
