# Module 9: Pregnancy Safety Checker

## Overview

Module 9 is a **Pregnancy and Lactation Safety Assessment System** that evaluates drug safety for pregnant and lactating patients using FDA PLLR (Pregnancy and Lactation Labeling Rule) data.

### Key Features

1. **FDA PLLR Database Integration**
   - Loads pregnancy/lactation safety data from local JSON database
   - Legacy FDA categories (A, B, C, D, X) for reference
   - Modern PLLR categories (1, 2, 3, Not Recommended)
   - Comprehensive drug safety information

2. **Teratogenicity Assessment**
   - Evaluates risk of birth defects (teratogenicity)
   - FDA category classification
   - Evidence-based risk levels (minimal, low, moderate, high, very_high)
   - Identifies high-risk drugs requiring alternatives

3. **Trimester-Specific Safety**
   - First trimester (organogenesis)
   - Second trimester (fetal development)
   - Third trimester (labor/delivery considerations)
   - Trimester-specific warnings and recommendations

4. **Lactation Safety Evaluation**
   - Assesses drug passage into breast milk
   - Categorizes risk for breastfeeding
   - Identifies contraindications for lactation
   - Safe alternatives for nursing mothers

5. **Clinical Decision Support**
   - Recommends safer alternatives
   - Flags drugs requiring specialist review
   - Provides evidence-based guidance
   - Supports shared decision-making

## Installation

### 1. No External Dependencies Required!

Module 9 uses only Python standard library:
```bash
# Just copy the module - no pip install needed
cd backend/modules/module9
```

### 2. (Optional) FDA PLLR Database

The module includes a default hardcoded database. To use a custom JSON database:

```bash
# Place your database at:
/home/kart/Desktop/Kshema/data/fda_pllr_database.json

# Or set environment variable:
export FDA_PLLR_DATABASE="/path/to/your/pllr_database.json"
```

Template provided: `backend/modules/module9/fda_pllr_database_template.json`

## Usage

### 1. Python API - Pregnant Patient

```python
from backend.modules.module9.pregnancy_safety import check_pregnancy_safety

# Drug list from module 3
drugs = [
    {"generic": "amoxicillin", "corrected_name": "amoxicillin"},
    {"generic": "paracetamol", "corrected_name": "paracetamol"},
]

# Check pregnancy safety (2nd trimester)
result = check_pregnancy_safety(
    drug_list=drugs,
    is_pregnant=True,
    trimester="second"
)

print(result)
```

### 2. Python API - Lactating Patient

```python
result = check_pregnancy_safety(
    drug_list=drugs,
    is_lactating=True
)

print(result)
```

### 3. Python API - Both Pregnant and Lactating

```python
result = check_pregnancy_safety(
    drug_list=drugs,
    is_pregnant=True,
    is_lactating=True,
    trimester="third"
)

print(result)
```

### 4. CLI

```bash
python -m backend.modules.module9.pregnancy_safety \
    --drugs-json '[{"generic":"amoxicillin"}]' \
    --pregnant \
    --trimester second

# For lactation:
python -m backend.modules.module9.pregnancy_safety \
    --drugs-json '[{"generic":"amoxicillin"}]' \
    --lactating
```

### 5. Integration with Module 3 & 4

```python
from backend.modules.module9.pregnancy_safety import check_from_module_outputs

# Use outputs directly from module 3 and 4
result = check_from_module_outputs(
    module3_normalized_drugs=module3_output,
    module4_validation=module4_output,
    is_pregnant=True,
    trimester="first"
)
```

## Input Format

### `check_pregnancy_safety()`

```python
{
    "drug_list": [
        {
            "generic": "amoxicillin",
            "corrected_name": "amoxicillin",
            "structured": {"dose": "500mg", "route": "oral"}
        }
    ],
    "is_pregnant": True,
    "is_lactating": False,
    "trimester": "second"  # Optional: 'first', 'second', or 'third'
}
```

## Output Format

### Per-Drug Assessment

```json
{
  "drug": "amoxicillin",
  "found_in_database": true,
  "safe_in_pregnancy": true,
  "safe_in_lactation": true,
  "teratogenicity_risk": "minimal",
  "fda_category": "B",
  "pllr_category": "Category 1",
  "lactation_risk": "minimal",
  "lactation_status": "Safe",
  "trimester_warnings": [],
  "pregnancy_risk_description": "Adequate studies show no increased fetal risk",
  "lactation_risk_description": "Compatible with breastfeeding; minimally absorbed by infant",
  "recommendation": "✓ Safe in pregnancy - Adequate studies show no increased fetal risk. Note: First-line antibiotic for pregnant women with infections",
  "requires_review": false,
  "alternatives": []
}
```

