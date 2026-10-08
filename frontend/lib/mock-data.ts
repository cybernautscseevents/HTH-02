/**
 * Realistic mock data for the Antibiotic Stewardship Copilot demo.
 * All data is synthetic — no real patient information.
 *
 * To swap in real API data: set USE_MOCK = false in api.ts.
 */

import type {
  AuditEntry,
  DashboardStats,
  Episode,
  Evaluation,
  ExtractedDrug,
  OCRResult,
  TimeoutItem,
} from '@/types/stewardship'

// ─── OCR Result ────────────────────────────────────────────────────────────────

export const MOCK_OCR_RESULT: OCRResult = {
  success: true,
  raw_text:
    'Rx\nTab. Amoxycillin 500 mg TID × 7 days\nInj. Ceftriaxone 2g IV OD\nTab. Metronidazole 400mg BD × 5 days\nInj. Meropenem 1g IV BD',
  drugs: [
    {
      id: 'dO1',
      raw_text: 'Tab. Amoxycillin 500 mg TID × 7 days',
      generic: 'amoxicillin',
      confidence: 0.97,
      norm_status: 'ACCEPTED',
      norm_candidates: ['amoxicillin'],
      dose_mg: 500,
      freq_per_day: 3,
      route: 'PO',
      duration_days: 7,
    },
    {
      id: 'dO2',
      raw_text: 'Inj. Ceftriaxone 2g IV OD',
      generic: 'ceftriaxone',
      confidence: 0.99,
      norm_status: 'ACCEPTED',
      norm_candidates: ['ceftriaxone'],
      dose_mg: 2000,
      freq_per_day: 1,
      route: 'IV',
      duration_days: null,
    },
    {
      id: 'dO3',
      raw_text: 'Tab. Metronidazole 400mg BD × 5 days',
      generic: 'metronidazole',
      confidence: 0.94,
      norm_status: 'ACCEPTED',
      norm_candidates: ['metronidazole'],
      dose_mg: 400,
      freq_per_day: 2,
      route: 'PO',
      duration_days: 5,
    },
    {
      id: 'dO4',
      raw_text: 'Inj. Meropenem 1g IV BD',
      generic: 'meropenem',
      confidence: 0.41,
      norm_status: 'AMBIGUOUS',
      norm_candidates: ['meropenem', 'ertapenem'],
      dose_mg: 1000,
      freq_per_day: 2,
      route: 'IV',
      duration_days: null,
    },
  ] satisfies ExtractedDrug[],
  processing_time_ms: 1820,
  model: 'Qwen2-VL-7B',
}

// ─── Episode ───────────────────────────────────────────────────────────────────

