'use client'

import React, { useEffect, useRef, useState } from 'react'
import { FlaskConical, Loader2, RotateCcw } from 'lucide-react'
import { whatIfEpisode } from '@/lib/api'
import type { Episode, EvaluationReport, Finding, PatientChanges } from '@/types/stewardship'
import { FindingCard } from '@/components/stewardship/FindingCard'
import { Button } from '@/components/ui/Button'

interface WhatIfPanelProps {
  episode: Episode
  baseline: EvaluationReport
}

type Change = 'new' | 'changed' | 'same'

const key = (f: Finding) => `${f.rule_id}|${f.order_id ?? ''}`

const CHANGE_CHIP: Record<Exclude<Change, 'same'>, string> = {
  new: 'border-[#D9A4A4] bg-[#FDF2F2] text-[#8B1A1A]',
  changed: 'border-[#E8D5A7] bg-[#FFF9EB] text-[#8B5E00]',
}

/**
 * Sandbox for the evaluation: change a patient value and the same deterministic rules re-run
 * on the backend. Nothing here is stored, reviewed or signed; the recorded evaluation is
 * untouched.
 */
export const WhatIfPanel: React.FC<WhatIfPanelProps> = ({ episode, baseline }) => {
  const patient = episode.patient
  const [changes, setChanges] = useState<PatientChanges>({})
  const [result, setResult] = useState<EvaluationReport | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const latest = useRef(0)

  const touched = Object.keys(changes).length > 0
  const creatinine = changes.serum_creatinine_mg_dl ?? patient.serum_creatinine_mg_dl ?? 1.0
  const allergies = changes.allergies ?? patient.allergies
  const penicillinAllergy = allergies.some((a) => a.trim().toLowerCase() === 'penicillin')
  const pregnant = 'pregnant' in changes ? changes.pregnant : patient.pregnant
  const canBePregnant = patient.sex === 'F'

  useEffect(() => {
    if (!touched) {
      latest.current++
      setResult(null)
      setError(null)
      setRunning(false)
      return
    }
    const request = ++latest.current
    setRunning(true)
    const timer = setTimeout(async () => {
      try {
        const report = await whatIfEpisode(episode.id, changes)
        if (request === latest.current) {
          setResult(report)
          setError(null)
        }
      } catch (e) {
        if (request === latest.current) setError(e instanceof Error ? e.message : 'What-if failed.')
      } finally {
        if (request === latest.current) setRunning(false)
      }
    }, 200)
    return () => clearTimeout(timer)
  }, [changes, episode.id, touched])

  const togglePenicillin = () => {
    const others = allergies.filter((a) => a.trim().toLowerCase() !== 'penicillin')
    const next = penicillinAllergy ? others : [...others, 'penicillin']
    const status =
      next.length > 0
        ? 'KNOWN'
        : patient.allergy_status === 'KNOWN'
          ? 'NONE_KNOWN'
          : patient.allergy_status
    setChanges((c) => ({ ...c, allergies: next, allergy_status: status }))
  }

  const before = new Map(baseline.findings.map((f) => [key(f), f]))
  const changeOf = (f: Finding): Change => {
    const old = before.get(key(f))
    if (!old || old.outcome === 'PASS') return 'new'
    return old.outcome !== f.outcome || old.severity !== f.severity || old.message !== f.message
      ? 'changed'
      : 'same'
  }
  const shown = (result?.findings ?? []).filter((f) => f.outcome !== 'PASS')
  const after = new Map((result?.findings ?? []).map((f) => [key(f), f]))
  const resolved = baseline.findings.filter(
    (f) => f.outcome !== 'PASS' && (after.get(key(f))?.outcome ?? 'PASS') === 'PASS'
  )
  const counts = {
    new: shown.filter((f) => changeOf(f) === 'new').length,
    changed: shown.filter((f) => changeOf(f) === 'changed').length,
  }
  const orderMap = Object.fromEntries(episode.orders.map((o) => [o.id, o.generic ?? o.raw_text]))
  const viewFor = (f: Finding) =>
    result?.items?.find((i) => i.rule_id === f.rule_id && (i.order_id ?? null) === (f.order_id ?? null))

  return (
    <div className="space-y-5">
      <div className="rounded-[8px] border border-[#D8D5F0] bg-[#F7F6FF] px-4 py-3 text-xs text-[#3730A3]">
        <span className="font-medium">Simulation only.</span> Change a value and the same rules
        re-run instantly. Nothing here is saved, reviewed or added to the audit log.
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-[8px] border border-[#E2E1DC] bg-white p-4">
          <div className="flex items-baseline justify-between">
            <label htmlFor="whatif-creatinine" className="text-sm font-medium text-[#1A1A1A]">
              Serum creatinine
            </label>
            <span className="font-mono text-sm text-[#1A1A1A]">{creatinine.toFixed(1)} mg/dL</span>
          </div>
          <input
            id="whatif-creatinine"
            type="range"
            min={0.4}
            max={8}
            step={0.1}
            value={creatinine}
            onChange={(e) =>
              setChanges((c) => ({ ...c, serum_creatinine_mg_dl: Number(e.target.value) }))
            }
            className="mt-3 w-full accent-[#3730A3]"
          />
          <p className="mt-1 text-xs text-[#6B6A65]">
            {patient.weight_kg
              ? `Recorded: ${patient.serum_creatinine_mg_dl ?? 'none'} · ${patient.age_years} y · ${patient.weight_kg} kg`
              : 'Weight not recorded, so kidney function cannot be estimated.'}
          </p>
        </div>

        <div className="rounded-[8px] border border-[#E2E1DC] bg-white p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-[#1A1A1A]">Penicillin allergy</span>
            <button
              role="switch"
              aria-checked={penicillinAllergy}
              aria-label="Penicillin allergy"
              onClick={togglePenicillin}
              className={`relative h-6 w-11 rounded-full transition-colors ${
                penicillinAllergy ? 'bg-[#8B1A1A]' : 'bg-[#C8C7C0]'
              }`}
            >
              <span
                className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${
                  penicillinAllergy ? 'left-[22px]' : 'left-0.5'
                }`}
              />
            </button>
          </div>
          <p className="mt-3 text-xs text-[#6B6A65]">
            Allergies: {allergies.join(', ') || 'none recorded'}
          </p>
        </div>

        <div className="rounded-[8px] border border-[#E2E1DC] bg-white p-4">
          <span className="text-sm font-medium text-[#1A1A1A]">Pregnancy</span>
          <div className="mt-3 grid grid-cols-3 overflow-hidden rounded-md border border-[#E2E1DC] text-xs">
            {([
              ['Not recorded', null],
              ['No', false],
              ['Pregnant', true],
            ] as const).map(([label, value]) => (
              <button
                key={label}
                disabled={!canBePregnant}
                onClick={() => setChanges((c) => ({ ...c, pregnant: value }))}
                className={`px-2 py-1.5 transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                  (pregnant ?? null) === value
                    ? 'bg-[#1A1A1A] text-white'
                    : 'bg-white text-[#6B6A65] hover:text-[#1A1A1A]'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {!canBePregnant && (
            <p className="mt-1 text-xs text-[#6B6A65]">Not applicable: patient is male.</p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#E2E1DC] pb-3">
        <div className="flex items-center gap-2 text-sm text-[#1A1A1A]">
          {running ? (
            <Loader2 className="h-4 w-4 animate-spin text-[#3730A3]" />
          ) : (
            <FlaskConical className="h-4 w-4 text-[#3730A3]" />
          )}
          {!touched
            ? 'Change a value above to see what the rules return.'
            : result
              ? `${counts.new} new · ${counts.changed} changed · ${resolved.length} resolved, compared with the recorded evaluation`
              : 'Running the rules...'}
        </div>
        {touched && (
          <Button
            variant="outline"
            size="sm"
            leftIcon={<RotateCcw className="h-4 w-4" />}
            onClick={() => setChanges({})}
          >
            Reset to recorded values
          </Button>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-[#D9A4A4] bg-[#FDF2F2] p-3 text-sm text-[#8B1A1A]">{error}</div>
      )}

      {result && (
        <div className={`space-y-4 transition-opacity ${running ? 'opacity-60' : ''}`}>
          {resolved.length > 0 && (
            <div className="rounded-md border border-[#A9CFB7] bg-[#F0FBF4] p-3 text-xs text-[#1A6B3C]">
              <p className="font-medium">Resolved by this change</p>
              <ul className="mt-1 space-y-0.5">
                {resolved.map((f) => (
                  <li key={key(f)}>
                    <span className="font-mono">{f.rule_id}</span>
                    {f.order_id && ` · ${orderMap[f.order_id]}`}: {f.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {shown.length === 0 && (
            <p className="py-8 text-center text-sm text-[#6B6A65]">Every check passes with these values.</p>
          )}
          {shown.map((f) => {
            const change = changeOf(f)
            return (
              <div key={key(f)} className="relative">
                {change !== 'same' && (
                  <span
                    className={`absolute -top-2 right-3 z-10 rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${CHANGE_CHIP[change]}`}
                  >
                    {change}
                  </span>
                )}
                <FindingCard
                  finding={f}
                  orderText={f.order_id ? orderMap[f.order_id] : undefined}
                  view={viewFor(f)}
                />
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
