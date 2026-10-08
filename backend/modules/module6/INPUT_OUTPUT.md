# Module 6: Antibiotic Stewardship Checker — Input & Output Reference

## Inputs

Module 6 receives the following inputs:

---

### 1. Normalized Drug List (`drug_list`)

**Source**: Module 3 — Drug Normalization Pipeline

**Type**: `list[dict[str, Any]]`

**Description**: Normalized drug list with generic names, corrected names, and structured dose/route/frequency fields from the drug normalization pipeline (Module 3).

**Required fields per drug entry**:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `generic` | str | Generic name of the drug | `"amoxicillin"` |
| `corrected_name` | str | Corrected/standardized drug name | `"amoxicillin"` |
| `structured` | dict | Structured dosage information | `{"dose": "500mg", "route": "oral", "frequency": "TID"}` |
| `structured.dose` | str | Prescribed dose string | `"500mg"`, `"2g"`, `"160/800mg"` |
| `structured.route` | str | Administration route | `"oral"`, `"IV"`, `"IM"` |
| `structured.frequency` | str | Dosing frequency | `"TID"`, `"BID"`, `"QID"` |
| `structured.duration` | str (optional) | Treatment duration | `"7 days"` |

**Example Input**:
```json
{
  "drug_list": [
    {
      "generic": "amoxicillin",
      "corrected_name": "amoxicillin",
      "structured": {
        "dose": "500mg",
        "route": "oral",
        "frequency": "TID",
        "duration": "7 days"
      }
    },
    {
      "generic": "paracetamol",
      "corrected_name": "paracetamol",
      "structured": {
        "dose": "500mg",
        "route": "oral",
        "frequency": "TID"
      }
    }
  ]
}
```

---

### 2. Clinical Diagnosis (`diagnosis`)

**Type**: `str`

**Description**: Clinical diagnosis string for indication matching against built-in antibiotic guidelines covering 12 diagnosis categories.

**Supported diagnosis categories**:
- pneumonia
- UTI / urinary tract infection
- skin infection
- throat infection
- respiratory tract infection
- sepsis
- meningitis
- sinusitis
- otitis media
- bronchitis
- cellulitis

**Example**: `"pneumonia"`, `"urinary tract infection"`, `"uti"`

---

### 3. Hospital Antibiotic Policy JSON (`policy_json_path`)

**Type**: `str` (file path)

**Description**: Hospital antibiotic policy JSON loaded from a configurable path via the `HOSPITAL_ANTIBIOTIC_POLICY_JSON` environment variable. The JSON contains structured `policy_sections` with diagnosis variants, antibiotic recommendations (first_line, alternatives, severe_hospitalized, avoid), dose ranges, evidence levels, and stewardship alerts.

**Fallback behavior**: Falls back to hardcoded `INDICATION_ANTIBIOTICS` guidelines if the JSON is unavailable.

**Environment variable**: `HOSPITAL_ANTIBIOTIC_POLICY_JSON`
**Default**: `hospital_policy_template.json` in the module directory

**Expected JSON Structure**:
```json
{
  "hospital_antibiotic_policy": {
    "policy_sections": [
      {
        "diagnosis": "Pneumonia",
        "variants": ["pneumonia", "community-acquired pneumonia", "CAP"],
        "antibiotic_recommendations": {
          "first_line": [
            {
              "drug": "amoxicillin",
              "dose_range": "500-1000 mg",
              "frequency": "TID",
              "duration": "5-7 days",
              "route": "oral",
              "spectrum": "narrow",
              "evidence_level": "A",
              "notes": "First-line for community-acquired pneumonia"
            }
          ],
          "alternatives": [
            {
              "drug": "azithromycin",
              "dose_range": "500mg day 1, then 250mg",
              "frequency": "daily",
              "duration": "5 days",
              "route": "oral",
              "spectrum": "narrow",
              "evidence_level": "A"
            }
          ],
          "severe_hospitalized": [
            {
              "drug": "ceftriaxone",
              "dose_range": "1-2g",
              "frequency": "daily",
              "duration": "7-10 days",
              "route": "IV",
              "spectrum": "broad",
              "evidence_level": "A",
              "notes": "Reserved for severe/hospitalized cases"
            }
          ],
          "avoid": []
        }
      }
    ]
  }
}
```

