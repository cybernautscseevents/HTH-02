'use client'

import React, { useState } from 'react'
import { addCulture } from '@/lib/api'
import type { CultureInput, CultureStatus, EvaluationReport, SIR } from '@/types/stewardship'
import { Button } from '@/components/ui/Button'

interface AddCultureFormProps {
  episodeId: string
  onAdded: (report: EvaluationReport) => void
  onCancel: () => void
}

const inputClass =
  'w-full rounded-md border border-[#C8C7C0] bg-white px-3 py-2 text-sm text-[#1A1A1A] focus:border-[#3730A3] focus:outline-none'

// Statuses whose report can name an organism; the backend rejects isolates on any other.
const WITH_ORGANISM: CultureStatus[] = ['FINAL', 'GROWTH_NO_AST', 'CONTAMINATED']

/**
 * A culture result reported after the episode was created. Saving attaches it to the episode
 * and re-runs the rules (trigger CULTURE_RESULT); earlier specimens are kept as they were.
 */
export const AddCultureForm: React.FC<AddCultureFormProps> = ({ episodeId, onAdded, onCancel }) => {
  const [status, setStatus] = useState<CultureStatus>('FINAL')
  const [specimenType, setSpecimenType] = useState('urine')
  const [organism, setOrganism] = useState('')
  const [rows, setRows] = useState<{ agent: string; result: SIR }[]>([{ agent: '', result: 'S' }])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const setRow = (i: number, field: 'agent' | 'result', value: string) =>
    setRows((prev) => prev.map((row, idx) => (idx === i ? { ...row, [field]: value } : row)))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!specimenType.trim()) {
      setError('Enter the specimen type.')
      return
    }
    if (status === 'FINAL' && !organism.trim()) {
      setError('A final positive culture needs an organism. Choose "No growth" for a negative culture.')
      return
    }
    const culture: CultureInput = {
      specimen_type: specimenType.trim(),
      status,
      isolates:
        WITH_ORGANISM.includes(status) && organism.trim()
          ? [
              {
                organism: organism.trim(),
                susceptibilities:
                  status === 'FINAL'
                    ? Object.fromEntries(rows.filter((r) => r.agent.trim()).map((r) => [r.agent.trim(), r.result]))
                    : {},
              },
            ]
          : [],
    }
    setSaving(true)
    try {
      onAdded(await addCulture(episodeId, culture))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save the culture result.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 rounded-lg border border-[#D8D5F0] bg-[#F7F6FF] p-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="text-xs font-medium text-[#6B6A65]">
          Result
          <select className={`${inputClass} mt-1`} value={status} onChange={(e) => setStatus(e.target.value as CultureStatus)}>
            <option value="FINAL">Positive: organism and susceptibility reported</option>
            <option value="GROWTH_NO_AST">Growth, awaiting susceptibility</option>
            <option value="NO_GROWTH">Negative: no growth</option>
            <option value="PENDING">Sent, pending result</option>
            <option value="CONTAMINATED">Contaminated specimen</option>
          </select>
        </label>
        <label className="text-xs font-medium text-[#6B6A65]">
          Specimen
          <input
            className={`${inputClass} mt-1`}
            placeholder="urine, blood, sputum, pus"
            value={specimenType}
            onChange={(e) => setSpecimenType(e.target.value)}
          />
        </label>
        {WITH_ORGANISM.includes(status) && (
          <label className="text-xs font-medium text-[#6B6A65] sm:col-span-2">
            Organism{status === 'FINAL' ? '' : ' (optional)'}
            <input
              className={`${inputClass} mt-1`}
              placeholder="e.g. Escherichia coli, Klebsiella pneumoniae"
              value={organism}
              onChange={(e) => setOrganism(e.target.value)}
            />
          </label>
        )}
      </div>

      {status === 'FINAL' && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-[#6B6A65]">Susceptibility (AST)</p>
          {rows.map((row, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                className={`${inputClass} flex-1`}
                placeholder="Antibiotic name"
                value={row.agent}
                onChange={(e) => setRow(i, 'agent', e.target.value)}
              />
              <select className={`${inputClass} w-44`} value={row.result} onChange={(e) => setRow(i, 'result', e.target.value)}>
                <option value="S">S: Susceptible</option>
                <option value="I">I: Intermediate</option>
                <option value="SDD">SDD: Dose-dependent</option>
                <option value="R">R: Resistant</option>
              </select>
              <button
                type="button"
                className="rounded-md border border-[#C8C7C0] bg-white px-3 py-2 text-sm text-[#6B6A65] hover:bg-[#FAFAF8]"
                onClick={() =>
                  i === rows.length - 1
                    ? setRows((p) => [...p, { agent: '', result: 'S' }])
                    : setRows((p) => p.filter((_, idx) => idx !== i))
                }
                aria-label={i === rows.length - 1 ? 'Add antibiotic' : 'Remove antibiotic'}
              >
                {i === rows.length - 1 ? '+' : '×'}
              </button>
            </div>
          ))}
        </div>
      )}

      {error && <div className="rounded-md border border-[#D9A4A4] bg-[#FDF2F2] px-3 py-2 text-sm text-[#8B1A1A]">{error}</div>}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <Button type="submit" size="sm" isLoading={saving}>
          Save and re-evaluate
        </Button>
      </div>
    </form>
  )
}
