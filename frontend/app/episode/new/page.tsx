'use client'

import React, { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Loader2, ArrowRight, User, FlaskConical } from 'lucide-react'
import { createEpisode, evaluateEpisode, getSyndromes } from '@/lib/api'
import type {
  AllergyStatus,
  CultureStatus,
  ExtractedDrug,
  Sex,
  Setting,
  SIR,
} from '@/types/stewardship'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'

// Fallback used only if the API cannot be reached. The live list comes from GET /api/syndromes
// and is exactly the guideline rule pack; do not add codes here that the rule pack lacks.
const FALLBACK_SYNDROMES = [
  { code: 'cystitis', label: 'Uncomplicated cystitis' },
  { code: 'pyelonephritis', label: 'Acute pyelonephritis' },
  { code: 'cellulitis_nonpurulent', label: 'Cellulitis, non-purulent' },
  { code: 'cellulitis_moderate_severe', label: 'Cellulitis, moderate to severe' },
  { code: 'cap_opd_no_comorbidity', label: 'CAP, OPD, no comorbidities' },
  { code: 'cap_opd_comorbidity', label: 'CAP, OPD, with comorbidities' },
  { code: 'cap_ward', label: 'CAP, inpatient ward' },
  { code: 'cap_icu', label: 'CAP, inpatient ICU' },
  { code: 'copd_exacerbation', label: 'Infective exacerbation of asthma/COPD' },
  { code: 'acute_bronchitis', label: 'Acute bronchitis' },
  { code: 'bronchiolitis', label: 'Bronchiolitis' },
  { code: 'viral_uri', label: 'Uncomplicated viral laryngitis/URTI' },
  { code: 'acute_gastroenteritis_no_danger_signs', label: 'Acute gastroenteritis, no danger signs' },
]

function FieldLabel({ label, required }: { label: string; required?: boolean }) {
  return (
    <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wide">
      {label}
      {required && <span className="text-rose-400 ml-1">*</span>}
    </label>
  )
}

const inputClass =
  'w-full bg-[#0f1117] border border-[#2d3148] rounded-lg px-3 py-2.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500'

const selectClass =
  'w-full bg-[#0f1117] border border-[#2d3148] rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500'

