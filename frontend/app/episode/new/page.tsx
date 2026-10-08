'use client'

import React, { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Loader2, ArrowRight, User, FlaskConical, Search } from 'lucide-react'
import { createEpisode, evaluateEpisode, getPatientRecord, getSyndromes } from '@/lib/api'
import type {
  AllergyStatus,
  CultureStatus,
  ExtractedDrug,
  PrescriptionDiagnosis,
  Sex,
  Setting,
  SIR,
} from '@/types/stewardship'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { WorkflowStepper } from '@/components/stewardship/WorkflowStepper'

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
    <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.06em] text-[#6B6A65]">
      {label}
      {required && <span className="text-rose-400 ml-1">*</span>}
    </label>
  )
}

const inputClass =
  'w-full rounded-md border border-[#C8C7C0] bg-white px-3 py-2.5 text-sm text-[#1A1A1A] placeholder:text-[#8B8982] focus:border-[#3730A3] focus:outline-none focus:ring-2 focus:ring-[#3730A3]/10'

const selectClass =
  'w-full rounded-md border border-[#C8C7C0] bg-white px-3 py-2.5 text-sm text-[#1A1A1A] focus:border-[#3730A3] focus:outline-none focus:ring-2 focus:ring-[#3730A3]/10'

export default function EpisodeNewPage() {
  const router = useRouter()
  const [submitting, setSubmitting] = useState(false)
  const [pendingDrugs, setPendingDrugs] = useState<ExtractedDrug[]>([])
  const [syndromes, setSyndromes] = useState(FALLBACK_SYNDROMES)
  const [prescription, setPrescription] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [specimenType, setSpecimenType] = useState('urine')
  const [lookingUp, setLookingUp] = useState(false)
  const [recordNote, setRecordNote] = useState<string | null>(null)
  const [rxDiagnosis, setRxDiagnosis] = useState<PrescriptionDiagnosis | null>(null)

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
      const diagnosis = sessionStorage.getItem('rxDiagnosis')
      if (diagnosis) {
        const parsed: PrescriptionDiagnosis = JSON.parse(diagnosis)
        setRxDiagnosis(parsed)
        setDiagnosisText(parsed.text ?? '')
        setSyndromeCode(parsed.syndrome_code ?? '')
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

  // Fills the form from the hospital record. Every value stays editable; a value the record
  // lacks is cleared, never kept from a previous patient. The syndrome is still chosen by hand.
  const handleLookup = async () => {
    const id = patientId.trim()
    if (!id) {
      setError('Enter a patient ID to fetch the record.')
      return
    }
    setError(null)
    setRecordNote(null)
    setLookingUp(true)
    try {
      const { patient, cultures, source } = await getPatientRecord(id)
      setAge(String(patient.age_years))
      setSex(patient.sex)
      setWeight(patient.weight_kg != null ? String(patient.weight_kg) : '')
      setCreatinine(patient.serum_creatinine_mg_dl != null ? String(patient.serum_creatinine_mg_dl) : '')
      setAllergyStatus(patient.allergy_status)
      setAllergies(patient.allergies.join(', '))
      const culture = cultures[0]
      setCultureStatus(culture?.status ?? 'NOT_SENT')
      setSpecimenType(culture?.specimen_type ?? 'urine')
      const isolate = culture?.isolates[0]
      setOrganism(isolate?.organism ?? '')
      const rows = Object.entries(isolate?.susceptibilities ?? {}).map(([agent, result]) => ({ agent, result }))
      setSus(rows.length ? rows : [{ agent: '', result: 'S' }])
      const missing = [
        patient.weight_kg == null && 'weight',
        patient.serum_creatinine_mg_dl == null && 'creatinine',
        patient.allergy_status === 'UNKNOWN' && 'allergy status',
      ].filter(Boolean)
      const extra = cultures.length > 1 ? ` The record has ${cultures.length} cultures; only the first is shown.` : ''
      setRecordNote(
        `Filled from ${source}. Check every value before running.` +
          (missing.length ? ` Not in the record: ${missing.join(', ')}.` : '') +
          extra
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not fetch the patient record.')
    } finally {
      setLookingUp(false)
    }
  }

  const syndromeNote = () => {
    const fromDoctor = rxDiagnosis?.syndrome_code
    if (fromDoctor && syndromeCode === fromDoctor)
      return `From the prescriber's diagnosis "${rxDiagnosis?.text}". Change it only if that diagnosis is wrong; the change is recorded.`
    if (fromDoctor && syndromeCode)
      return `Changed from the prescriber's diagnosis (${rxDiagnosis?.syndrome_name}). The change is recorded with the evaluation.`
    if (rxDiagnosis?.text && !syndromeCode)
      return `The prescriber wrote "${rxDiagnosis.text}". ${rxDiagnosis.note ?? ''} Select the matching syndrome.`
    if (!syndromeCode)
      return 'Leave empty to use the diagnosis written on the prescription. With no diagnosis, the review flags the indication as undocumented.'
    return 'Selected by you.'
  }

  const handleSusChange = (i: number, field: 'agent' | 'result', value: string) => {
    setSus((prev) =>
      prev.map((row, idx) => (idx === i ? { ...row, [field]: value } : row))
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    const ageYears = Number(age)
    if (!age.trim() || !Number.isInteger(ageYears) || ageYears < 0 || ageYears > 120) {
      setError('Enter the patient age in whole years (0-120).')
      return
    }
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
          age_years: ageYears,
          sex,
          weight_kg: weight ? parseFloat(weight) : null,
          serum_creatinine_mg_dl: creatinine ? parseFloat(creatinine) : null,
          allergy_status: allergyStatus,
          allergies: allergyStatus === 'KNOWN' ? allergies.split(',').map((a) => a.trim()).filter(Boolean) : [],
        },
        setting,
        // Empty when nobody chose one: the backend then reads the prescriber's diagnosis, and
        // reports the indication as undocumented if there is none.
        syndrome_code: syndromeCode || null,
        diagnosis_text: diagnosisText.trim() || null,
        prescription,
        confirmed_drugs: pendingDrugs
          .filter((drug) => drug.norm_status === 'CONFIRMED' && drug.generic)
          .map((drug) => ({
            order_id: drug.id,
            raw_text: drug.raw_text,
            generic: drug.generic as string,
          })),
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

      const evaluation = await evaluateEpisode(episode.id)
      sessionStorage.removeItem('pendingDrugs')
      sessionStorage.removeItem('ocrRawText')
      sessionStorage.removeItem('rxDiagnosis')
      router.push(`/evaluation/${evaluation.id}`)
    } catch (e) {
      console.error('Episode creation failed:', e)
      setError(e instanceof Error ? e.message : 'Could not run the evaluation.')
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 animate-fade-in">
      <div className="flex flex-col justify-between gap-3 border-b border-[#E2E1DC] pb-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-[#6B6A65]">New stewardship review</p>
          <h1 className="mt-1 text-2xl font-medium tracking-[-0.02em] text-[#1A1A1A]">Add clinical context</h1>
          <p className="mt-1 text-sm text-[#6B6A65]">
            Complete the patient, syndrome, renal, allergy, and culture information needed by the rules.
          </p>
        </div>
        <span className="text-xs text-[#6B6A65]">Step 2 of 4</span>
      </div>

      <WorkflowStepper current={2} />

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
              <div className="flex gap-2">
                <input
                  className={`${inputClass} flex-1`}
                  placeholder="e.g. SYN-DEMO-04"
                  value={patientId}
                  onChange={(e) => {
                    setPatientId(e.target.value)
                    setRecordNote(null)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      handleLookup()
                    }
                  }}
                />
                <button
                  type="button"
                  onClick={handleLookup}
                  disabled={lookingUp}
                  className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border border-[#C8C7C0] px-3 py-2.5 text-sm text-[#3730A3] hover:bg-[#3730A3]/5 disabled:opacity-50"
                >
                  {lookingUp ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                  Fetch record
                </button>
              </div>
              {recordNote && <p className="mt-1 text-xs text-[#3730A3]">{recordNote}</p>}
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
              <FieldLabel label="Syndrome / Infection Type" />
              <select className={selectClass} value={syndromeCode} onChange={(e) => setSyndromeCode(e.target.value)}>
                <option value="">Select syndrome...</option>
                {syndromes.map((s) => (
                  <option key={s.code} value={s.code}>
                    {s.label}
                  </option>
                ))}
              </select>
              <p className="text-xs text-slate-500 mt-1">{syndromeNote()}</p>
            </div>
            <div className="sm:col-span-2">
              <FieldLabel label="Prescriber's diagnosis" />
              <textarea
                className={`${inputClass} resize-none`}
                rows={2}
                placeholder="As written by the doctor, e.g. Uncomplicated cystitis"
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
          subtitle="Optional: microbiological specimen results, if available"
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
