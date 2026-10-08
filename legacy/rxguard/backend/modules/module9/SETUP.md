# Module 9 Setup Guide

## Quick Start

### 1. Module is Ready to Use!

No pip installation required - uses Python standard library only:

```bash
python backend/modules/module9/test_module9.py
```

### 2. (Optional) Custom PLLR Database

Replace the default hardcoded database with your own:

```bash
# Copy template
cp backend/modules/module9/fda_pllr_database_template.json \
   /home/kart/Desktop/Kshema/data/fda_pllr_database.json

# Edit the JSON file to add/modify drugs
# Module will automatically load it on next run
```

### 3. Set Environment Variable (Optional)

```bash
export FDA_PLLR_DATABASE="/home/kart/Desktop/Kshema/data/fda_pllr_database.json"
```

## Configuration Options

### Option A: Use Default Hardcoded Database (Recommended for Quick Start)

- 12 common drugs included
- Pre-loaded with FDA/PLLR data
- Works immediately, no setup needed
- Located in `/backend/modules/module9/pregnancy_safety.py`

### Option B: Use Custom JSON Database

1. **Create database file:**
   ```bash
   # Use template as starting point
   cp backend/modules/module9/fda_pllr_database_template.json \
      /home/kart/Desktop/Kshema/data/fda_pllr_database.json
   ```

2. **Edit for your institution:**
   ```json
   {
     "database_version": "1.0",
     "drugs": {
       "drug_name": {
         "fda_category": "B",
         "pllr_pregnancy": "Category 1",
         "trimester_specific": {...}
       }
     }
   }
   ```

3. **Module auto-loads:**
   - Looks for: `/home/kart/Desktop/Kshema/data/fda_pllr_database.json`
   - Or set: `export FDA_PLLR_DATABASE="/path/to/db.json"`

## Integration with Other Modules

### With Modules 3 & 4

```python
# Process prescription
drugs = normalize_drug_list(ocr_text)
diagnosis = validate_diagnosis(diagnosis_text)

# Check pregnancy safety
from backend.modules.module9.pregnancy_safety import check_pregnancy_safety

result = check_pregnancy_safety(
    drug_list=drugs.get("drugs", []),
    is_pregnant=True,
    trimester="second"
)
```

### Standalone Usage

```python
from backend.modules.module9.pregnancy_safety import check_pregnancy_safety

result = check_pregnancy_safety(
    drug_list=[{"generic": "amoxicillin"}],
    is_pregnant=True
)
```

## Database Structure

### Minimal Required Fields

```json
{
  "generic_name": "amoxicillin",
  "fda_category": "B",
  "pllr_pregnancy": "Category 1",
  "pregnancy_risk": "Description",
  "teratogenicity_risk": "minimal",
  "lactation": "Safe",
  "lactation_risk": "minimal",
  "trimester_specific": {
    "first": {"safe": true, "risk": "minimal", "notes": "..."},
    "second": {"safe": true, "risk": "minimal", "notes": "..."},
    "third": {"safe": true, "risk": "minimal", "notes": "..."}
  },
  "recommended_alternatives": [],
  "comments": "..."
}
```

### Adding New Drugs

Edit JSON and add entries:

```json
"fluconazole": {
  "generic_name": "fluconazole",
  "fda_category": "C",
  "pllr_pregnancy": "Category 2",
  "pregnancy_risk": "Limited data; generally safe for vaginal candidiasis",
  "teratogenicity_risk": "low",
  "lactation": "Safe",
  "lactation_risk": "minimal",
  "trimester_specific": {
    "first": {
      "safe": true,
      "risk": "low",
      "notes": "Safe for vaginal candidiasis"
    },
    "second": {"safe": true, "risk": "low", "notes": "Safe"},
    "third": {"safe": true, "risk": "low", "notes": "Safe"}
  },
  "recommended_alternatives": [],
  "comments": "Preferred agent for fungal infections in pregnancy"
}
```

## Usage Patterns

### Pattern 1: Pregnant Patient with Infection

```python
# Patient: 28-week pregnant, pneumonia
result = check_pregnancy_safety(
    drug_list=[
        {"generic": "amoxicillin"},
        {"generic": "acetaminophen"}
    ],
    is_pregnant=True,
    trimester="second"
)
# Output: Both safe ✓
```

### Pattern 2: Lactating Patient on Chronic Medication

```python
# Patient: Postpartum day 5, on antidepressant
result = check_pregnancy_safety(
    drug_list=[
        {"generic": "fluoxetine"},
        {"generic": "prenatal_vitamin"}
    ],
    is_lactating=True
)
# Output: Fluoxetine probably safe ⚠️
```

### Pattern 3: Pre-Pregnancy Medication Review

```python
# Patient: Planning pregnancy in 3 months
result = check_pregnancy_safety(
    drug_list=[
        {"generic": "lisinopril"},  # Needs change
        {"generic": "metformin"},    # Safe
        {"generic": "warfarin"}      # Needs change
    ],
    is_pregnant=False  # Currently not pregnant
)
# Output: Recommends medication switch before conception
```

### Pattern 4: Postpartum Medication Transition

