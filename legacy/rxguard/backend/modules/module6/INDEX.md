# Module 6: Antibiotic Stewardship Checker - Complete Implementation

## 📦 What's Been Created

A complete **Module 6** for antibiotic stewardship assessment with JSON-based hospital policy loading and LLM reasoning.

### Directory Structure

```
backend/modules/module6/
├── __init__.py                          # Module entry point
├── antibiotic_stewardship.py            # Main implementation (1000+ lines)
├── test_module6.py                      # Test suite
├── integration_examples.py              # Integration examples (5 complete examples)
├── requirements_module6.txt             # Dependencies
├── README.md                            # Full documentation
├── SETUP.md                             # Setup and configuration guide
├── hospital_policy_template.json        # Policy template example
└── INDEX.md                             # This file
```

## ✨ Key Features Implemented

### 1. **JSON-Based Hospital Policy Loading**
   - Loads hospital antibiotic policy from structured JSON template
   - Matches diagnosis-drug pairs against policy sections
   - Returns first-line, alternative, severe/hospitalized, and avoid categories
   - Fallback to hardcoded guidelines if JSON unavailable

### 2. **Antibiotic Spectrum Classification**
   - **Narrow-spectrum**: amoxicillin, penicillin, azithromycin, erythromycin
   - **Moderate-spectrum**: amoxicillin-clavulanate, ciprofloxacin, cephalexin
   - **Broad-spectrum**: ceftriaxone, cefotaxime, piperacillin-tazobactam
   - Automatic classification with metadata lookup

### 3. **Clinical Indication Matching**
   - Maps diagnoses to appropriate antibiotics
   - Supports: pneumonia, UTI, skin infections, throat infections, respiratory infections
   - Indicates first-line, alternatives, broad-spectrum, and avoidable drugs
   - Uses evidence-based guidelines

### 4. **LLM Reasoning via Mistral**
   - Calls Mistral 7B LLM via Ollama for clinical reasoning
   - Evaluates appropriateness and spectrum justification
   - Identifies concerns and suggests alternatives
   - Temperature 0.3 for deterministic reasoning

### 5. **Comprehensive Output JSON**
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
      "llm_reasoning": {...},
      "recommendation": "...",
      "needs_review": false,
      "confidence": 0.9
    }
  ],
  "summary": {...},
  "error": null
}
```

## 📋 Files Explained

| File | Purpose | Key Points |
|------|---------|-----------|
| `antibiotic_stewardship.py` | Main module logic | 1000+ lines, full implementation |
| `__init__.py` | Module interface | Exports public functions |
| `test_module6.py` | Unit tests | Runnable test with sample data |
| `integration_examples.py` | Usage examples | 5 complete examples with modules 3-6 |
| `requirements_module6.txt` | Dependencies | CSV, JSON, urllib (core features work without external deps) |
| `README.md` | Full documentation | 500+ lines of API docs and reference |
| `SETUP.md` | Setup guide | Installation, config, troubleshooting |
| `hospital_policy_template.json` | Policy template | Customizable JSON structure for policies |

## 🚀 Quick Start

### 1. Install
```bash
pip install -r backend/modules/module6/requirements_module6.txt
```

### 2. Start Ollama
```bash
ollama serve
ollama pull mistral:7b-instruct-q4_K_M
```

### 3. Test
```bash
python backend/modules/module6/test_module6.py
```

### 4. Use
```python
from backend.modules.module6.antibiotic_stewardship import check_antibiotic_stewardship