export const MOCK_EPISODE: Episode = {
  id: 'EP-1024',
  patient: {
    id: 'PT-1024',
    age_years: 68,
    sex: 'M',
    weight_kg: 72,
    serum_creatinine_mg_dl: 1.8,
    allergy_status: 'KNOWN',
    allergies: ['penicillin'],
    pregnant: null,
  },
  setting: 'WARD',
  syndrome_code: 'UTI_COMPLICATED',
  diagnosis_text: 'Complicated urinary tract infection with suspected bacteraemia',
  started_at: '2026-10-06T08:00:00+05:30',
  orders: [
    {
      id: 'dO1',
      raw_text: 'Tab. Amoxycillin 500 mg TID × 7 days',
      generic: 'amoxicillin',
      brand: null,
      norm_status: 'ACCEPTED',
      norm_candidates: ['amoxicillin'],
      dose_mg: 500,
      freq_per_day: 3,
      route: 'PO',
      duration_days: 7,
      started_at: '2026-10-06T08:00:00+05:30',
    },
    {
      id: 'dO2',
      raw_text: 'Inj. Ceftriaxone 2g IV OD',
      generic: 'ceftriaxone',
      brand: null,
      norm_status: 'ACCEPTED',
      norm_candidates: ['ceftriaxone'],
      dose_mg: 2000,
      freq_per_day: 1,
      route: 'IV',
      duration_days: null,
      started_at: '2026-10-06T08:00:00+05:30',
    },
    {
      id: 'dO3',
      raw_text: 'Tab. Metronidazole 400mg BD × 5 days',
      generic: 'metronidazole',
      brand: null,
      norm_status: 'ACCEPTED',
      norm_candidates: ['metronidazole'],
      dose_mg: 400,
      freq_per_day: 2,
      route: 'PO',
      duration_days: 5,
      started_at: '2026-10-06T08:00:00+05:30',
    },
    {
      id: 'dO4',
      raw_text: 'Inj. Meropenem 1g IV BD',
      generic: 'meropenem',
      brand: null,
      norm_status: 'AMBIGUOUS',
      norm_candidates: ['meropenem', 'ertapenem'],
      dose_mg: 1000,
      freq_per_day: 2,
      route: 'IV',
      duration_days: null,
      started_at: '2026-10-06T08:00:00+05:30',
    },
  ],
  specimens: [
    {
      id: 'SP-001',
      specimen_type: 'urine',
      status: 'FINAL',
      collected_at: '2026-10-06T10:00:00+05:30',
      reported_at: '2026-10-07T09:30:00+05:30',
      isolates: [
        {
          id: 'ISO-001',
          organism: 'Escherichia coli',
          probable_contaminant: false,
          susceptibilities: [
            { agent: 'ceftriaxone', result: 'R' },
            { agent: 'meropenem', result: 'S' },
            { agent: 'amoxicillin', result: 'R' },
            { agent: 'trimethoprim-sulfamethoxazole', result: 'S' },
            { agent: 'nitrofurantoin', result: 'S' },
            { agent: 'ciprofloxacin', result: 'I' },
            { agent: 'gentamicin', result: 'S' },
          ],
        },
      ],
    },
  ],
}

// ─── Evaluation ────────────────────────────────────────────────────────────────

