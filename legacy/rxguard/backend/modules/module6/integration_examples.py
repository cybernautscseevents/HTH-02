#!/usr/bin/env python3
"""
Module 6 Integration Example

Shows how to use Module 6 (Antibiotic Stewardship) with:
- Module 3: Drug Normalization
- Module 4: Diagnosis Validation
- Module 5: Drug Appropriateness
- Module 6: Antibiotic Stewardship (NEW)
"""

import json
from typing import Any


def example_minimal():
    """Minimal example: Module 6 standalone."""
    from backend.modules.module6.antibiotic_stewardship import check_antibiotic_stewardship
    
    print("\n" + "="*70)
    print("EXAMPLE 1: Minimal Usage (Standalone)")
    print("="*70)
    
    drugs = [
        {"generic": "amoxicillin", "corrected_name": "amoxicillin"},
        {"generic": "paracetamol", "corrected_name": "paracetamol"}
    ]
    
    result = check_antibiotic_stewardship(
        drug_list=drugs,
        diagnosis="pneumonia"
    )
    
    print(json.dumps(result, indent=2))
    return result


def example_with_modules_3_4():
    """Integration with Module 3 & 4."""
    from backend.modules.module3.drug_normalization import normalize_drug_list
    from backend.modules.module4.diagnosis_validator import validate_diagnosis
    from backend.modules.module6.antibiotic_stewardship import check_from_module_outputs
    
    print("\n" + "="*70)
    print("EXAMPLE 2: Integration with Modules 3, 4, and 6")
    print("="*70)
    
    # Simulate OCR prescription text
    prescription_text = """
    Patient: John Doe
    Age: 45, M
    Diagnosis: Pneumonia
    
    Rx:
    Tab Amoxicillin 500mg TID x 7 days
    Tab Paracetamol 500mg TID PRN
    """
    
    print(f"\n📄 Prescription Text:\n{prescription_text}")
    
    # Module 3: Normalize drugs
    print("\n[Module 3] Normalizing drugs...")
    normalized_drugs = normalize_drug_list(prescription_text)
    print(f"  ✓ Found {len(normalized_drugs.get('drugs', []))} drugs")
    
    # Module 4: Validate diagnosis
    print("\n[Module 4] Validating diagnosis...")
    diagnosis_result = validate_diagnosis(
        symptoms="cough, fever, shortness of breath",
        age=45,
        gender="M",
        examination_findings="rales on auscultation",
        diagnosis="pneumonia"
    )
    print(f"  ✓ Status: {diagnosis_result.get('status')}")
    print(f"  ✓ Plausible: {diagnosis_result.get('is_plausible')}")
    
    # Module 6: Check antibiotic stewardship
    print("\n[Module 6] Checking antibiotic stewardship...")
    stewardship = check_from_module_outputs(
        module3_normalized_drugs=normalized_drugs,
        module4_validation=diagnosis_result
    )
    
    print("\nSTEWARDSHIP ASSESSMENT:")
    for ab in stewardship.get("antibiotics_detected", []):
        print(f"\n  Drug: {ab['drug']}")
        print(f"    - Antibiotic needed: {ab.get('antibiotic_needed')}")
        print(f"    - Policy compliant: {ab.get('policy_compliant')}")
        print(f"    - Spectrum appropriate: {ab.get('spectrum_appropriate')}")
        print(f"    - Needs review: {ab.get('needs_review')}")
        print(f"    - Recommendation: {ab.get('recommendation')}")
    
    summary = stewardship.get("summary", {})
    print("\nSummary:")
    print(f"    - Total drugs: {summary.get('total_drugs')}")
    print(f"    - Antibiotics found: {summary.get('antibiotics_found')}")
    print(f"    - Requires review: {summary.get('requires_review')}")
    
    return stewardship


def example_full_pipeline():
    """Complete pipeline: Modules 1-6 (where available)."""
    from backend.modules.module3.drug_normalization import normalize_drug_list
    from backend.modules.module4.diagnosis_validator import validate_diagnosis
    from backend.modules.module5.drug_appropriateness import check_drug_appropriateness
    from backend.modules.module6.antibiotic_stewardship import check_antibiotic_stewardship
    
    print("\n" + "="*70)
    print("EXAMPLE 3: Full Pipeline - Modules 3, 4, 5, and 6")
    print("="*70)
    
    prescription_text = """
    Patient: Jane Smith, Age 32, F
    
    Diagnosis: Urinary Tract Infection
    
    Rx:
    Tab Trimethoprim-Sulfa 160/800mg BID x 3 days
    Tab Pyridium 100mg TID
    """
    
    print(f"\n📄 Prescription:\n{prescription_text}")
    
    # Module 3: Normalize
    print("\n[Module 3] Drug Normalization...")
    mod3 = normalize_drug_list(prescription_text)
    print(f"  ✓ Drugs normalized: {len(mod3.get('drugs', []))}")
    
    # Module 4: Validate diagnosis
    print("\n[Module 4] Diagnosis Validation...")
    mod4 = validate_diagnosis(
        symptoms="dysuria, urgency",
        age=32,
        gender="F",
        diagnosis="urinary tract infection"
    )
    print(f"  ✓ Diagnosis plausible: {mod4.get('is_plausible')}")
    
    # Module 5: Drug appropriateness
    print("\n[Module 5] Drug Appropriateness...")
    mod5 = check_drug_appropriateness(
        normalized_drugs=mod3,
        diagnosis="urinary tract infection"
    )
    print(f"  ✓ Drugs evaluated: {len(mod5.get('drug_evaluation', []))}")
    
    # Module 6: Antibiotic stewardship
    print("\n[Module 6] Antibiotic Stewardship...")
    mod6 = check_antibiotic_stewardship(
        drug_list=mod3.get("drugs", []),
        diagnosis="urinary tract infection",
        patient_age=32,
        patient_gender="F"
    )
    
    print("\n✅ COMBINED ASSESSMENT:")
    print("\nModule 5 - Drug Appropriateness:")
    for eval_item in mod5.get("drug_evaluation", []):
        print(f"  {eval_item.get('drug')}: {eval_item.get('status')}")
    
    print("\nModule 6 - Antibiotic Stewardship:")
    for ab in mod6.get("antibiotics_detected", []):
        print(f"  {ab['drug']}:")
        print(f"    - Spectrum: {ab.get('spectrum_type')}")
        print(f"    - Policy compliant: {ab.get('policy_compliant')}")
        print(f"    - Needs review: {ab.get('needs_review')}")
    
    return {
        "module3": mod3,
        "module4": mod4,
        "module5": mod5,
        "module6": mod6
    }