### Summary Output

```json
{
  "safety_assessment": [...],
  "summary": {
    "total_drugs": 3,
    "drugs_evaluated": 3,
    "safe_count": 2,
    "unsafe_count": 1,
    "requires_review": true,
    "is_pregnant": true,
    "is_lactating": false,
    "trimester": "second",
    "database_source": "PLLR - FDA Pregnancy and Lactation Labeling Rule"
  },
  "error": null
}
```

## Output Fields Explained

| Field | Type | Values | Meaning |
|-------|------|--------|---------|
| `safe_in_pregnancy` | bool | true/false/null | Is drug safe if pregnant? |
| `safe_in_lactation` | bool | true/false/null | Is drug safe if lactating? |
| `teratogenicity_risk` | str | minimal/low/moderate/high/very_high/unknown | Risk of birth defects |
| `fda_category` | str | A/B/C/D/X | Legacy FDA category |
| `pllr_category` | str | Category 1/2/3/Not Recommended | Modern PLLR category |
| `lactation_risk` | str | minimal/low/moderate/high/very_high/unknown | Risk via breast milk |
| `trimester_warnings` | list | strings | Trimester-specific warnings |
| `requires_review` | bool | true/false | Needs clinical review? |
| `alternatives` | list | drug names | Safer alternative drugs |
| `recommendation` | str | text | Clinical recommendation |

## FDA Risk Categories

### Legacy FDA Categories (Pre-2016)

| Category | Definition | Risk Level |
|----------|-----------|-----------|
| **A** | Adequate human studies show no risk | Minimal |
| **B** | Animal studies show no risk; no human data | Low |
| **C** | Animal studies show adverse effects; no human data | Moderate |
| **D** | Evidence of fetal risk; benefits may warrant use | High |
| **X** | Studies show fetal abnormalities; contraindicated | Very High |

### Modern PLLR Categories (2016+)

| Category | Definition | Risk Level |
|----------|-----------|-----------|
| **Category 1** | Adequate human studies show no increased risk | Minimal |
| **Category 2** | Limited human data; cannot rule out small risks | Low |
| **Category 3** | Animal data only; limited/no human data | Moderate |
| **Not Recommended** | Fetal abnormalities demonstrated | Very High |

### Lactation Categories

| Status | Risk Level | Meaning |
|--------|-----------|---------|
| **Safe** | Minimal | Compatible with breastfeeding |
| **Probably Safe** | Low | Limited data but likely safe |
| **Unknown** | Moderate | Insufficient data; use caution |
| **Probably Unsafe** | High | Some evidence of harm |
| **Contraindicated** | Very High | Evidence of significant harm |

## Built-in Drug Database

### Current Database (12 drugs)

**Safe in Pregnancy:**
- ✅ Amoxicillin (Category A/B)
- ✅ Azithromycin (Category B)
- ✅ Acetaminophen (Category A)
- ✅ Paracetamol (Category A)
- ✅ Cephalexin (Category B)

**Caution/Limited Data:**
- ⚠️ Ibuprofen (Category C - avoid 3rd trimester)
- ⚠️ Fluoxetine (Category C - probably safe)

**Contraindicated:**
- ❌ Tetracycline (Category D)
- ❌ Doxycycline (Category D)
- ❌ Warfarin (Category X)
- ❌ Methotrexate (Category X)
- ❌ Lisinopril (Category D)

### Adding Custom Drugs

1. Edit `/home/kart/Desktop/Kshema/data/fda_pllr_database.json`
2. Add drug entry following the template structure
3. Include trimester-specific data
4. Module will automatically use updated database on next run

## Trimester-Specific Examples

### Safe Throughout Pregnancy
```json
{
  "drug": "amoxicillin",
  "safe_in_pregnancy": true,
  "trimester_warnings": [],
  "recommendation": "✓ Safe in pregnancy"
}
```

### Third Trimester Concern
```json
{
  "drug": "ibuprofen",
  "safe_in_pregnancy": false,  // Only in 3rd trimester
  "trimester_warnings": [
    "AVOID in third trimester - increases risk of closure of PDA, oligohydramnios"
  ],
  "recommendation": "Use acetaminophen instead, especially in third trimester"
}
```