export const MOCK_EVALUATION: Evaluation = {
  id: 'EV-20261007-0001',
  episode_id: 'EP-1024',
  evaluated_at: '2026-10-07T14:23:00+05:30',
  trigger: 'CULTURE_RESULT',
  ruleset_version: '1.0.0',
  inputs_hash: 'a3f2c1d9e8b7',
  status: 'FLAGGED',
  findings: [
    {
      rule_id: 'R2_AWARE',
      outcome: 'FLAG',
      severity: 'HIGH',
      order_id: 'dO4',
      message: 'Reserve antibiotic (Meropenem) prescribed without documented escalation criteria.',
      evidence: [
        {
          source_id: 'who-aware-2025',
          title: 'WHO AWaRe Classification of Antibiotics, 2025',
          page: 'Table 3',
          quote:
            'Reserve antibiotics should be used only when all other alternatives have failed or are not suitable.',
          provenance: 'PUBLIC',
        },
      ],
      suggestion: {
        action: 'switch',
        drug: 'trimethoprim-sulfamethoxazole',
        detail:
          'Culture shows E. coli susceptible to co-trimoxazole. Consider de-escalating to an Access antibiotic per ICMR/NCDC guidelines.',
      },
      missing_inputs: [],
    },
    {
      rule_id: 'R1_ALLERGY',
      outcome: 'FLAG',
      severity: 'HIGH',
      order_id: 'dO1',
      message: 'Patient has documented penicillin allergy. Amoxicillin is a penicillin.',
      evidence: [
        {
          source_id: 'icmr-stewardship-2023',
          title: 'ICMR Guidelines for Antibiotic Stewardship, 2023',
          page: '18',
          quote: 'Cross-reactivity between penicillins must be assessed before prescribing.',
          provenance: 'PUBLIC',
        },
      ],
      suggestion: {
        action: 'stop',
        drug: null,
        detail:
          'Stop amoxicillin immediately. Patient has known penicillin allergy. Confirm allergy details and switch to a non-beta-lactam alternative.',
      },
      missing_inputs: [],
    },
    {
      rule_id: 'R5_CULTURE_MISMATCH',
      outcome: 'FLAG',
      severity: 'MODERATE',
      order_id: 'dO2',
      message:
        'Culture report shows E. coli is resistant to Ceftriaxone — the current antibiotic.',
      evidence: [
        {
          source_id: 'urine-culture-SP-001',
          title: 'Urine Culture Report — SP-001',
          page: null,
          quote: 'E. coli: Ceftriaxone — Resistant (R)',
          provenance: 'HOSPITAL',
        },
      ],
      suggestion: {
        action: 'switch',
        drug: 'gentamicin',
        detail:
          'E. coli is susceptible to Gentamicin (S) and co-trimoxazole (S). Review antibiotic choice based on culture susceptibility.',
      },
      missing_inputs: [],
    },
    {
      rule_id: 'R4_RENAL',
      outcome: 'FLAG',
      severity: 'MODERATE',
      order_id: 'dO4',
      message:
        'Meropenem dose may require adjustment. Patient serum creatinine is 1.8 mg/dL (CrCl estimated < 40 mL/min).',
      evidence: [
        {
          source_id: 'drug-prescribing-renal-2024',
          title: 'Drug Prescribing in Renal Failure, 5th Ed.',
          page: '142',
          quote: 'Reduce meropenem dose to 500 mg IV BD when CrCl 25-50 mL/min.',
          provenance: 'PUBLIC',
        },
      ],
      suggestion: {
        action: 'adjust_dose',
        drug: 'meropenem',
        detail:
          'Reduce meropenem to 500 mg IV BD based on estimated renal function. Verify with clinical pharmacist.',
      },
      missing_inputs: [],
    },
    {
      rule_id: 'R0_IDENTIFIED',
      outcome: 'CANNOT_ASSESS',
      severity: 'MODERATE',
      order_id: 'dO4',
      message:
        'Drug identity could not be confirmed — OCR returned ambiguous match (meropenem / ertapenem).',
      evidence: [],
      suggestion: {
        action: 'confirm_drug',
        drug: null,
        detail:
          'Confirm drug identity from the original prescription before applying any stewardship rules.',
      },
      missing_inputs: ['confirmed_drug_identity'],
    },
    {
      rule_id: 'C1_CULTURE_NOT_SENT',
      outcome: 'FLAG',
      severity: 'LOW',
      order_id: null,
      message: 'Antibiotic therapy started without sending blood culture for bacteraemia workup.',
      evidence: [
        {
          source_id: 'icmr-stewardship-2023',
          title: 'ICMR Guidelines for Antibiotic Stewardship, 2023',
          page: '22',
          quote:
            'Blood cultures should be drawn before initiating antibiotic therapy in suspected bacteraemia.',
          provenance: 'PUBLIC',
        },
      ],
      suggestion: {
        action: 'send_culture',
        drug: null,
        detail:
          'Send blood cultures (2 sets) before or within 1 hour of next antibiotic dose if not yet collected.',
      },
      missing_inputs: [],
    },
  ],
  coverage: [],
}

// ─── Recent Episodes / Dashboard ──────────────────────────────────────────────

export const MOCK_STATS: DashboardStats = {
  total_reviewed: 142,
  flagged_count: 31,
  pending_review_count: 8,
  high_severity_count: 12,
  timeout_due_count: 5,
  recent_evaluations: [
    {
      evaluation_id: 'EV-20261007-0001',
      episode_id: 'EP-1024',
      patient_id: 'PT-1024',
      status: 'FLAGGED',
      evaluated_at: '2026-10-07T14:23:00+05:30',
      high_count: 2,
      moderate_count: 2,
    },
    {
      evaluation_id: 'EV-20261007-0002',
      episode_id: 'EP-1021',
      patient_id: 'PT-1021',
      status: 'OK',
      evaluated_at: '2026-10-07T12:05:00+05:30',
      high_count: 0,
      moderate_count: 0,
    },
    {
      evaluation_id: 'EV-20261007-0003',
      episode_id: 'EP-1019',
      patient_id: 'PT-1019',
      status: 'FLAGGED',
      evaluated_at: '2026-10-07T09:50:00+05:30',
      high_count: 1,
      moderate_count: 3,
    },
    {
      evaluation_id: 'EV-20261006-0012',
      episode_id: 'EP-1018',
      patient_id: 'PT-1018',
      status: 'INCOMPLETE',
      evaluated_at: '2026-10-06T18:30:00+05:30',
      high_count: 1,
      moderate_count: 0,
    },
    {
      evaluation_id: 'EV-20261006-0011',
      episode_id: 'EP-1016',
      patient_id: 'PT-1016',
      status: 'OK',
      evaluated_at: '2026-10-06T15:15:00+05:30',
      high_count: 0,
      moderate_count: 0,
    },
  ],
}

