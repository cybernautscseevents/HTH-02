# Module 6: Antibiotic Stewardship Checker

## Overview

Module 6 is an **Antibiotic Stewardship Assessment System** that validates prescribed antibiotics against hospital policies, classifies their spectrum, and provides LLM-based clinical reasoning.

### Key Features

1. **JSON-based Policy Loading**
   - Loads hospital antibiotic policy from structured JSON template
   - Matches diagnosis-drug pairs against policy sections
   - Returns first-line, alternative, severe/hospitalized, and avoid categories

2. **Antibiotic Spectrum Classification**
   - Narrow-spectrum (e.g., amoxicillin, azithromycin)
   - Moderate-spectrum (e.g., amoxicillin-clavulanate, ciprofloxacin)
   - Broad-spectrum (e.g., ceftriaxone, piperacillin-tazobactam)

3. **Clinical Indication Matching**
   - Checks if prescribed antibiotic is appropriate for diagnosis
   - Built-in guideline maps (pneumonia, UTI, skin infections, etc.)
   - Suggests narrower alternatives when broad-spectrum is overused

4. **LLM Reasoning with Mistral**
   - Calls Mistral 7B via Ollama for clinical reasoning
   - Evaluates appropriateness and spectrum justification
   - Identifies concerns and suggests alternatives

## Installation

### 1. Install Dependencies

```bash
pip install -r backend/modules/module6/requirements_module6.txt
```

### 2. Ensure Ollama is Running with Mistral

```bash
ollama pull mistral:7b-instruct-q4_K_M
ollama serve
```

### 3. Prepare Hospital Policy JSON (Optional)

Place your hospital's antibiotic policy JSON at:
```
hospital_policy_template.json
```

Or set via environment variable:
```bash
export HOSPITAL_ANTIBIOTIC_POLICY_JSON="/path/to/your/policy.json"
```

**If no JSON is provided**, the module uses the bundled `hospital_policy_template.json`.

## Usage

### 1. Python API

```python
from backend.modules.module6.antibiotic_stewardship import check_antibiotic_stewardship

# Drug list from module 3 (normalized drugs)
drugs = [
    {
        "generic": "ceftriaxone",
        "corrected_name": "ceftriaxone",
        "structured": {"dose": "2g", "route": "IV"}
    },
    {
        "generic": "amoxicillin",
        "corrected_name": "amoxicillin",
        "structured": {"dose": "500mg", "route": "oral"}
    }
]

result = check_antibiotic_stewardship(
    drug_list=drugs,
    diagnosis="pneumonia",
    patient_age=45,
    patient_gender="M"
)

print(result)
```

### 2. CLI

```bash
python -m backend.modules.module6.antibiotic_stewardship \
    --drugs-json '[{"generic":"amoxicillin"}]' \
    --diagnosis "pneumonia" \
    --age 45 \
    --gender M
```

### 3. Integration with Module 3 & 4

```python
from backend.modules.module6.antibiotic_stewardship import check_from_module_outputs

# Use outputs directly from module 3 (drug normalization) and 4 (diagnosis validation)
result = check_from_module_outputs(
    module3_normalized_drugs=module3_output,
    module4_validation=module4_output
)
```

## Input Format

### `check_antibiotic_stewardship()`

```python
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
        }
    ],
    "diagnosis": "pneumonia",
    "patient_age": 45,
    "patient_gender": "M"
}
```

## Output Format

```json
{
  "antibiotics_detected": [
    {
      "drug": "amoxicillin",
      "antibiotic_needed": true,
      "policy_compliant": true,
      "spectrum_appropriate": true,
      "spectrum_type": "narrow",
      "policy_source": "guidelines",
      "llm_reasoning": {
        "appropriate": true,
        "spectrum_justified": true,
        "rationale": "Amoxicillin is a good first-line narrow-spectrum choice for pneumonia...",
        "alternatives": [],
        "concerns": []
      },
      "recommendation": "Amoxicillin is compliant with hospital policy for pneumonia.",
      "needs_review": false,
      "confidence": 0.9
    },
    {
      "drug": "ceftriaxone",
      "antibiotic_needed": true,
      "policy_compliant": true,
      "spectrum_appropriate": false,
      "spectrum_type": "broad",
      "policy_source": "guidelines",
      "llm_reasoning": {
        "appropriate": true,
        "spectrum_justified": false,
        "rationale": "Ceftriaxone is appropriate for pneumonia but broad-spectrum use should be reserved...",
        "alternatives": ["amoxicillin", "azithromycin"],
        "concerns": ["Unnecessary broad-spectrum use may promote resistance"]
      },
      "recommendation": "Broad-spectrum ceftriaxone may not be justified. Consider narrower alternatives: amoxicillin, azithromycin",
      "needs_review": true,
      "confidence": 0.75
    }
  ],
  "summary": {
    "total_drugs": 3,
    "antibiotics_found": 2,
    "antibiotics_evaluated": 2,
    "policy_compliant_count": 2,
    "requires_review": true
  },
  "error": null
}
```

