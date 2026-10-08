'use client'

import React, { useCallback, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  Upload,
  FileImage,
  X,
  ArrowRight,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  Zap,
} from 'lucide-react'
import { uploadPrescription } from '@/lib/api'
import type { ExtractedDrug, OCRResult } from '@/types/stewardship'
import { Button } from '@/components/ui/Button'
import { DrugOrderRow } from '@/components/stewardship/DrugOrderRow'

type Step = 'upload' | 'processing' | 'review'

export default function UploadPage() {
  const router = useRouter()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [step, setStep] = useState<Step>('upload')
  const [dragging, setDragging] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [ocrResult, setOcrResult] = useState<OCRResult | null>(null)
  const [drugs, setDrugs] = useState<ExtractedDrug[]>([])
  const [error, setError] = useState<string | null>(null)

  const handleFile = useCallback(async (f: File) => {
    if (!f.type.startsWith('image/')) {
      setError('Please upload an image file (JPEG, PNG, or TIFF).')
      return
    }
    setError(null)
    setFile(f)
    setPreview(URL.createObjectURL(f))
    setStep('processing')

    try {
      const result = await uploadPrescription(f)
      setOcrResult(result)
      setDrugs(result.drugs)
      setStep('review')
    } catch (e) {
      setError('OCR processing failed. Please try again.')
      setStep('upload')
    }
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      const f = e.dataTransfer.files[0]
      if (f) handleFile(f)
    },
    [handleFile]
  )

  const handleConfirmDrug = (id: string, confirmed: string) => {
    setDrugs((prev) =>
      prev.map((d) =>
        d.id === id
          ? { ...d, generic: confirmed, norm_status: 'CONFIRMED', norm_candidates: [] }
          : d
      )
    )
  }

  const handleProceed = () => {
    // Store drugs in sessionStorage so the episode form can pick them up
    sessionStorage.setItem('pendingDrugs', JSON.stringify(drugs))
    sessionStorage.setItem('ocrRawText', ocrResult?.raw_text ?? '')
    router.push('/episode/new')
  }

  const ambiguousCount = drugs.filter((d) => d.norm_status === 'AMBIGUOUS').length
  const noMatchCount = drugs.filter((d) => d.norm_status === 'NO_MATCH').length
  const canProceed = drugs.length > 0 && noMatchCount === 0

  return (
    <div className="space-y-6 animate-fade-in max-w-3xl">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-100">New Prescription</h1>
        <p className="text-sm text-slate-400 mt-0.5">
          Upload a prescription image to extract drug orders and run stewardship evaluation
        </p>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-2 text-xs">
        {(['upload', 'processing', 'review'] as Step[]).map((s, i) => (
          <React.Fragment key={s}>
            <div
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full border transition-all ${
                step === s
                  ? 'bg-indigo-500/20 border-indigo-500/40 text-indigo-300 font-semibold'
                  : step === 'review' && i < 2
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                  : step === 'processing' && i < 1
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                  : 'border-[#2d3148] text-slate-500'
              }`}
            >
              {step === 'review' && i < 2 ? (
                <CheckCircle2 className="w-3.5 h-3.5" />
              ) : (
                <span>{i + 1}</span>
              )}
              <span className="capitalize">{s === 'processing' ? 'OCR Processing' : s}</span>
            </div>
            {i < 2 && <div className="h-px w-4 bg-[#2d3148]" />}
          </React.Fragment>
        ))}
      </div>

      {/* Step 1: Upload zone */}
      {step === 'upload' && (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`relative rounded-2xl border-2 border-dashed transition-all cursor-pointer p-12 text-center ${
            dragging
              ? 'border-indigo-500/60 bg-indigo-500/10'
              : 'border-[#2d3148] hover:border-[#3b4263] bg-[#1e2235]'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) handleFile(f)
            }}
          />

          <div className="flex flex-col items-center gap-4">
            <div className="w-16 h-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
              <FileImage className="w-8 h-8 text-indigo-400" />
            </div>
            <div>
              <p className="text-base font-semibold text-slate-100">
                Drop prescription image here
              </p>
              <p className="text-sm text-slate-400 mt-1">or click to browse — JPEG, PNG, TIFF</p>
            </div>
            <Button variant="outline" size="sm" leftIcon={<Upload className="w-4 h-4" />}>
              Choose file
            </Button>
          </div>

          {error && (
            <div className="mt-4 flex items-center gap-2 text-sm text-rose-400">
              <AlertTriangle className="w-4 h-4" />
              {error}
            </div>
          )}
        </div>
      )}

      {/* Step 2: Processing */}
      {step === 'processing' && (
        <div className="rounded-2xl border border-[#2d3148] bg-[#1e2235] overflow-hidden">
          {/* Image preview */}
          {preview && (
            <div className="border-b border-[#2d3148] bg-[#141724] p-4 flex items-center gap-4">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={preview}
                alt="Prescription preview"
                className="w-24 h-24 object-cover rounded-lg border border-[#2d3148]"
              />
              <div>
                <p className="text-sm font-semibold text-slate-100">{file?.name}</p>
                <p className="text-xs text-slate-400 mt-0.5">
                  {file ? `${(file.size / 1024).toFixed(1)} KB` : ''}
                </p>
              </div>
            </div>
          )}

          {/* Processing animation */}
          <div className="p-10 flex flex-col items-center gap-4 text-center">
            <div className="relative">
              <div className="w-16 h-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
                <Zap className="w-8 h-8 text-indigo-400" />
              </div>
              <Loader2 className="absolute -top-2 -right-2 w-6 h-6 text-indigo-400 animate-spin" />
            </div>
            <div>
              <p className="text-base font-semibold text-slate-100">OCR Processing...</p>
              <p className="text-sm text-slate-400 mt-1">
                Extracting drug orders from prescription image
              </p>
            </div>
            <div className="flex gap-1 mt-2">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="w-2 h-2 rounded-full bg-indigo-500 animate-bounce"
                  style={{ animationDelay: `${i * 0.15}s` }}
                />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Step 3: Review extracted drugs */}
      {step === 'review' && ocrResult && (
        <div className="space-y-4">
          {/* Image + raw text */}
          <div className="rounded-xl border border-[#2d3148] bg-[#1e2235] overflow-hidden">
            <div className="px-5 py-3 border-b border-[#2d3148] flex items-center justify-between">
              <p className="text-sm font-semibold text-slate-100">Prescription Image</p>
              <button
                onClick={() => {
                  setStep('upload')
                  setFile(null)
                  setPreview(null)
                  setOcrResult(null)
                  setDrugs([])
                }}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-[#2d3148] transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-4 flex gap-4 flex-wrap">
              {preview && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={preview}
                  alt="Prescription"
                  className="max-h-48 rounded-lg border border-[#2d3148] object-contain"
                />
              )}
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-slate-400 mb-2">Raw OCR text</p>
                <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap bg-[#141724] rounded-lg p-3 border border-[#2d3148] max-h-40 overflow-y-auto">
                  {ocrResult.raw_text}
                </pre>
                <p className="text-[11px] text-slate-500 mt-2">
                  Processed in {ocrResult.processing_time_ms}ms
                  {ocrResult.model && ` · ${ocrResult.model}`}
                </p>
              </div>
            </div>
          </div>

          {/* Extracted drugs */}
          <div className="rounded-xl border border-[#2d3148] bg-[#1e2235] overflow-hidden">
            <div className="px-5 py-3 border-b border-[#2d3148] flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-slate-100">Extracted Medicines</p>
                <p className="text-xs text-slate-400">{drugs.length} drug orders identified</p>
              </div>
              <div className="flex gap-2">
                {ambiguousCount > 0 && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30">
                    {ambiguousCount} need confirmation
                  </span>
                )}
                {noMatchCount > 0 && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-rose-500/15 text-rose-400 border border-rose-500/30">
                    {noMatchCount} unmatched
                  </span>
                )}
              </div>
            </div>

            <div className="p-4 space-y-3">
              {drugs.map((drug) => (
                <DrugOrderRow key={drug.id} drug={drug} onConfirm={handleConfirmDrug} />
              ))}
            </div>
          </div>

          {/* CTA */}
          <div className="flex items-center justify-between pt-2">
            <p className="text-xs text-slate-400">
              {ambiguousCount > 0
                ? `⚠ Confirm ${ambiguousCount} ambiguous drug(s) before proceeding`
                : '✓ All drugs confirmed — ready to proceed'}
            </p>
            <Button
              variant="primary"
              size="md"
              rightIcon={<ArrowRight className="w-4 h-4" />}
              disabled={!canProceed}
              onClick={handleProceed}
            >
              Proceed to patient information
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
