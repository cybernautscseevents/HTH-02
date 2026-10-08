'use client'

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileImage,
  FileText,
  Loader2,
  RotateCcw,
  Upload,
  Zap,
} from 'lucide-react'
import { parsePrescriptionText, uploadPrescription } from '@/lib/api'
import type { ExtractedDrug, OCRResult } from '@/types/stewardship'
import { Button } from '@/components/ui/Button'
import { DrugOrderRow } from '@/components/stewardship/DrugOrderRow'
import { WorkflowStepper } from '@/components/stewardship/WorkflowStepper'

type Mode = 'image' | 'typed'

// The demo images are named after the patient, e.g. SYN-DEMO-01_concordant.png -> SYN-DEMO-01.
// A name with no digit before the first underscore (IMG_1234.jpg) is not treated as an ID.
function patientIdFromFileName(name: string): string | null {
  const stem = name.replace(/\.[^.]+$/, '').split(/[_\s]/)[0].trim()
  return /\d/.test(stem) ? stem : null
}
type Step = 'input' | 'processing' | 'review'

export default function UploadPage() {
  const router = useRouter()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [mode, setMode] = useState<Mode>('image')
  const [step, setStep] = useState<Step>('input')
  const [engine, setEngine] = useState<'glm' | 'qwen'>('glm')
  const [dragging, setDragging] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [typedText, setTypedText] = useState('')
  const [result, setResult] = useState<OCRResult | null>(null)
  const [drugs, setDrugs] = useState<ExtractedDrug[]>([])
  const [error, setError] = useState<string | null>(null)
  const [fileId, setFileId] = useState<string | null>(null)

  // Back from the clinical-context step reopens the reviewed prescription instead of an empty
  // form. A plain visit to this page always starts a new prescription.
  useEffect(() => {
    if (!new URLSearchParams(window.location.search).has('back')) return
    try {
      const saved = sessionStorage.getItem('rxReview')
      if (!saved) return
      const review: { mode: Mode; typedText: string; result: OCRResult; drugs: ExtractedDrug[]; fileId?: string | null } = JSON.parse(saved)
      setFileId(review.fileId ?? null)
      setMode(review.mode)
      setTypedText(review.typedText)
      setResult(review.result)
      setDrugs(review.drugs)
      setStep('review')
    } catch {
      /* start a new prescription */
    }
  }, [])

  const handleFile = useCallback(async (selected: File) => {
    if (!selected.type.startsWith('image/')) {
      setError('Upload a JPEG, PNG, TIFF, or WebP prescription image.')
      return
    }
    setError(null)
    setFile(selected)
    setFileId(patientIdFromFileName(selected.name))
    setPreview(URL.createObjectURL(selected))
    setStep('processing')
    try {
      const response = await uploadPrescription(selected, engine)
      setResult(response)
      setDrugs(response.drugs)
      setStep('review')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'OCR processing failed.')
      setStep('input')
    }
  }, [engine])

  const handleTyped = async () => {
    if (!typedText.trim()) {
      setError('Enter at least one medicine line.')
      return
    }
    setError(null)
    setStep('processing')
    try {
      const parsed = await parsePrescriptionText(typedText)
      setDrugs(parsed.orders)
      setResult({
        success: true,
        raw_text: typedText,
        drugs: parsed.orders,
        processing_time_ms: 0,
        model: 'Typed input',
        warnings: parsed.warnings,
        diagnosis: parsed.diagnosis,
        patient: parsed.patient,
      })
      setStep('review')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Prescription parsing failed.')
      setStep('input')
    }
  }

  const confirmDrug = (id: string, generic: string) => {
    setDrugs((current) =>
      current.map((drug) =>
        drug.id === id
          ? { ...drug, generic, norm_status: 'CONFIRMED', norm_candidates: [], excluded: false }
          : drug
      )
    )
  }

  const excludeDrug = (id: string) => {
    setDrugs((current) =>
      current.map((drug) => (drug.id === id ? { ...drug, excluded: true } : drug))
    )
  }

  const reset = () => {
    setStep('input')
    setFile(null)
    setFileId(null)
    setPreview(null)
    setResult(null)
    setDrugs([])
    setError(null)
  }

  const proceed = () => {
    const activeDrugs = drugs.filter((drug) => !drug.excluded)
    sessionStorage.setItem('pendingDrugs', JSON.stringify(activeDrugs))
    sessionStorage.setItem('rxReview', JSON.stringify({ mode, typedText, result, drugs, fileId }))
    sessionStorage.setItem('ocrRawText', result?.raw_text ?? typedText)
    if (result?.diagnosis) sessionStorage.setItem('rxDiagnosis', JSON.stringify(result.diagnosis))
    else sessionStorage.removeItem('rxDiagnosis')
    const idFromFile = mode === 'image' ? fileId : null
    const patientId = idFromFile ?? result?.patient?.id ?? null
    if (patientId || result?.patient?.name) {
      sessionStorage.setItem(
        'rxPatient',
        JSON.stringify({ id: patientId, name: result?.patient?.name ?? null, from: idFromFile ? 'file' : 'prescription' })
      )
    }
    else sessionStorage.removeItem('rxPatient')
    router.push('/episode/new')
  }

  const activeDrugs = drugs.filter((drug) => !drug.excluded)
  const ambiguous = activeDrugs.filter((drug) => drug.norm_status === 'AMBIGUOUS').length
  const unmatched = activeDrugs.filter((drug) => drug.norm_status === 'NO_MATCH').length
  const ready = activeDrugs.length > 0 && ambiguous === 0 && unmatched === 0

  return (
    <div className="mx-auto max-w-4xl space-y-6 animate-fade-in">
      <div className="flex flex-col justify-between gap-3 border-b border-[#E2E1DC] pb-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-[#6B6A65]">New stewardship review</p>
          <h1 className="mt-1 text-2xl font-medium tracking-[-0.02em] text-[#1A1A1A]">Start with the prescription</h1>
          <p className="mt-1 text-sm text-[#6B6A65]">
            Upload an image or paste typed orders. You will verify extraction before clinical analysis.
          </p>
        </div>
        <span className="text-xs text-[#6B6A65]">Step 1 of 5</span>
      </div>

      <WorkflowStepper current={1} />

      {step === 'input' && (
        <section className="overflow-hidden rounded-[8px] border border-[#E2E1DC] bg-white shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <div className="flex border-b border-[#E2E1DC] bg-[#F4F3EF] p-1">
            {([
              ['image', FileImage, 'Image upload'],
              ['typed', FileText, 'Typed prescription'],
            ] as const).map(([value, Icon, label]) => (
              <button
                key={value}
                onClick={() => { setMode(value); setError(null) }}
                className={`flex flex-1 items-center justify-center gap-2 rounded-md px-3 py-2 text-xs font-medium transition-colors ${
                  mode === value ? 'bg-white text-[#1A1A1A] shadow-sm' : 'text-[#6B6A65] hover:text-[#1A1A1A]'
                }`}
              >
                <Icon className="h-4 w-4" /> {label}
              </button>
            ))}
          </div>

          {mode === 'image' ? (
            <div className="p-5">
              <div className="mb-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                <div>
                  <h2 className="text-sm font-medium text-[#1A1A1A]">Prescription image</h2>
                  <p className="text-xs text-[#6B6A65]">The selected OCR engine extracts text; the drug catalog decides identity.</p>
                </div>
                <label className="flex items-center gap-2 text-xs text-[#6B6A65]">
                  OCR engine
                  <select
                    value={engine}
                    onChange={(event) => setEngine(event.target.value as 'glm' | 'qwen')}
                    className="rounded-md border border-[#C8C7C0] bg-white px-2.5 py-1.5 text-xs text-[#1A1A1A] outline-none focus:border-[#3730A3]"
                  >
                    <option value="glm">GLM-OCR</option>
                    <option value="qwen">Qwen-VL</option>
                  </select>
                </label>
              </div>
              <div
                onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
                onDragLeave={() => setDragging(false)}
                onDrop={(event) => {
                  event.preventDefault()
                  setDragging(false)
                  const selected = event.dataTransfer.files[0]
                  if (selected) handleFile(selected)
                }}
                onClick={() => fileInputRef.current?.click()}
                className={`cursor-pointer rounded-[8px] border border-dashed p-10 text-center transition-colors ${
                  dragging ? 'border-[#3730A3] bg-[#F4F2FC]' : 'border-[#C8C7C0] bg-[#FAFAF8] hover:border-[#6B6A65]'
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/tiff,image/webp"
                  className="hidden"
                  onChange={(event) => {
                    const selected = event.target.files?.[0]
                    if (selected) handleFile(selected)
                  }}
                />
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-md border border-[#E2E1DC] bg-white text-[#1A1A1A]">
                  <Upload className="h-5 w-5" />
                </div>
                <p className="mt-4 text-sm font-medium text-[#1A1A1A]">Drop a prescription image here</p>
                <p className="mt-1 text-xs text-[#6B6A65]">JPEG, PNG, TIFF or WebP · maximum 15 MB</p>
                <Button className="mt-4" variant="outline" size="sm">Choose image</Button>
              </div>
            </div>
          ) : (
            <div className="p-5">
              <h2 className="text-sm font-medium text-[#1A1A1A]">Typed prescription</h2>
              <p className="mt-0.5 text-xs text-[#6B6A65]">Paste the prescription as the doctor wrote it: the &quot;Diagnosis:&quot; line, then one medicine per line with dose, route, frequency and duration.</p>
              <textarea
                value={typedText}
                onChange={(event) => setTypedText(event.target.value)}
                rows={7}
                placeholder={'Diagnosis: Uncomplicated cystitis\nRx\nTab Nitrofurantoin 100 mg PO BD x 5 days\nTab Paracetamol 500 mg PO TDS x 3 days'}
                className="mt-4 w-full resize-y rounded-md border border-[#C8C7C0] bg-white px-3 py-2.5 font-mono text-sm text-[#1A1A1A] outline-none placeholder:text-[#8B8982] focus:border-[#3730A3] focus:ring-2 focus:ring-[#3730A3]/10"
              />
              <div className="mt-4 flex justify-end">
                <Button onClick={handleTyped} rightIcon={<ArrowRight className="h-4 w-4" />}>Parse orders</Button>
              </div>
            </div>
          )}
          {error && (
            <div className="mx-5 mb-5 flex items-start gap-2 rounded-md border border-[#D9A4A4] bg-[#FDF2F2] p-3 text-xs text-[#8B1A1A]">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {error}
            </div>
          )}
        </section>
      )}

      {step === 'processing' && (
        <section className="rounded-[8px] border border-[#E2E1DC] bg-white p-12 text-center shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-md bg-[#F4F2FC] text-[#3730A3]">
            {mode === 'image' ? <Zap className="h-5 w-5" /> : <FileText className="h-5 w-5" />}
          </div>
          <Loader2 className="mx-auto mt-4 h-5 w-5 animate-spin text-[#3730A3]" />
          <p className="mt-3 text-sm font-medium text-[#1A1A1A]">
            {mode === 'image' ? 'Reading prescription image' : 'Structuring medication orders'}
          </p>
          <p className="mt-1 text-xs text-[#6B6A65]">No clinical rule runs until you verify these results.</p>
        </section>
      )}

      {step === 'review' && result && (
        <div className="space-y-4">
          <section className="overflow-hidden rounded-[8px] border border-[#E2E1DC] bg-white shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
            <div className="flex items-center justify-between border-b border-[#E2E1DC] px-5 py-4">
              <div>
                <h2 className="text-sm font-medium text-[#1A1A1A]">Verify extraction</h2>
                <p className="text-xs text-[#6B6A65]">Compare every line with the source before continuing.</p>
              </div>
              <Button variant="ghost" size="sm" leftIcon={<RotateCcw className="h-3.5 w-3.5" />} onClick={reset}>Start again</Button>
            </div>
            <div className="grid gap-4 border-b border-[#E2E1DC] p-5 md:grid-cols-[220px_1fr]">
              {preview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={preview} alt="Uploaded prescription" className="max-h-56 w-full rounded-md border border-[#E2E1DC] object-contain" />
              ) : (
                <div className="flex min-h-36 items-center justify-center rounded-md border border-[#E2E1DC] bg-[#F4F3EF] text-[#6B6A65]">
                  <FileText className="h-8 w-8" />
                </div>
              )}
              <div className="min-w-0">
                <p className="text-xs font-medium uppercase tracking-wider text-[#6B6A65]">Source text</p>
                <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded-md border border-[#E2E1DC] bg-[#FAFAF8] p-3 font-mono text-xs text-[#1A1A1A]">{result.raw_text}</pre>
                <p className="mt-2 text-xs text-[#6B6A65]">{result.model}{result.processing_time_ms ? ` · ${result.processing_time_ms} ms` : ''}</p>
                <p className="mt-3 text-xs font-medium uppercase tracking-wider text-[#6B6A65]">Patient</p>
                {mode === 'image' && fileId && (
                  <p className="mt-1 text-sm text-[#1A1A1A]">
                    ID from file name
                    <span className="ml-2 font-mono text-xs text-[#6B6A65]">{fileId}</span>
                  </p>
                )}
                {result.patient?.id || result.patient?.name ? (
                  <p className="mt-1 text-sm text-[#1A1A1A]">
                    {result.patient.name ?? 'Name not printed'}
                    <span className="ml-2 font-mono text-xs text-[#6B6A65]">{result.patient.id ?? 'no ID printed'}</span>
                  </p>
                ) : !(mode === 'image' && fileId) ? (
                  <p className="mt-1 text-xs text-[#8B5E00]">No patient ID or name found on the prescription. Enter the ID on the next step.</p>
                ) : null}
                <p className="mt-3 text-xs font-medium uppercase tracking-wider text-[#6B6A65]">Prescriber&apos;s diagnosis</p>
                {result.diagnosis?.text ? (
                  <p className="mt-1 text-sm text-[#1A1A1A]">
                    {result.diagnosis.text}
                    <span className="block text-xs text-[#6B6A65]">
                      {result.diagnosis.syndrome_name
                        ? `Reads as guideline syndrome: ${result.diagnosis.syndrome_name}`
                        : `${result.diagnosis.note ?? ''} You will select the syndrome on the next step.`}
                    </span>
                  </p>
                ) : (
                  <p className="mt-1 text-xs text-[#8B5E00]">
                    No diagnosis is written on the prescription. The indication will be flagged as undocumented unless you select a syndrome.
                  </p>
                )}
              </div>
            </div>
            <div className="p-5">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="text-sm font-medium text-[#1A1A1A]">Medication orders</h3>
                  <p className="text-xs text-[#6B6A65]">{drugs.length} line{drugs.length === 1 ? '' : 's'} detected</p>
                </div>
                <div className="flex gap-2 text-xs">
                  {ambiguous > 0 && <span className="rounded-full border border-[#E8D5A7] bg-[#FFF9EB] px-2 py-0.5 text-[#8B5E00]">{ambiguous} ambiguous</span>}
                  {unmatched > 0 && <span className="rounded-full border border-[#D9A4A4] bg-[#FDF2F2] px-2 py-0.5 text-[#8B1A1A]">{unmatched} unmatched</span>}
                </div>
              </div>
              <div className="space-y-3">
                {drugs.map((drug) => (
                  <DrugOrderRow
                    key={drug.id}
                    drug={drug}
                    onConfirm={confirmDrug}
                    onExclude={excludeDrug}
                  />
                ))}
              </div>
            </div>
          </section>

          <div className="flex flex-col justify-between gap-3 rounded-[8px] border border-[#E2E1DC] bg-white p-4 sm:flex-row sm:items-center">
            <div className="flex items-center gap-2 text-xs">
              {ready ? (
                <><CheckCircle2 className="h-4 w-4 text-[#1A6B3C]" /><span className="text-[#1A6B3C]">Verified orders are ready for clinical context.</span></>
              ) : (
                <><AlertTriangle className="h-4 w-4 text-[#8B5E00]" /><span className="text-[#8B5E00]">Resolve {ambiguous + unmatched} order{ambiguous + unmatched === 1 ? '' : 's'} before continuing.</span></>
              )}
            </div>
            <Button disabled={!ready} onClick={proceed} rightIcon={<ArrowRight className="h-4 w-4" />}>Continue to clinical context</Button>
          </div>
        </div>
      )}
    </div>
  )
}