## Output Fields Explained

| Field | Type | Description |
|-------|------|-------------|
| `drug` | str | Name of the antibiotic |
| `antibiotic_needed` | bool | Is an antibiotic needed for this diagnosis? |
| `policy_compliant` | bool | Is the antibiotic compliant with hospital policy? |
| `spectrum_appropriate` | bool | Is the spectrum choice justified? |
| `spectrum_type` | str | narrow / moderate / broad |
| `policy_source` | str | json_policy / guidelines / unknown |
| `llm_reasoning` | dict | Mistral LLM analysis |
| `recommendation` | str | Clinical recommendation |
| `needs_review` | bool | Flagged for clinical review? |
| `confidence` | float | 0.0-1.0 confidence score |

## Antibiotic Classification

### Narrow-Spectrum (Preferred First-Line)
- amoxicillin, penicillin, oxacillin
- azithromycin, erythromycin
- *Use to minimize resistance risk*

### Moderate-Spectrum (Alternative)
- amoxicillin-clavulanate, cephalexin
- ciprofloxacin, levofloxacin
- trimethoprim-sulfamethoxazole

### Broad-Spectrum (Reserve Use)
- ceftriaxone, cefotaxime
- piperacillin-tazobactam
- meropenem, ertapenem
- *Only when narrow/moderate insufficient*

## Built-in Indication Guidelines

### Pneumonia
- **First-line**: amoxicillin, amoxicillin-clavulanate
- **Alternatives**: cephalexin, azithromycin
- **Broad-spectrum**: ceftriaxone, cefotaxime

### UTI / Urinary Tract Infection
- **First-line**: trimethoprim-sulfamethoxazole, nitrofurantoin
- **Alternatives**: ciprofloxacin, cephalexin
- **Broad-spectrum**: piperacillin-tazobactam

### Skin Infection
- **First-line**: amoxicillin, oxacillin
- **Alternatives**: cephalexin, cloxacillin
- **Broad-spectrum**: ceftriaxone

### Throat Infection
- **First-line**: penicillin V, amoxicillin
- **Alternatives**: erythromycin, azithromycin
- **Broad-spectrum**: ceftriaxone

### Respiratory Tract Infection
- **First-line**: amoxicillin, azithromycin
- **Alternatives**: cephalexin, erythromycin
- **Broad-spectrum**: ceftriaxone, cefotaxime

## Environment Variables

```bash
# Ollama host (default: http://localhost:11434)
export OLLAMA_HOST="http://localhost:11434"

# Mistral model (default: mistral:7b-instruct-q4_K_M)
export MISTRAL_MODEL="mistral:7b-instruct-q4_K_M"

# Hospital policy JSON path (default: hospital_policy_template.json)
export HOSPITAL_ANTIBIOTIC_POLICY_JSON="/path/to/policy.json"

# LLM timeout in seconds (default: 120)
export STEWARDSHIP_TIMEOUT="120"
```

## Testing

```bash
python backend/modules/module6/test_module6.py
```

## Dependencies

### Core Dependencies
- **Python stdlib** - csv, json, re, os, pathlib, urllib (all features work out of the box)

### External Services
- **Ollama** - Local LLM server with Mistral model

### Python Standard Library
- json, re, os, pathlib, urllib

## Troubleshooting

### 1. JSON Policy Not Loading

```
Policy JSON not found at ...
```

**Solution**: Ensure the policy JSON path is correct. The module falls back to hardcoded guidelines automatically.

### 2. Ollama Connection Error

```
Error calling Mistral: urlopen error
```

**Solution**: Ensure Ollama is running:

```bash
ollama serve  # In a separate terminal
```

### 3. Mistral Model Not Found

```
error pulling mistral:7b-instruct-q4_K_M
```

**Solution**: Download the model first:

```bash
ollama pull mistral:7b-instruct-q4_K_M
```

## Future Enhancements

1. **Dose Appropriateness**
   - Validate dose ranges for age, weight, renal function
   - Check frequency appropriateness

2. **Allergy Checking**
   - Cross-check against patient allergy history
   - Flag cross-reactive drug classes

3. **Resistance Patterns**
   - Consider local resistance epidemiology
   - Recommend based on pathogen susceptibility

4. **Multi-drug Policies**
   - Evaluate drug combination appropriateness
   - Check for redundant coverage

## Input/Output Reference

For detailed input/output specifications with examples, see **[INPUT_OUTPUT.md](INPUT_OUTPUT.md)**.

## References

- Antibiotic Stewardship: https://www.cdc.gov/antibiotic-use/
- Spectrum Classification: WHO AWaRe Classification
- JSON Policy Template: hospital_policy_template.json

---

**Module 6 Version**: 1.0.0  
**Last Updated**: May 2026