export default function EpisodeNewPage() {
  const router = useRouter()
  const [submitting, setSubmitting] = useState(false)
  const [pendingDrugs, setPendingDrugs] = useState<ExtractedDrug[]>([])
  const [syndromes, setSyndromes] = useState(FALLBACK_SYNDROMES)
  const [prescription, setPrescription] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [specimenType, setSpecimenType] = useState('urine')

  // Form state
  const [patientId, setPatientId] = useState('')
  const [age, setAge] = useState('')
  const [sex, setSex] = useState<Sex>('M')
  const [weight, setWeight] = useState('')
  const [creatinine, setCreatinine] = useState('')
  const [allergyStatus, setAllergyStatus] = useState<AllergyStatus>('NONE_KNOWN')
  const [allergies, setAllergies] = useState('')
  const [setting, setSetting] = useState<Setting>('WARD')
  const [syndromeCode, setSyndromeCode] = useState('')
  const [diagnosisText, setDiagnosisText] = useState('')
  const [cultureStatus, setCultureStatus] = useState<CultureStatus>('NOT_SENT')
  const [organism, setOrganism] = useState('')
  const [sus, setSus] = useState<{ agent: string; result: SIR }[]>([
    { agent: '', result: 'S' },
  ])

  useEffect(() => {
    try {
      const stored = sessionStorage.getItem('pendingDrugs')
      if (stored) {
        const drugs: ExtractedDrug[] = JSON.parse(stored)
        setPendingDrugs(drugs)
        setPrescription(drugs.map((d) => d.raw_text).join('\n'))
      }
    } catch {
      /* ignore */
    }
    getSyndromes()
      .then((list) => {
        if (list.length) setSyndromes(list.map((s) => ({ code: s.code, label: s.name })))
      })
      .catch(() => {
        /* keep the fallback list */
      })
  }, [])

  const handleSusChange = (i: number, field: 'agent' | 'result', value: string) => {
    setSus((prev) =>
      prev.map((row, idx) => (idx === i ? { ...row, [field]: value } : row))
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!prescription.trim()) {
      setError('Enter the prescription: one medicine per line, e.g. "Ceftriaxone 2 g IV OD for 7 days".')
      return
    }
    if (cultureStatus === 'FINAL' && !organism.trim()) {
      setError('A final positive culture needs an organism. Choose "No growth" for a negative culture.')
      return
    }
    setSubmitting(true)

    try {
      const withGrowth = cultureStatus === 'FINAL' && organism.trim()
      const episode = await createEpisode({
        patient: {
          id: patientId || `PT-${Date.now()}`,
          age_years: parseInt(age) || 30,
          sex,
          weight_kg: weight ? parseFloat(weight) : null,
          serum_creatinine_mg_dl: creatinine ? parseFloat(creatinine) : null,
          allergy_status: allergyStatus,
          allergies: allergyStatus === 'KNOWN' ? allergies.split(',').map((a) => a.trim()).filter(Boolean) : [],
        },
        setting,
        syndrome_code: syndromeCode || null,
        diagnosis_text: diagnosisText || null,
        prescription,
        // "Not sent" is sent as no culture at all: unknown, never negative.
        cultures:
          cultureStatus === 'NOT_SENT'
            ? []
            : [
                {
                  specimen_type: specimenType,
                  status: cultureStatus,
                  isolates: withGrowth
                    ? [
                        {
                          organism: organism.trim(),
                          susceptibilities: Object.fromEntries(
                            sus.filter((s) => s.agent.trim()).map((s) => [s.agent.trim(), s.result as SIR])
                          ),
                        },
                      ]
                    : [],
                },
              ],
      })

      await evaluateEpisode(episode.id)
      sessionStorage.removeItem('pendingDrugs')
      sessionStorage.removeItem('ocrRawText')
      router.push(`/evaluation/${episode.id}`)
    } catch (e) {
      console.error('Episode creation failed:', e)
      setError(e instanceof Error ? e.message : 'Could not run the evaluation.')
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-6 animate-fade-in max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Prescription → Audit → Action</h1>
        <p className="text-sm text-slate-400 mt-0.5">
          Enter the patient and the prescription. The deterministic engine checks it against the
          NCDC guideline and tells you what to review.
        </p>
      </div>

      {/* Drugs summary */}
      {pendingDrugs.length > 0 && (
        <div className="p-4 rounded-xl border border-indigo-500/30 bg-indigo-500/5">
          <p className="text-sm font-semibold text-indigo-300 mb-2">
            Drug orders from OCR ({pendingDrugs.length})
          </p>
          <div className="flex flex-wrap gap-2">
            {pendingDrugs.map((d) => (
              <span
                key={d.id}
                className="text-xs px-2.5 py-1 rounded-full bg-[#141724] border border-[#2d3148] text-slate-300 capitalize font-mono"
              >
                {d.generic ?? d.raw_text}
              </span>
            ))}
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Patient */}
        <Card title="Patient Information" subtitle="Demographics and clinical baseline">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <div>
              <FieldLabel label="Patient ID" required />
              <input
                className={inputClass}
                placeholder="e.g. PT-1024"
                value={patientId}
                onChange={(e) => setPatientId(e.target.value)}
              />
            </div>
            <div>
              <FieldLabel label="Age (years)" required />
              <input
                className={inputClass}
                type="number"
                min="0"
                max="120"
                placeholder="e.g. 65"
                value={age}
                onChange={(e) => setAge(e.target.value)}
              />
            </div>
            <div>
              <FieldLabel label="Sex" required />
              <select className={selectClass} value={sex} onChange={(e) => setSex(e.target.value as Sex)}>
                <option value="M">Male</option>
                <option value="F">Female</option>
              </select>
            </div>
            <div>
              <FieldLabel label="Weight (kg)" />
              <input
                className={inputClass}
                type="number"
                min="0"
                placeholder="e.g. 70"
                value={weight}
                onChange={(e) => setWeight(e.target.value)}
              />
            </div>
            <div>
              <FieldLabel label="Serum Creatinine (mg/dL)" />
              <input
                className={inputClass}
                type="number"
                step="0.1"
                min="0"
                placeholder="e.g. 1.2"
                value={creatinine}
                onChange={(e) => setCreatinine(e.target.value)}
              />
              <p className="text-xs text-slate-500 mt-1">Used for renal dose adjustment</p>
            </div>
            <div>
              <FieldLabel label="Allergy Status" required />
              <select
                className={selectClass}
                value={allergyStatus}
                onChange={(e) => setAllergyStatus(e.target.value as AllergyStatus)}
              >
                <option value="NONE_KNOWN">None known</option>
                <option value="KNOWN">Known allergy</option>
                <option value="UNKNOWN">Unknown / Not asked</option>
              </select>
            </div>
            {allergyStatus === 'KNOWN' && (
              <div className="sm:col-span-2">
                <FieldLabel label="Known Allergies" required />
                <input
                  className={inputClass}
                  placeholder="e.g. penicillin, sulfonamides (comma-separated)"
                  value={allergies}
                  onChange={(e) => setAllergies(e.target.value)}
                />
              </div>
            )}
          </div>
        </Card>

        {/* Episode */}
        <Card title="Episode Information" subtitle="Clinical context for this admission">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <div>
              <FieldLabel label="Care Setting" required />
              <select className={selectClass} value={setting} onChange={(e) => setSetting(e.target.value as Setting)}>
                <option value="OPD">Outpatient (OPD)</option>
                <option value="WARD">Inpatient (Ward)</option>
                <option value="ICU">ICU</option>
              </select>
            </div>
            <div>
              <FieldLabel label="Syndrome / Infection Type" required />
              <select className={selectClass} value={syndromeCode} onChange={(e) => setSyndromeCode(e.target.value)}>
                <option value="">Select syndrome...</option>
                {syndromes.map((s) => (
                  <option key={s.code} value={s.code}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="sm:col-span-2">
              <FieldLabel label="Diagnosis (free text)" />
              <textarea
                className={`${inputClass} resize-none`}
                rows={3}
                placeholder="Brief clinical diagnosis / impression..."
                value={diagnosisText}
                onChange={(e) => setDiagnosisText(e.target.value)}
              />
            </div>
          </div>
        </Card>

        {/* Prescription */}
        <Card title="Prescription" subtitle="One medicine per line, typed or pasted from the chart">
          <FieldLabel label="Prescription text" required />
          <textarea
            className={`${inputClass} font-mono resize-y`}
            rows={5}
            placeholder={'Ceftriaxone 2 g IV OD for 7 days\nTab Nitrofurantoin 100 mg BD x 5 days'}
            value={prescription}
            onChange={(e) => setPrescription(e.target.value)}
          />
          <p className="text-xs text-slate-500 mt-1">
            Drug, dose, route, frequency and duration are read as written: include the form or route (Tab, PO, IV) or the route check cannot run. Unrecognised or
            misspelt drugs are not guessed; you will be asked to confirm them.
          </p>
        </Card>

        {/* Culture */}
        <Card
          title="Culture Information"
          subtitle="Microbiological specimen results (if available)"
        >
          <div className="space-y-4">
            <div>
              <FieldLabel label="Culture Status" required />
              <select
                className={selectClass}
                value={cultureStatus}
                onChange={(e) => setCultureStatus(e.target.value as CultureStatus)}
              >
                <option value="NOT_SENT">No culture available (unknown, not negative)</option>
                <option value="PENDING">Sent — pending result</option>
                <option value="NO_GROWTH">Negative: no growth</option>
                <option value="GROWTH_NO_AST">Growth, awaiting susceptibility</option>
                <option value="FINAL">Positive: organism and susceptibility reported</option>
                <option value="CONTAMINATED">Contaminated specimen</option>
              </select>
            </div>

            {cultureStatus !== 'NOT_SENT' && (
              <div>
                <FieldLabel label="Specimen" />
                <input
                  className={inputClass}
                  placeholder="urine, blood, sputum, pus"
                  value={specimenType}
                  onChange={(e) => setSpecimenType(e.target.value)}
                />
              </div>
            )}

            {cultureStatus === 'FINAL' && (
              <div className="space-y-4 pt-2">
                <div>
                  <FieldLabel label="Organism" />
                  <input
                    className={inputClass}
                    placeholder="e.g. Escherichia coli, Klebsiella pneumoniae"
                    value={organism}
                    onChange={(e) => setOrganism(e.target.value)}
                  />
                </div>

                <div>
                  <FieldLabel label="Susceptibility (AST)" />
                  <div className="space-y-2">
                    {sus.map((row, i) => (
                      <div key={i} className="flex gap-2 items-center">
                        <input
                          className={`${inputClass} flex-1`}
                          placeholder="Antibiotic name"
                          value={row.agent}
                          onChange={(e) => handleSusChange(i, 'agent', e.target.value)}
                        />
                        <select
                          className={`${selectClass} w-40`}
                          value={row.result}
                          onChange={(e) => handleSusChange(i, 'result', e.target.value)}
                        >
                          <option value="S">S — Susceptible</option>
                          <option value="I">I — Intermediate</option>
                          <option value="R">R — Resistant</option>
                        </select>
                        {i === sus.length - 1 ? (
                          <button
                            type="button"
                            onClick={() => setSus((p) => [...p, { agent: '', result: 'S' }])}
                            className="px-3 py-2.5 rounded-lg text-sm text-indigo-400 border border-indigo-500/30 hover:bg-indigo-500/10 transition-colors whitespace-nowrap"
                          >
                            + Add
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setSus((p) => p.filter((_, idx) => idx !== i))}
                            className="px-3 py-2.5 rounded-lg text-sm text-rose-400 border border-rose-500/30 hover:bg-rose-500/10 transition-colors"
                          >
                            ×
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </Card>

        {error && (
          <div className="p-3 rounded-lg border border-rose-500/30 bg-rose-500/10 text-sm text-rose-300">
            {error}
          </div>
        )}

        {/* Submit */}
        <div className="flex items-center justify-between pt-2">
          <p className="text-xs text-slate-400">
            The stewardship engine will evaluate all drug orders against patient data and guidelines.
          </p>
          <Button
            type="submit"
            variant="primary"
            size="md"
            isLoading={submitting}
            rightIcon={!submitting ? <ArrowRight className="w-4 h-4" /> : undefined}
          >
            {submitting ? 'Running evaluation...' : 'Run Evaluation'}
          </Button>
        </div>
      </form>
    </div>
  )
}