// ─── 48-hour Timeout Queue ─────────────────────────────────────────────────────

export const MOCK_TIMEOUTS: TimeoutItem[] = [
  {
    episode_id: 'EP-1024',
    patient_id: 'PT-1024',
    setting: 'WARD',
    antibiotic_name: 'Ceftriaxone, Meropenem',
    started_at: '2026-10-06T08:00:00+05:30',
    hours_elapsed: 54,
    status: 'REVIEW_DUE',
  },
  {
    episode_id: 'EP-1017',
    patient_id: 'PT-1017',
    setting: 'ICU',
    antibiotic_name: 'Piperacillin-Tazobactam',
    started_at: '2026-10-05T22:00:00+05:30',
    hours_elapsed: 76,
    status: 'REVIEW_DUE',
  },
  {
    episode_id: 'EP-1015',
    patient_id: 'PT-1015',
    setting: 'WARD',
    antibiotic_name: 'Vancomycin',
    started_at: '2026-10-05T14:00:00+05:30',
    hours_elapsed: 96,
    status: 'REVIEW_DUE',
  },
  {
    episode_id: 'EP-1013',
    patient_id: 'PT-1013',
    setting: 'OPD',
    antibiotic_name: 'Azithromycin',
    started_at: '2026-10-04T10:00:00+05:30',
    hours_elapsed: 124,
    status: 'REVIEW_DUE',
  },
  {
    episode_id: 'EP-1011',
    patient_id: 'PT-1011',
    setting: 'WARD',
    antibiotic_name: 'Ciprofloxacin',
    started_at: '2026-10-05T08:00:00+05:30',
    hours_elapsed: 82,
    status: 'REVIEW_DUE',
  },
]

// ─── Audit Log ─────────────────────────────────────────────────────────────────

export const MOCK_AUDIT_LOG: AuditEntry[] = [
  {
    at: '2026-10-07T15:12:00+05:30',
    actor: 'Dr. Priya Mehta (Pharmacist)',
    action: 'review.OVERRIDE',
    entity: 'finding',
    entity_id: 'EV-20261006-0012:R2_AWARE:dO4',
    payload: {
      reason_code: 'CLINICAL_JUDGEMENT',
      note: 'Patient previously failed cephalosporins; Reserve antibiotic use is appropriate in this context. Discussed with attending physician.',
      action: 'OVERRIDE',
    },
  },
  {
    at: '2026-10-07T14:50:00+05:30',
    actor: 'Dr. Suresh Kumar (Pharmacist)',
    action: 'review.ACCEPT',
    entity: 'finding',
    entity_id: 'EV-20261007-0001:R5_CULTURE_MISMATCH:dO2',
    payload: {
      reason_code: null,
      note: 'Culture confirmed — switching recommendation accepted.',
      action: 'ACCEPT',
    },
  },
  {
    at: '2026-10-07T13:30:00+05:30',
    actor: 'System',
    action: 'evaluation.created',
    entity: 'evaluation',
    entity_id: 'EV-20261007-0001',
    payload: {
      trigger: 'CULTURE_RESULT',
      status: 'FLAGGED',
      findings_count: 6,
    },
  },
  {
    at: '2026-10-06T18:45:00+05:30',
    actor: 'Dr. Ananya Singh (Pharmacist)',
    action: 'review.MODIFY',
    entity: 'finding',
    entity_id: 'EV-20261006-0012:R4_RENAL:dO3',
    payload: {
      reason_code: 'PATIENT_FACTOR',
      note: 'Dose reduced to 250 mg BD after discussion with nephrology. Patient stable.',
      action: 'MODIFY',
    },
  },
  {
    at: '2026-10-06T10:00:00+05:30',
    actor: 'System',
    action: 'evaluation.created',
    entity: 'evaluation',
    entity_id: 'EV-20261006-0012',
    payload: {
      trigger: 'NEW_PRESCRIPTION',
      status: 'INCOMPLETE',
      findings_count: 3,
    },
  },
]