### Contraindicated All Trimesters
```json
{
  "drug": "methotrexate",
  "safe_in_pregnancy": false,
  "fda_category": "X",
  "trimester_warnings": [
    "Not safe in first trimester",
    "Not safe in second trimester",
    "Not safe in third trimester"
  ],
  "alternatives": [],
  "recommendation": "❌ NOT SAFE IN PREGNANCY - Teratogenic; causes neural tube defects, skeletal abnormalities"
}
```

## Environment Variables

```bash
# PLLR database file path (optional)
export FDA_PLLR_DATABASE="/home/kart/Desktop/Kshema/data/fda_pllr_database.json"
```

## Utility Functions

### Get Drug Information
```python
from backend.modules.module9.pregnancy_safety import get_drug_pllr_info

info = get_drug_pllr_info("amoxicillin")
print(info["fda_category"])  # "B"
print(info["pregnancy_risk"])  # "Adequate studies show no increased fetal risk"
```

### List All Available Drugs
```python
from backend.modules.module9.pregnancy_safety import list_all_drugs_in_database

drugs = list_all_drugs_in_database()
print(len(drugs))  # 12
print(drugs)  # ['acetaminophen', 'amoxicillin', ...]
```

## Testing

```bash
python backend/modules/module9/test_module9.py
```

**Test Coverage:**
1. Safe drugs in pregnancy
2. Contraindicated drugs
3. Trimester-specific risks (NSAIDs)
4. Lactation safety
5. Drug information lookup
6. Database listing

## Common Use Cases

### 1. Check Medication in Pregnant Patient

```python
result = check_pregnancy_safety(
    drug_list=prescribed_drugs,
    is_pregnant=True,
    trimester="first"
)
# Review requires_review=True drugs with clinician
```

### 2. Check Medication in Breastfeeding Patient

```python
result = check_pregnancy_safety(
    drug_list=prescribed_drugs,
    is_lactating=True
)
# Alert if any drugs unsafe for breastfeeding
```

### 3. Patient Planning Pregnancy

```python
result = check_pregnancy_safety(
    drug_list=current_medications,
    is_pregnant=False
)
# Review and plan medication changes before conception
```

### 4. Transition from Pregnancy to Postpartum

```python
# Pregnancy check
preg_result = check_pregnancy_safety(
    drug_list=drugs,
    is_pregnant=True,
    trimester="third"
)

# Lactation check
lact_result = check_pregnancy_safety(
    drug_list=drugs,
    is_lactating=True
)
```

## Limitations & Future Work

### Current Limitations
1. **Limited drug database** - 12 common drugs included
2. **No dose adjustments** - Same risk for all doses
3. **No indication weighting** - Doesn't consider necessity
4. **Simplified risk assessment** - Binary safe/unsafe
5. **No interaction data** - Doesn't consider drug combinations

### Future Enhancements
- [ ] Expand drug database (100+ medications)
- [ ] Dosing adjustments for pregnancy
- [ ] Indication-based risk-benefit analysis
- [ ] Drug-drug interaction checking in pregnancy
- [ ] LactMed integration (NIH database)
- [ ] MotherToBaby registry data integration
- [ ] Machine learning for risk prediction
- [ ] Trimester-specific dosing recommendations

## References

- FDA PLLR: https://www.fda.gov/drugs/labeling-information/pregnancy-and-lactation-labeling-rule
- LactMed: https://www.ncbi.nlm.nih.gov/books/NBK501922/
- MotherToBaby: https://mothertobaby.org/
- ACOG (American College of Obstetricians and Gynecologists)
- Briggs GG, Freeman RK, Yaffe SJ. Drugs in Pregnancy and Lactation

## Integration with Other Modules

### Module 3 (Drug Normalization)
- Takes normalized drugs as input
- Matches generic/brand names

### Module 4 (Diagnosis Validation)
- Optional: confirms patient diagnosis
- Can exclude pregnancy-incompatible treatments

### Module 5 (Drug Appropriateness)
- Complements appropriateness checks
- Adds pregnancy-specific context

### Module 6 (Antibiotic Stewardship)
- Identifies pregnancy-safe antibiotics
- Ensures narrow-spectrum choices

---

**Module 9 Version**: 1.0.0  
**Date**: May 2026  
**Status**: Production Ready  
**No External Dependencies Required**