---

### 4. Mistral LLM Model (`model`, `host`)

**Type**: `str`

**Description**: Mistral-7B instruct model (`mistral:7b-instruct-q4_K_M`) served locally via Ollama at a configurable host and port, with `temperature=0.3` and `top_p=0.9`. Used for clinical reasoning; gracefully falls back when unavailable.

**Parameters**:
| Parameter | Environment Variable | Default |
|-----------|---------------------|---------|
| Ollama Host | `OLLAMA_HOST` | `http://localhost:11434` |
| Model | `MISTRAL_MODEL` | `mistral:7b-instruct-q4_K_M` |
| Timeout | `STEWARDSHIP_TIMEOUT` | `120` seconds |

---

### 5. Patient Demographics (Optional)

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `patient_age` | int \| None | Patient age for enriched LLM reasoning context | `45` |
| `patient_gender` | str \| None | Patient gender (M/F) | `"M"`, `"F"` |

---

### 6. Built-in Classification Maps (Internal)

These are internal to the module and not passed as parameters:

**Antibiotic Spectrum Classification**:
| Spectrum | Drug Count | Examples |
|----------|------------|----------|
| Narrow | 11 drugs | penicillin V/G, oxacillin, nafcillin, methicillin, cloxacillin, dicloxacillin, amoxicillin, erythromycin, azithromycin, clarithromycin |
| Moderate | 11 drugs | amoxicillin-clavulanate, augmentin, cephalexin, cefadroxil, cefuroxime, cefixime, ciprofloxacin, levofloxacin, trimethoprim-sulfamethoxazole, bactrim, cotrim |
| Broad | 10 drugs | piperacillin-tazobactam, zosyn, meropenem, ertapenem, imipenem, ceftriaxone, cefotaxime, cefepime, ceftazidime, aztreonam |

**Keyword-based heuristic fallback**: Unknown drug names classified via keywords:
- `"carbapenem"` → broad
- `"fluoroquinolone"` → moderate

---

## Outputs

The module generates a structured JSON stewardship assessment with the following schema:

---

### Top-Level Response Structure

```json
{
  "antibiotics_detected": [...],
  "summary": {...},
  "error": null
}
```

| Field | Type | Description |
|-------|------|-------------|
| `antibiotics_detected` | list[dict] | Array of per-drug stewardship assessments |
| `summary` | dict | Aggregate assessment summary |
| `error` | str \| null | Top-level error message (null if successful) |

---

### Per-Drug Assessment (`antibiotics_detected` array elements)

Each element in the array contains:

| Field | Type | Description |
|-------|------|-------------|
| `drug` | str | Generic name of the antibiotic assessed |
| `antibiotic_needed` | bool \| null | Whether the antibiotic is indicated for the diagnosis. `true` = indicated, `false` = not needed, `null` = uncertain/unknown diagnosis |
| `policy_compliant` | bool | `true` if the drug adheres to hospital antibiotic policy |
| `spectrum_appropriate` | bool | `false` when broad-spectrum use is not clinically justified |
| `spectrum_type` | str | `"narrow"`, `"moderate"`, `"broad"`, or `"unknown"` |
| `policy_source` | str | `"json_policy"`, `"guidelines"`, or `"fallback"` |
| `dose_issues` | list[str] | Dose validation issues (empty list if no issues) |
| `prescribed_dose` | str \| null | The prescribed dose string (e.g., `"500mg"`) or null |
| `recommended_dose` | str \| null | The policy-recommended dose range (e.g., `"500-1000 mg"`) or null |
| `llm_reasoning` | dict \| str | Mistral LLM analysis object (see LLM Reasoning below) |
| `recommendation` | str | Actionable clinical guidance string with alternative suggestions |
| `needs_review` | bool | `true` when mandatory pharmacist consultation is required |
| `confidence` | float | 0.0 to 1.0 reflecting assessment reliability |

#### LLM Reasoning Object

| Field | Type | Description |
|-------|------|-------------|
| `appropriate` | bool \| null | Whether the antibiotic is appropriate for the diagnosis |
| `spectrum_justified` | bool \| null | Whether the spectrum choice is clinically justified |
| `rationale` | str | Brief clinical explanation |
| `alternatives` | list[str] | Suggested alternative antibiotics (empty if none) |
| `concerns` | list[str] | Clinical concerns identified (empty if none) |

