# Module 6 Setup Guide

## Quick Start

### 1. Install Dependencies

```bash
cd RxGuard
pip install -r backend/modules/module6/requirements_module6.txt
```

### 2. Verify Ollama is Running

```bash
# Terminal 1: Start Ollama
ollama serve

# Terminal 2: Pull Mistral model (if not already downloaded)
ollama pull mistral:7b-instruct-q4_K_M
```

### 3. Test the Module

```bash
python backend/modules/module6/test_module6.py
```

## Configuration Options

### Option A: Use JSON Policy (Recommended)

1. **Edit the built-in policy template**:
   ```
   backend/modules/module6/hospital_policy_template.json
   ```

2. **On each run**, the module will:
   - Load the JSON policy file
   - Match diagnosis-drug pairs against policy sections
   - Return first-line, alternative, severe/hospitalized, and avoid categories

3. **Verify setup**:
   ```bash
   python backend/modules/module6/test_module6.py
   ```

### Option B: Use Fallback Guidelines (Works Out-of-Box)

If you don't have a PDF:
- The module automatically falls back to **hardcoded evidence-based guidelines**
- Supports: pneumonia, UTI, skin infections, throat infections, respiratory infections
- No additional setup needed
- Policy source will be `"guidelines"` in output

### Option C: Custom Policy JSON

Use the provided `hospital_policy_template.json` as a starting point:

```bash
cp backend/modules/module6/hospital_policy_template.json ./custom_policy.json
# Edit the JSON to match your hospital's actual policies
```

*JSON policy is the default policy source since v1.0*

## Environment Variables

Create a `.env` file or set these in your shell:

```bash
# Ollama Configuration
export OLLAMA_HOST="http://localhost:11434"
export MISTRAL_MODEL="mistral:7b-instruct-q4_K_M"

# Policy and Storage
export HOSPITAL_ANTIBIOTIC_POLICY_JSON="./hospital_policy_template.json"

# LLM Timeout (seconds)
export STEWARDSHIP_TIMEOUT="120"
```

## Integration with Other Modules

### With Module 3 & 4 (Recommended Pipeline)

```python
# script.py or your main pipeline
from backend.modules.module3.drug_normalization import normalize_drug_list
from backend.modules.module4.diagnosis_validator import validate_diagnosis
from backend.modules.module6.antibiotic_stewardship import check_from_module_outputs

# Process prescription
ocr_text = "Tab Amoxicillin 500mg TID for 7 days"
drugs = normalize_drug_list(ocr_text)
diagnosis = "pneumonia"  # From NER or manual input
validation = validate_diagnosis(diagnosis=diagnosis)

# Check stewardship
stewardship = check_from_module_outputs(
    module3_normalized_drugs=drugs,
    module4_validation=validation
)

print(stewardship)
```

### Standalone Usage (Independent Module)

```python
from backend.modules.module6.antibiotic_stewardship import check_antibiotic_stewardship

result = check_antibiotic_stewardship(
    drug_list=[{"generic": "amoxicillin", "corrected_name": "amoxicillin"}],
    diagnosis="pneumonia"
)
```

## Policy JSON Customization

### Edit Policy Template

The file `hospital_policy_template.json` contains the hospital's antibiotic policy.

```python
import json
from pathlib import Path

policy_path = Path("backend/modules/module6/hospital_policy_template.json")
policy = json.loads(policy_path.read_text(encoding="utf-8"))

# Query policy sections
for section in policy.get("hospital_antibiotic_policy", {}).get("policy_sections", []):
    print(section.get("section_name"))
```

### Reset to Default

```bash
git checkout backend/modules/module6/hospital_policy_template.json
```

## Troubleshooting

### Issue: "policy_error" in output

**Possible Causes:**
1. Policy JSON file not found
2. JSON file has invalid syntax

**Solutions:**
```bash
# Verify policy JSON exists
ls backend/modules/module6/hospital_policy_template.json

# Check JSON is valid
python -m json.tool backend/modules/module6/hospital_policy_template.json > /dev/null
```

### Issue: "Error calling Mistral"

**Possible Causes:**
1. Ollama not running
2. Model not downloaded
3. Port mismatch

**Solutions:**
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve

# In another terminal, download model
ollama pull mistral:7b-instruct-q4_K_M

# Test inference
ollama run mistral "Hello"
```

### Issue: Slow on First Run

**Expected Behavior:**
- JSON policy loads on first use: <0.5 seconds (cached after first load)

### Issue: Import Error

**Solution:**
```bash
# Module uses only Python stdlib — no external packages required
# If you get an import error, check your Python installation
python --version
```

## Performance Tuning

### Reduce LLM Timeout

```bash
export STEWARDSHIP_TIMEOUT="60"  # seconds
```

## API Reference

### `check_antibiotic_stewardship()`

```python
result = check_antibiotic_stewardship(
    drug_list=[...],              # list of drug dicts from module 3
    diagnosis="pneumonia",         # str, clinical diagnosis
    patient_age=45,               # int, optional
    patient_gender="M",           # str, optional
    model="mistral:...",         # str, LLM model tag
    host="http://localhost:11434", # str, Ollama host
    timeout_sec=120              # float, LLM timeout
)
```

### Output Fields

| Field | Type | Range | Meaning |
|-------|------|-------|---------|
| `antibiotic_needed` | bool | - | Antibiotic required for diagnosis? |
| `policy_compliant` | bool | - | Matches hospital policy? |
| `spectrum_appropriate` | bool | - | Spectrum justified? |
| `confidence` | float | 0.0-1.0 | Confidence in assessment |
| `needs_review` | bool | - | Flagged for clinical review |

## Examples

### Example 1: Appropriate Narrow-Spectrum Choice

```json
{
  "drug": "amoxicillin",
  "antibiotic_needed": true,
  "policy_compliant": true,
  "spectrum_appropriate": true,
  "needs_review": false,
  "recommendation": "Amoxicillin is compliant with hospital policy for pneumonia."
}
```

### Example 2: Inappropriate Broad-Spectrum for Simple Diagnosis

```json
{
  "drug": "ceftriaxone",
  "antibiotic_needed": true,
  "policy_compliant": true,
  "spectrum_appropriate": false,
  "needs_review": true,
  "recommendation": "Broad-spectrum ceftriaxone may not be justified. Consider narrower alternatives: amoxicillin, azithromycin"
}
```

### Example 3: Non-Antibiotic Drug

```json
{
  "antibiotics_detected": [],
  "summary": {
    "antibiotics_found": 0,
    "requires_review": false
  }
}
```

## Next Steps

1. ✅ Test with `test_module6.py`
2. ✅ Prepare hospital policy PDF
3. ✅ Integrate with main pipeline
4. ✅ Monitor output for clinical validation
5. ✅ Customize guidelines as needed

## Support

For issues or questions:
- Check `backend/modules/module6/README.md` for full documentation
- Review test case: `backend/modules/module6/test_module6.py`
- Check hospital policy template: `backend/modules/module6/hospital_policy_template.json`