def example_broad_spectrum_alert():
    """Example flagging unnecessary broad-spectrum use."""
    from backend.modules.module6.antibiotic_stewardship import check_antibiotic_stewardship
    
    print("\n" + "="*70)
    print("EXAMPLE 4: Broad-Spectrum Alert")
    print("="*70)
    
    print("\n⚠️ Scenario: Broad-spectrum used for simple infection")
    print("   Diagnosis: Throat infection")
    print("   Drug: Ceftriaxone 2g IV BID")
    
    drugs = [
        {
            "generic": "ceftriaxone",
            "corrected_name": "ceftriaxone",
            "structured": {"dose": "2g", "route": "IV", "frequency": "BID"}
        }
    ]
    
    result = check_antibiotic_stewardship(
        drug_list=drugs,
        diagnosis="throat infection"
    )
    
    print("\n📊 Assessment:")
    for ab in result.get("antibiotics_detected", []):
        print(f"\n  Drug: {ab['drug']}")
        print(f"  Spectrum: {ab.get('spectrum_type')}")
        print(f"  Spectrum Appropriate: {ab.get('spectrum_appropriate')} ❌")
        print(f"  Needs Review: {ab.get('needs_review')} ⚠️")
        print(f"\n  Recommendation:")
        print(f"  {ab.get('recommendation')}")
        
        alternatives = ab.get("llm_reasoning", {}).get("alternatives", [])
        if alternatives:
            print("\n  Suggested Alternatives:")
            for alt in alternatives:
                print(f"     - {alt}")
    
    return result


def example_diagnostic_uncertainty():
    """Example when diagnosis-antibiotic match is unclear."""
    from backend.modules.module6.antibiotic_stewardship import check_antibiotic_stewardship
    
    print("\n" + "="*70)
    print("EXAMPLE 5: Uncertain Indication")
    print("="*70)
    
    print("\nScenario: Unclear if antibiotic is needed")
    print("  Diagnosis: Viral fever (antibiotics typically not indicated)")
    print("  Drug: Azithromycin 500mg")
    
    drugs = [
        {"generic": "azithromycin", "corrected_name": "azithromycin"}
    ]
    
    result = check_antibiotic_stewardship(
        drug_list=drugs,
        diagnosis="viral fever"
    )
    
    print("\n📊 Assessment:")
    for ab in result.get("antibiotics_detected", []):
        print(f"\n  Drug: {ab['drug']}")
        print(f"  Antibiotic Needed: {ab.get('antibiotic_needed')}")
        print(f"  Needs Review: {ab.get('needs_review')} ⚠️")
        print(f"  Recommendation: {ab.get('recommendation')}")
    
    return result


def main():
    """Run all examples."""
    print("\n" + "="*70)
    print("MODULE 6: ANTIBIOTIC STEWARDSHIP - INTEGRATION EXAMPLES")
    print("="*70)
    
    examples = [
        ("Minimal", example_minimal),
        ("Modules 3, 4, 6", example_with_modules_3_4),
        ("Full Pipeline (3, 4, 5, 6)", example_full_pipeline),
        ("Broad-Spectrum Alert", example_broad_spectrum_alert),
        ("Diagnostic Uncertainty", example_diagnostic_uncertainty),
    ]
    
    results = {}
    
    for name, func in examples:
        try:
            print(f"\n\n{'#' * 70}")
            print(f"# {name}")
            print(f"{'#' * 70}")
            results[name] = func()
            print("✅ Success\n")
        except ImportError as e:
            print(f"⚠️ Skipped: {e}\n")
        except Exception as e:
            print(f"❌ Error: {e}\n")
    
    print("\n" + "="*70)
    print("ALL EXAMPLES COMPLETED")
    print("="*70)
    
    return results


if __name__ == "__main__":
    main()