---

### Summary Object

| Field | Type | Description |
|-------|------|-------------|
| `total_drugs` | int | Total number of drugs in the input drug list |
| `antibiotics_found` | int | Number of antibiotics detected in the drug list |
| `antibiotics_evaluated` | int | Number of antibiotics that were fully evaluated |
| `policy_compliant_count` | int | Count of antibiotics passing all compliance checks |
| `requires_review` | bool | `true` if any antibiotic needs pharmacist review |
| `total_dose_issues` | int | Total number of dose validation issues found |
| `policy_source` | str | `"json_policy"` or `"fallback"` indicating which policy source was used |
| `policy_error` | str \| null | Error message if policy JSON loading failed |

---

## Needs Review Decision Logic

The `needs_review` flag is raised (`true`) when any of the following trigger conditions are met:

1. **Antibiotic not needed**: `antibiotic_needed is False` — the antibiotic is not indicated for the diagnosis
2. **Policy non-compliance**: `policy_compliant is False` — the drug does not adhere to hospital policy
3. **Unjustified broad-spectrum**: `spectrum_appropriate is False` — broad-spectrum use without clinical justification
4. **Dose issues**: `len(dose_issues) > 0` — prescribed dose falls outside recommended range
5. **LLM clinical concerns**: Mistral identified clinical concerns (`concerns` array is non-empty)

---

## Policy Compliance Logic

The `policy_compliant` flag is set to `true` **only when all three conditions hold**:

1. `has_policy is true` — a matching policy section was found
2. `source` is either `"json_policy"` or `"guidelines"` — policy was successfully retrieved
3. `antibiotic_needed is not False` — the antibiotic is not explicitly contraindicated

---

## Spectrum Appropriateness Logic

The `spectrum_appropriate` flag is `true` unless:

- The antibiotic is **broad-spectrum** AND
- The drug is **not** listed as first-line or alternative in the policy AND
- The LLM did **not** confirm spectrum justification

This means broad-spectrum drugs explicitly recommended by policy (e.g., ceftriaxone for sepsis) are considered appropriate even without LLM confirmation.

---

## Recommendation String Priority

The final recommendation string is built from a priority-ordered cascade:

1. **Antibiotic not needed**: `"Antibiotic may not be needed for {diagnosis}. Consider non-antibiotic treatment."`
2. **Unjustified broad-spectrum**: `"Broad-spectrum {drug} may not be justified. Consider narrower alternatives: {alternatives}"`
3. **Policy compliant**: `"{drug} is compliant with hospital policy for {diagnosis}."`
4. **Default**: Policy guidance text or `"No policy guidance available."`

Dose issues are appended to the recommendation string.

---

## Complete Input/Output Examples

### Example 1: Appropriate Narrow-Spectrum Antibiotic

**Input**:
```json
{
  "drug_list": [
    {
      "generic": "amoxicillin",
      "corrected_name": "amoxicillin",
      "structured": {"dose": "500mg", "route": "oral", "frequency": "TID"}
    }
  ],
  "diagnosis": "pneumonia",
  "patient_age": 45,
  "patient_gender": "M"
}
```

**Output**:
```json
{
  "antibiotics_detected": [
    {
      "drug": "amoxicillin",
      "antibiotic_needed": true,
      "policy_compliant": true,
      "spectrum_appropriate": true,
      "spectrum_type": "narrow",
      "policy_source": "json_policy",
      "dose_issues": [],
      "prescribed_dose": "500mg",
      "recommended_dose": "500-1000 mg",
      "llm_reasoning": {
        "appropriate": true,
        "spectrum_justified": true,
        "rationale": "Amoxicillin is appropriate first-line narrow-spectrum treatment for pneumonia",
        "alternatives": [],
        "concerns": []
      },
      "recommendation": "amoxicillin is compliant with hospital policy for pneumonia.",
      "needs_review": false,
      "confidence": 0.9
    }
  ],
  "summary": {
    "total_drugs": 1,
    "antibiotics_found": 1,
    "antibiotics_evaluated": 1,
    "policy_compliant_count": 1,
    "requires_review": false,
    "total_dose_issues": 0,
    "policy_source": "json_policy",
    "policy_error": null
  },
  "error": null
}
```