result = check_antibiotic_stewardship(
    drug_list=[{"generic": "amoxicillin"}],
    diagnosis="pneumonia"
)
print(result)
```

## 🔧 Main Functions Exposed

### `check_antibiotic_stewardship()`
Main function for antibiotic stewardship assessment.

**Parameters:**
- `drug_list` (list[dict]) - Normalized drugs from module 3
- `diagnosis` (str) - Patient diagnosis
- `patient_age` (int, optional) - Patient age
- `patient_gender` (str, optional) - Patient gender
- `model` (str) - Mistral model tag
- `host` (str) - Ollama host
- `timeout_sec` (float) - LLM timeout

**Returns:**
```python
{
    "antibiotics_detected": [...],
    "summary": {...},
    "error": null or str
}
```

### `check_from_module_outputs()`
Integration wrapper for modules 3 & 4 outputs.

**Parameters:**
- `module3_normalized_drugs` (dict) - Module 3 output
- `module4_validation` (dict) - Module 4 output

**Returns:**
Same as `check_antibiotic_stewardship()`

## 📊 Output Structure

### Antibiotic Detection Result

| Field | Type | Range | Meaning |
|-------|------|-------|---------|
| `drug` | str | - | Antibiotic name |
| `antibiotic_needed` | bool | true/false | Is antibiotic indicated? |
| `policy_compliant` | bool | true/false | Matches hospital policy? |
| `spectrum_appropriate` | bool | true/false | Spectrum justified? |
| `spectrum_type` | str | narrow/moderate/broad | Antibiotic spectrum class |
| `policy_source` | str | json_policy/guidelines/unknown | Source of policy info |
| `llm_reasoning` | dict | - | LLM analysis results |
| `recommendation` | str | - | Clinical recommendation |
| `needs_review` | bool | true/false | Flagged for review? |
| `confidence` | float | 0.0-1.0 | Confidence in assessment |

### LLM Reasoning Output

```json
{
  "appropriate": true|false,
  "spectrum_justified": true|false,
  "rationale": "explanation",
  "alternatives": ["drug1", "drug2"],
  "concerns": ["concern1", "concern2"]
}
```

### Summary Statistics

```json
{
  "total_drugs": 5,
  "antibiotics_found": 2,
  "antibiotics_evaluated": 2,
  "policy_compliant_count": 2,
  "requires_review": true,
  "total_dose_issues": 0
}
```

## 🧪 Testing

### Run Test Suite
```bash
python backend/modules/module6/test_module6.py
```

### Run Integration Examples
```bash
python backend/modules/module6/integration_examples.py
```

### Example Scenarios Covered
1. ✅ Minimal usage (standalone)
2. ✅ Integration with modules 3, 4, 6
3. ✅ Full pipeline (modules 3, 4, 5, 6)
4. ✅ Broad-spectrum alert scenario
5. ✅ Diagnostic uncertainty scenario

## 🔄 Integration Points

### With Module 3 (Drug Normalization)
```python
normalized_drugs = normalize_drug_list(ocr_text)
result = check_antibiotic_stewardship(
    drug_list=normalized_drugs.get("drugs", []),
    diagnosis="pneumonia"
)
```

### With Module 4 (Diagnosis Validation)
```python
validation = validate_diagnosis(diagnosis="pneumonia")
result = check_antibiotic_stewardship(
    drug_list=drugs,
    diagnosis=validation.get("diagnosis")
)
```

### With Module 5 (Drug Appropriateness)
```python
appropriateness = check_drug_appropriateness(...)
stewardship = check_antibiotic_stewardship(...)
# Combine both assessments for comprehensive review
```

## ⚙️ Configuration

### Environment Variables
```bash
OLLAMA_HOST                   # Ollama server (default: http://localhost:11434)
MISTRAL_MODEL                 # LLM model (default: mistral:7b-instruct-q4_K_M)
HOSPITAL_ANTIBIOTIC_POLICY_JSON # Path to hospital policy JSON (default: hospital_policy_template.json)
STEWARDSHIP_TIMEOUT          # LLM timeout in seconds (default: 120)
```

## 📚 Built-in Indication Guidelines

Supported diagnoses with first-line recommendations:
- **Pneumonia**: amoxicillin, azithromycin
- **UTI**: trimethoprim-sulfamethoxazole, nitrofurantoin
- **Skin Infection**: amoxicillin, cephalexin
- **Throat Infection**: penicillin V, azithromycin
- **Respiratory Tract Infection**: amoxicillin, azithromycin

## 🎯 Use Cases

1. **Antibiotic Stewardship Programs**
   - Audit prescribed antibiotics against policies
   - Flag unnecessary broad-spectrum use
   - Suggest narrower alternatives

2. **Clinical Decision Support**
   - Real-time assessment during prescription entry
   - Alert when spectrum not justified
   - Recommend policy-compliant alternatives

3. **Resistance Prevention**
   - Identify and minimize unnecessary antibiotic use
   - Promote narrow-spectrum prescribing
   - Support evidence-based guidelines

4. **Quality Assurance**
   - Monitor compliance with hospital antibiotic policy
   - Identify outliers for review
   - Generate compliance reports

## 🔐 Safety Features

- ✅ Graceful fallback to guidelines if JSON policy unavailable
- ✅ JSON validation for LLM output
- ✅ Timeout protection for LLM calls
- ✅ Error handling for missing data
- ✅ Confidence scores for all assessments
- ✅ Manual review flagging for uncertain cases

## 🚨 Limitations & Future Work

### Current Limitations
1. **No drug-drug interactions** - Limited to antibiotic appropriateness
2. **No dose validation** - Doesn't check dose ranges
3. **No allergy checking** - Assumes allergy data available externally
4. **Simplified indication matching** - Uses string matching, not NLP
5. **Single patient context** - No access to full EHR

### Future Enhancements
- [ ] Drug-drug interaction checking (Module 7?)
- [ ] Dose appropriateness validation
- [ ] Patient allergy and contraindication checking
- [ ] Local resistance patterns integration
- [ ] Renal function adjustment for dosing
- [ ] Multi-drug combination evaluation
- [ ] Integration with EHR systems

## 📖 Documentation

- **Full Documentation**: [README.md](README.md) (500+ lines)
- **Setup Guide**: [SETUP.md](SETUP.md) (troubleshooting, configuration)
- **Policy Template**: [hospital_policy_template.json](hospital_policy_template.json)
- **Examples**: [integration_examples.py](integration_examples.py) (5 runnable examples)
- **Test Suite**: [test_module6.py](test_module6.py)

## 🤝 Contributing

To customize the module:

1. **Add new indication guidelines** in `INDICATION_ANTIBIOTICS` dict
2. **Extend spectrum classification** in `NARROW_SPECTRUM`, `MODERATE_SPECTRUM`, `BROAD_SPECTRUM` sets
3. **Implement custom policy matching** by modifying `_retrieve_policy_guidance()`
4. **Add new LLM providers** by creating alternative to `_call_mistral_reasoning()`

## 📝 Version Info

- **Module Version**: 1.0.0
- **Date**: May 2026
- **Status**: Production Ready
- **Dependencies**: None beyond stdlib for core; ollama optional for LLM reasoning

## 🔗 Related Modules

- **Module 1**: OCR (Paddle)
- **Module 2**: NER (spaCy + regex)
- **Module 3**: Drug Normalization
- **Module 4**: Diagnosis Validation
- **Module 5**: Drug Appropriateness
- **Module 6**: Antibiotic Stewardship (NEW) ✨

---

**Ready to use!** Start with `SETUP.md` for installation, then run `test_module6.py` to verify.
