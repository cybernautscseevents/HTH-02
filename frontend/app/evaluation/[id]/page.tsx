'use client'

import React, { useCallback, useEffect, useState } from 'react'
import { use } from 'react'
import { Loader2, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react'
import { evaluateEpisode, getEpisode, submitReview } from '@/lib/api'
import type {
  Episode,
  EvaluationReport,
  Finding,
  ReasonCode,
  ReviewAction,
} from '@/types/stewardship'
import { EvaluationBanner } from '@/components/stewardship/EvaluationBanner'
import { FindingCard } from '@/components/stewardship/FindingCard'
import { ReviewPanel } from '@/components/stewardship/ReviewPanel'
import { CulturePanel } from '@/components/stewardship/CulturePanel'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'

type Tab = 'findings' | 'culture' | 'patient'

export default function EvaluationPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id: episodeId } = use(params)
  const [episode, setEpisode] = useState<Episode | null>(null)
  const [evaluation, setEvaluation] = useState<EvaluationReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [rerunning, setRerunning] = useState(false)
  const [activeTab, setActiveTab] = useState<Tab>('findings')
  const [patientOpen, setPatientOpen] = useState(false)

  const REVIEWER = 'Dr. Priya Mehta (Pharmacist)'

  const loadData = useCallback(async () => {
    try {
      const [ep, ev] = await Promise.all([
        getEpisode(episodeId),
        evaluateEpisode(episodeId),
      ])
      setEpisode(ep)
      setEvaluation(ev)
    } catch (e) {
      console.error('Failed to load evaluation:', e)
    } finally {
      setLoading(false)
      setRerunning(false)
    }
  }, [episodeId])

  useEffect(() => {
    loadData()
  }, [loadData])

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
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-400" />
        <p className="text-sm text-slate-400">Running stewardship evaluation...</p>
      </div>
    )
  }

  if (!evaluation || !episode) {
    return (
      <div className="text-center py-24 text-slate-400">Evaluation not found.</div>
    )
  }

  const viewFor = (f: Finding) =>
    evaluation.items?.find((i) => i.rule_id === f.rule_id && (i.order_id ?? null) === (f.order_id ?? null))
  const orderMap = Object.fromEntries(episode.orders.map((o) => [o.id, o.generic ?? o.raw_text]))
  const currentAntibiotics = episode.orders
    .filter((o) => o.generic)
    .map((o) => o.generic as string)

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
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-mono text-slate-400">Episode</span>
            <span className="text-xs font-mono text-slate-300">{episode.id}</span>
            <span className="text-slate-600">·</span>
            <span className="text-xs font-mono text-slate-400">Patient</span>
            <span className="text-xs font-mono text-slate-300">{episode.patient.id}</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-100">Stewardship Evaluation</h1>
          {episode.diagnosis_text && (
            <p className="text-sm text-slate-400 mt-0.5">{episode.diagnosis_text}</p>
          )}
        </div>
        <Button
          variant="ghost"
          size="sm"
          leftIcon={<RefreshCw className={`w-4 h-4 ${rerunning ? 'animate-spin' : ''}`} />}
          onClick={() => { setRerunning(true); loadData() }}
        >
          Re-evaluate
        </Button>
      </div>

      {/* Prescription → Audit → Action */}
      <div className="flex items-center gap-2 text-xs text-slate-400">
        <span className="px-2 py-1 rounded bg-[#141724] border border-[#2d3148]">Prescription</span>
        <span>→</span>
        <span className="px-2 py-1 rounded bg-[#141724] border border-[#2d3148]">
          Audit ({evaluation.ruleset_version})
        </span>
        <span>→</span>
        <span className="px-2 py-1 rounded bg-indigo-500/10 border border-indigo-500/30 text-indigo-300">
          {evaluation.findings.filter((f) => f.outcome !== 'PASS').length} to review
        </span>
      </div>

      {evaluation.syndrome && (
        <p className="text-xs text-slate-400">
          Guideline syndrome:{' '}
          <span className="text-slate-200">
            {evaluation.syndrome.name ?? 'not recognised: guideline checks (R1, R3, R5) could not run'}
          </span>
        </p>
      )}

      {(evaluation.warnings ?? []).map((w) => (
        <div key={w} className="p-3 rounded-lg border border-amber-500/30 bg-amber-500/10 text-sm text-amber-200">
          {w}
        </div>
      ))}

      {evaluation.culture && (
        <div className="p-3 rounded-lg border border-[#2d3148] bg-[#141724] text-sm">
          <span className="text-slate-400">Culture: </span>
          <span className="text-slate-200">{evaluation.culture.message}</span>
          {evaluation.culture.action && (
            <span className="text-indigo-300"> {evaluation.culture.action}</span>
          )}
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
      <div className="flex gap-1 border-b border-[#2d3148]">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2.5 text-sm font-medium transition-all border-b-2 -mb-px flex items-center gap-1.5 ${
              activeTab === tab.key
                ? 'border-indigo-500 text-indigo-300'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            {tab.label}
            {tab.count !== undefined && tab.count > 0 && (
              <span
                className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
                  activeTab === tab.key
                    ? 'bg-indigo-500/20 text-indigo-300'
                    : 'bg-[#2d3148] text-slate-400'
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
            <div className="text-center py-12 text-slate-400 text-sm">
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
              <ReviewPanel
                finding={finding}
                evaluationId={evaluation.id}
                episodeId={episode.id}
                reviewer={REVIEWER}
                onSubmit={(action, reasonCode, note) =>
                  handleReview(finding, action, reasonCode, note)
                }
              />
            </FindingCard>
          ))}
        </div>
      )}

      {/* Culture tab */}
      {activeTab === 'culture' && (
        <div className="space-y-6">
          {episode.specimens.length === 0 && (
            <div className="text-center py-12 text-slate-400 text-sm">
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
                  <dt className="text-slate-400 shrink-0">{k}</dt>
                  <dd className="text-slate-200 text-right font-mono">{v}</dd>
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
                  <dt className="text-slate-400 shrink-0">{k}</dt>
                  <dd className="text-slate-200 text-right font-mono">{v}</dd>
                </div>
              ))}
            </dl>
          </Card>
        </div>
      )}
    </div>
  )
}