---

### Example 2: Dose Exceeds Policy Range

**Input**:
```json
{
  "drug_list": [
    {
      "generic": "amoxicillin",
      "corrected_name": "amoxicillin",
      "structured": {"dose": "2000mg", "route": "oral"}
    }
  ],
  "diagnosis": "pneumonia",
  "patient_age": 45,
  "patient_gender": "M"
}
```

**Output**:
```json
{
  "antibiotics_detected": [
    {
      "drug": "amoxicillin",
      "antibiotic_needed": true,
      "policy_compliant": true,
      "spectrum_appropriate": true,
      "spectrum_type": "narrow",
      "policy_source": "json_policy",
      "dose_issues": [
        "Dose 2000mg exceeds recommended range 500-1000 mg for amoxicillin"
      ],
      "prescribed_dose": "2000mg",
      "recommended_dose": "500-1000 mg",
      "llm_reasoning": {
        "appropriate": true,
        "spectrum_justified": true,
        "rationale": "Amoxicillin is appropriate but dose is excessive",
        "alternatives": [],
        "concerns": ["Prescribed dose significantly exceeds recommended range"]
      },
      "recommendation": "amoxicillin is compliant with hospital policy for pneumonia. Dose issue: Dose 2000mg exceeds recommended range 500-1000 mg for amoxicillin",
      "needs_review": true,
      "confidence": 0.9
    }
  ],
  "summary": {
    "total_drugs": 1,
    "antibiotics_found": 1,
    "antibiotics_evaluated": 1,
    "policy_compliant_count": 1,
    "requires_review": true,
    "total_dose_issues": 1,
    "policy_source": "json_policy",
    "policy_error": null
  },
  "error": null
}
```

---

### Example 3: Broad-Spectrum Not Justified

**Input**:
```json
{
  "drug_list": [
    {
      "generic": "ceftriaxone",
      "corrected_name": "ceftriaxone",
      "structured": {"dose": "2g", "route": "IV", "frequency": "BID"}
    }
  ],
  "diagnosis": "throat infection",
  "patient_age": 30,
  "patient_gender": "F"
}
```

**Output**:
```json
{
  "antibiotics_detected": [
    {
      "drug": "ceftriaxone",
      "antibiotic_needed": true,
      "policy_compliant": false,
      "spectrum_appropriate": false,
      "spectrum_type": "broad",
      "policy_source": "json_policy",
      "dose_issues": [],
      "prescribed_dose": "2g",
      "recommended_dose": null,
      "llm_reasoning": {
        "appropriate": true,
        "spectrum_justified": false,
        "rationale": "Ceftriaxone is broad-spectrum and should be reserved for severe infections. Throat infections typically respond to narrow-spectrum agents.",
        "alternatives": ["penicillin v", "amoxicillin", "azithromycin"],
        "concerns": ["Unnecessary broad-spectrum use may promote resistance"]
      },
      "recommendation": "Broad-spectrum ceftriaxone may not be justified. Consider narrower alternatives: penicillin v, amoxicillin, azithromycin",
      "needs_review": true,
      "confidence": 0.75
    }
  ],
  "summary": {
    "total_drugs": 1,
    "antibiotics_found": 1,
    "antibiotics_evaluated": 1,
    "policy_compliant_count": 0,
    "requires_review": true,
    "total_dose_issues": 0,
    "policy_source": "json_policy",
    "policy_error": null
  },
  "error": null
}
```

---

### Example 4: Non-Antibiotic Drugs (Empty Detection)

**Input**:
```json
{
  "drug_list": [
    {"generic": "paracetamol", "corrected_name": "paracetamol"},
    {"generic": "omeprazole", "corrected_name": "omeprazole"}
  ],
  "diagnosis": "gastritis",
  "patient_age": 40,
  "patient_gender": "M"
}
```

**Output**:
```json
{
  "antibiotics_detected": [],
  "summary": {
    "total_drugs": 2,
    "antibiotics_found": 0,
    "antibiotics_evaluated": 0,
    "policy_compliant_count": 0,
    "requires_review": false,
    "total_dose_issues": 0,
    "policy_source": "json_policy",
    "policy_error": null
  },
  "error": null
}
```