```python
# Same patient transitioning from pregnancy to postpartum

# 1. Check pregnancy (before delivery)
preg_result = check_pregnancy_safety(
    drug_list=drugs,
    is_pregnant=True,
    trimester="third"
)

# 2. Check lactation (after delivery, if breastfeeding)
lact_result = check_pregnancy_safety(
    drug_list=drugs,
    is_lactating=True
)
```

## Output Examples

### Example 1: Safe Drug

```json
{
  "drug": "amoxicillin",
  "found_in_database": true,
  "safe_in_pregnancy": true,
  "teratogenicity_risk": "minimal",
  "fda_category": "B",
  "trimester_warnings": [],
  "recommendation": "✓ Safe in pregnancy - Adequate studies show no increased fetal risk",
  "requires_review": false,
  "alternatives": []
}
```

### Example 2: Unsafe Drug

```json
{
  "drug": "warfarin",
  "found_in_database": true,
  "safe_in_pregnancy": false,
  "teratogenicity_risk": "very_high",
  "fda_category": "X",
  "trimester_warnings": [
    "Not safe in first trimester",
    "Causes nasal hypoplasia, bone abnormalities - fetal warfarin syndrome"
  ],
  "recommendation": "❌ NOT SAFE IN PREGNANCY - Use heparin or low molecular weight heparin instead",
  "requires_review": true,
  "alternatives": ["heparin", "low molecular weight heparin"]
}
```

### Example 3: Trimester-Specific Concern

```json
{
  "drug": "ibuprofen",
  "safe_in_pregnancy": false,
  "teratogenicity_risk": "low",  // low overall but...
  "trimester_warnings": [
    "AVOID in third trimester - increases risk of closure of PDA, oligohydramnios"
  ],
  "recommendation": "Use acetaminophen instead, especially in third trimester",
  "requires_review": true,
  "alternatives": ["acetaminophen"]
}
```

### Example 4: Unknown Drug

```json
{
  "drug": "unknown_medication",
  "found_in_database": false,
  "safe_in_pregnancy": null,
  "teratogenicity_risk": "unknown",
  "trimester_warnings": [
    "Drug not found in PLLR database - manual review required"
  ],
  "recommendation": "MANUAL REVIEW REQUIRED - Consult clinical references",
  "requires_review": true
}
```

## Testing

### Run Full Test Suite
```bash
python backend/modules/module9/test_module9.py
```

**Tests included:**
1. Safe drugs in pregnancy ✓
2. Contraindicated drugs ⚠️
3. Trimester-specific risks 
4. Lactation safety 🍼
5. Drug information lookup
6. Database listing

### Test Specific Drug
```python
from backend.modules.module9.pregnancy_safety import get_drug_pllr_info

info = get_drug_pllr_info("amoxicillin")
print(f"FDA Category: {info['fda_category']}")
print(f"Safe in pregnancy: {info['trimester_specific']['first']['safe']}")
```

## Troubleshooting

### Issue: "Drug not found in PLLR database"

**Solution:**
1. Check drug name spelling
2. Use generic name, not brand name
3. Add drug to database JSON
4. Reload module

### Issue: Database not loading

**Check:**
```bash
# Verify database file exists
ls /home/kart/Desktop/Kshema/data/fda_pllr_database.json

# Validate JSON syntax
python -m json.tool /home/kart/Desktop/Kshema/data/fda_pllr_database.json
```

### Issue: Incorrect Risk Assessment

**Verify:**
1. FDA/PLLR categories in database
2. Trimester-specific data
3. Cross-reference with clinical guidelines
4. Consider updating database

## Performance

- **First call**: ~5ms (load database)
- **Subsequent calls**: ~1-2ms per drug
- **Memory**: <2MB (database in memory)
- **No external dependencies**: Fast startup

## Extending the Module

### Add Custom Risk Assessment

```python
def assess_custom_risk(drug_pllr, patient_info):
    """Add institution-specific risk factors."""
    # Your custom logic
    pass
```

### Implement Interaction Checking

```python
def check_pregnancy_interactions(drug1, drug2):
    """Check interactions relevant to pregnancy."""
    # Query interaction database
    pass
```

### Integrate with Electronic Health Records

```python
def check_ehr_medications(patient_id, is_pregnant):
    """Query EHR and check all medications."""
    # Connect to EHR API
    pass
```

## Reference Resources

- FDA PLLR: https://www.fda.gov/drugs/labeling-information/pregnancy-and-lactation-labeling-rule
- LactMed: https://www.ncbi.nlm.nih.gov/books/NBK501922/
- MotherToBaby: https://mothertobaby.org/
- ACOG Guidelines: https://www.acog.org/

## Next Steps

1. ✅ Test with `test_module9.py`
2. ✅ Review built-in database coverage
3. ✅ Customize with institutional drugs
4. ✅ Integrate into clinical workflow
5. ✅ Monitor output for validation

## Support

For questions or issues:
- Check [README.md](README.md) for full API documentation
- Review [test_module9.py](test_module9.py) for examples
- See database template: [fda_pllr_database_template.json](fda_pllr_database_template.json)