---

### Example 5: Unknown Diagnosis

**Input**:
```json
{
  "drug_list": [
    {
      "generic": "azithromycin",
      "corrected_name": "azithromycin",
      "structured": {"dose": "500mg", "route": "oral"}
    }
  ],
  "diagnosis": "viral fever",
  "patient_age": 25,
  "patient_gender": "F"
}
```

**Output**:
```json
{
  "antibiotics_detected": [
    {
      "drug": "azithromycin",
      "antibiotic_needed": null,
      "policy_compliant": false,
      "spectrum_appropriate": true,
      "spectrum_type": "narrow",
      "policy_source": "fallback",
      "dose_issues": [],
      "prescribed_dose": "500mg",
      "recommended_dose": null,
      "llm_reasoning": {
        "appropriate": null,
        "spectrum_justified": null,
        "rationale": "No guideline found for diagnosis 'viral fever'. Azithromycin is an antibiotic; viral infections do not respond to antibiotics.",
        "alternatives": [],
        "concerns": ["Could not parse LLM response"]
      },
      "recommendation": "Uncertain whether antibiotic is needed for viral fever. Clinical review advised.",
      "needs_review": true,
      "confidence": 0.5
    }
  ],
  "summary": {
    "total_drugs": 1,
    "antibiotics_found": 1,
    "antibiotics_evaluated": 1,
    "policy_compliant_count": 0,
    "requires_review": true,
    "total_dose_issues": 0,
    "policy_source": "fallback",
    "policy_error": null
  },
  "error": null
}
```

---

### Example 6: Dose Issue Only

**Input**:
```json
{
  "drug_list": [
    {
      "generic": "azithromycin",
      "corrected_name": "azithromycin",
      "structured": {"dose": "2000mg", "route": "oral"}
    }
  ],
  "diagnosis": "pneumonia",
  "patient_age": 70,
  "patient_gender": "M"
}
```

**Output**:
```json
{
  "antibiotics_detected": [
    {
      "drug": "azithromycin",
      "antibiotic_needed": true,
      "policy_compliant": true,
      "spectrum_appropriate": true,
      "spectrum_type": "narrow",
      "policy_source": "json_policy",
      "dose_issues": [
        "Dose 2000mg exceeds recommended range 250-500 mg for azithromycin"
      ],
      "prescribed_dose": "2000mg",
      "recommended_dose": "250-500 mg",
      "llm_reasoning": {
        "appropriate": true,
        "spectrum_justified": true,
        "rationale": "Azithromycin is appropriate for pneumonia but dose is excessive",
        "alternatives": [],
        "concerns": ["Dose exceeds recommended range"]
      },
      "recommendation": "azithromycin is compliant with hospital policy for pneumonia. Dose issue: Dose 2000mg exceeds recommended range 250-500 mg for azithromycin",
      "needs_review": true,
      "confidence": 0.9
    }
  ],
  "summary": {
    "total_drugs": 1,
    "antibiotics_found": 1,
    "antibiotics_evaluated": 1,
    "policy_compliant_count": 1,
    "requires_review": true,
    "total_dose_issues": 1,
    "policy_source": "json_policy",
    "policy_error": null
  },
  "error": null
}
```

---

## Integration Input (`check_from_module_outputs`)

When using the convenience wrapper `check_from_module_outputs()`, the inputs are:

| Parameter | Type | Description |
|-----------|------|-------------|
| `module3_normalized_drugs` | dict | Output from drug normalization (Module 3). Expected key: `"drugs"` (list of drug dicts) |
| `module4_validation` | dict | Diagnosis validation output (Module 4). Expected keys: `"diagnosis"` or `"input_diagnosis"`, `"patient"` (dict with `"age"` and `"gender"`) |

**Example**:
```python
result = check_from_module_outputs(
    module3_normalized_drugs={
        "drugs": [
            {"generic": "amoxicillin", "corrected_name": "amoxicillin",
             "structured": {"dose": "500mg", "route": "oral"}}
        ]
    },
    module4_validation={
        "diagnosis": "pneumonia",
        "patient": {"age": 45, "gender": "M"}
    }
)
```
