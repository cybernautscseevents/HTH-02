#!/usr/bin/env python3
"""
Module 9 Integration Examples

Shows how to use Module 9 (Pregnancy Safety Checker) with:
- Standalone usage
- Integration with Module 3 (Drug Normalization)
- Integration with Modules 3 & 4
- Clinical scenario examples
"""

import json
from typing import Any


def example_pregnant_with_infection():
    """Example 1: Pregnant patient with infection."""
    from backend.modules.module9.pregnancy_safety import check_pregnancy_safety
    
    print("\n" + "="*70)
    print("EXAMPLE 1: Pregnant Patient (2nd Trimester) with Infection")
    print("="*70)
    
    print("\n📋 Scenario:")
    print("  - Patient: Pregnant, 18 weeks (2nd trimester)")
    print("  - Chief complaint: Pneumonia symptoms")
    print("  - Current medications: Amoxicillin 500mg TID")
    
    drugs = [
        {"generic": "amoxicillin", "corrected_name": "amoxicillin"},
        {"generic": "acetaminophen", "corrected_name": "acetaminophen"}
    ]
    
    result = check_pregnancy_safety(
        drug_list=drugs,
        is_pregnant=True,
        trimester="second"
    )
    
    print("\n✅ PREGNANCY SAFETY ASSESSMENT:")
    for drug in result.get("safety_assessment", []):
        print(f"\n  Drug: {drug['drug']}")
        print(f"    Safe in pregnancy: {drug.get('safe_in_pregnancy')} ✓")
        print(f"    FDA Category: {drug.get('fda_category')}")
        print(f"    Teratogenicity risk: {drug.get('teratogenicity_risk')}")
        print(f"    Recommendation: {drug.get('recommendation')}")
    
    summary = result.get("summary", {})
    print(f"\n  Summary: {summary['safe_count']} safe, {summary['unsafe_count']} unsafe")
    print(f"  Requires review: {summary['requires_review']}")
    
    return result


def example_contraindicated_medications():
    """Example 2: Medications contraindicated in pregnancy."""
    from backend.modules.module9.pregnancy_safety import check_pregnancy_safety
    
    print("\n" + "="*70)
    print("EXAMPLE 2: Contraindicated Medications in Pregnancy")
    print("="*70)
    
    print("\n📋 Scenario:")
    print("  - Patient: Discovered to be pregnant while on chronic meds")
    print("  - Current meds: Warfarin, Lisinopril, Methotrexate")
    print("  - Need to change all medications")
    
    drugs = [
        {"generic": "warfarin", "corrected_name": "warfarin"},
        {"generic": "lisinopril", "corrected_name": "lisinopril"},
        {"generic": "methotrexate", "corrected_name": "methotrexate"}
    ]
    
    result = check_pregnancy_safety(
        drug_list=drugs,
        is_pregnant=True,
        trimester="first"
    )
    
    print("\n⚠️ CONTRAINDICATION ALERTS:")
    for drug in result.get("safety_assessment", []):
        print(f"\n  Drug: {drug['drug']}")
        print(f"    Safe in pregnancy: {drug.get('safe_in_pregnancy')} ❌")
        print(f"    FDA Category: {drug.get('fda_category')}")
        print(f"    Teratogenicity risk: {drug.get('teratogenicity_risk')}")
        print(f"    Requires review: {drug.get('requires_review')} ⚠️")
        
        if drug.get("alternatives"):
            print(f"    Suggested alternatives:")
            for alt in drug["alternatives"]:
                print(f"      → {alt}")
        
        print(f"    Note: {drug.get('recommendation')}")
    
    return result


def example_trimester_specific():
    """Example 3: Trimester-specific risks (NSAIDs)."""
    from backend.modules.module9.pregnancy_safety import check_pregnancy_safety
    
    print("\n" + "="*70)
    print("EXAMPLE 3: Trimester-Specific Risks (NSAIDs)")
    print("="*70)
    
    print("\n📋 Scenario:")
    print("  - Medication: Ibuprofen for pain relief")
    print("  - Question: Is it safe across all trimesters?")
    
    drugs = [
        {"generic": "ibuprofen", "corrected_name": "ibuprofen"}
    ]
    
    print("\n📅 Checking ibuprofen across all trimesters:")
    
    for trimester in ["first", "second", "third"]:
        result = check_pregnancy_safety(
            drug_list=drugs,
            is_pregnant=True,
            trimester=trimester
        )
        
        drug = result["safety_assessment"][0]
        print(f"\n  {trimester.upper()} TRIMESTER:")
        print(f"    Safe: {drug.get('safe_in_pregnancy')}")
        print(f"    Risk: {drug.get('teratogenicity_risk')}")
        
        if drug.get("trimester_warnings"):
            print(f"    Warnings:")
            for w in drug["trimester_warnings"]:
                print(f"      ⚠️  {w}")
        else:
            print(f"    No warnings")
    
    print("\n💡 CLINICAL IMPLICATION:")
    print("  Safe in 1st/2nd trimester but AVOID in 3rd trimester")
    print("  Use acetaminophen instead, especially near term")
    
    return None


def example_breastfeeding_mother():
    """Example 4: Medications safe for breastfeeding."""
    from backend.modules.module9.pregnancy_safety import check_pregnancy_safety
    
    print("\n" + "="*70)
    print("EXAMPLE 4: Breastfeeding Mother - Lactation Safety")
    print("="*70)
    
    print("\n📋 Scenario:")
    print("  - Patient: Postpartum day 10, planning to breastfeed")
    print("  - Current medications: Amoxicillin, Fluoxetine, Ibuprofen")
    print("  - Question: Are these safe for breastfeeding?")
    
    drugs = [
        {"generic": "amoxicillin", "corrected_name": "amoxicillin"},
        {"generic": "fluoxetine", "corrected_name": "fluoxetine"},
        {"generic": "ibuprofen", "corrected_name": "ibuprofen"}
    ]
    
    result = check_pregnancy_safety(
        drug_list=drugs,
        is_lactating=True
    )
    
    print("\n🍼 LACTATION SAFETY ASSESSMENT:")
    for drug in result.get("safety_assessment", []):
        print(f"\n  Drug: {drug['drug']}")
        print(f"    Safe for breastfeeding: {drug.get('safe_in_lactation')}")
        print(f"    Lactation status: {drug.get('lactation_status')}")
        print(f"    Risk level: {drug.get('lactation_risk')}")
        print(f"    Recommendation: {drug.get('recommendation')}")
        print(f"    Requires review: {drug.get('requires_review')}")
    
    summary = result.get("summary", {})
    print(f"\n  Summary: Safe for breastfeeding? "
          f"{summary['safe_count']} safe, {summary['unsafe_count']} unsafe")
    
    return result


def example_postpartum_transition():
    """Example 5: Transition from pregnancy to postpartum."""
    from backend.modules.module9.pregnancy_safety import check_pregnancy_safety
    
    print("\n" + "="*70)
    print("EXAMPLE 5: Postpartum Medication Transition")
    print("="*70)
    
    print("\n📋 Scenario:")
    print("  - Patient transitioning from pregnancy to postpartum")
    print("  - Medications: Lisinopril (for hypertension), Fluoxetine (for depression)")
    print("  - Planning to breastfeed")
    
    drugs = [
        {"generic": "lisinopril", "corrected_name": "lisinopril"},
        {"generic": "fluoxetine", "corrected_name": "fluoxetine"}
    ]
    
    # 1. Check pregnancy safety (at end of pregnancy)
    print("\n📅 DURING PREGNANCY (Third Trimester):")
    preg_result = check_pregnancy_safety(
        drug_list=drugs,
        is_pregnant=True,
        trimester="third"
    )
    
    for drug in preg_result.get("safety_assessment", []):
        print(f"  {drug['drug']}: "
              f"Safe={drug.get('safe_in_pregnancy')}, "
              f"Risk={drug.get('teratogenicity_risk')}")
    
    # 2. Check lactation safety (postpartum)
    print("\n🍼 POSTPARTUM (Breastfeeding):")
    lact_result = check_pregnancy_safety(
        drug_list=drugs,
        is_lactating=True
    )
    
    for drug in lact_result.get("safety_assessment", []):
        print(f"  {drug['drug']}: "
              f"Safe={drug.get('safe_in_lactation')}, "
              f"Status={drug.get('lactation_status')}")
    
    # 3. Summary
    print("\n💡 MEDICATION MANAGEMENT:")
    print("  Lisinopril:")
    print("    - Before: Safe in early pregnancy only")
    print("    - After: Safe for breastfeeding ✓")
    print("    - Action: Can continue postpartum safely")
    print()
    print("  Fluoxetine:")
    print("    - Before: Probably safe in pregnancy ⚠️")
    print("    - After: Probably safe for breastfeeding ⚠️")
    print("    - Action: Continue; monitor infant for effects")
    
    return {"pregnancy": preg_result, "lactation": lact_result}


def example_preconception_planning():
    """Example 6: Pre-conception medication planning."""
    from backend.modules.module9.pregnancy_safety import check_pregnancy_safety
    
    print("\n" + "="*70)
    print("EXAMPLE 6: Pre-Conception Medication Planning")
    print("="*70)
    
    print("\n📋 Scenario:")
    print("  - Patient: Plans to conceive in 3 months")
    print("  - Current medications: Warfarin, Tetracycline, Metformin")
    print("  - Need to identify drugs to change before conception")
    
    drugs = [
        {"generic": "warfarin", "corrected_name": "warfarin"},
        {"generic": "tetracycline", "corrected_name": "tetracycline"},
        {"generic": "metformin", "corrected_name": "metformin"}
    ]
    
    # Note: is_pregnant=False because not pregnant yet
    result = check_pregnancy_safety(
        drug_list=drugs,
        is_pregnant=False
    )
    
    print("\n🔍 PRE-CONCEPTION REVIEW (Not currently pregnant):")
    print("  (Used to plan medication changes before conception)\n")
    
    for drug in result.get("safety_assessment", []):
        print(f"  Drug: {drug['drug']}")
        
        if drug.get("found_in_database"):
            print(f"    FDA Category: {drug.get('fda_category')}")
            print(f"    Pregnancy safety: {drug.get('pregnancy_risk_description', 'Unknown')}")
            
            if drug.get("fda_category") in ["D", "X"]:
                print(f"    ⚠️ MUST CHANGE before conception")
                if drug.get("alternatives"):
                    print(f"    Alternatives: {', '.join(drug['alternatives'])}")
            else:
                print(f"    ✓ Can continue or change based on indication")
        else:
            print(f"    ⚠️ Not in database - consult specialist")
    
    return result


def example_with_module3():
    """Example 7: Integration with Module 3 (Drug Normalization)."""
    print("\n" + "="*70)
    print("EXAMPLE 7: Integration with Module 3 (Drug Normalization)")
    print("="*70)
    
    print("\n📋 Workflow:")
    print("  1. OCR prescription text")
    print("  2. Module 3: Normalize drugs")
    print("  3. Module 9: Check pregnancy safety")
    
    try:
        from backend.modules.module3.drug_normalization import normalize_drug_list
        from backend.modules.module9.pregnancy_safety import check_pregnancy_safety
        
        # Simulate OCR output
        prescription_text = """
        Patient: Jane Doe, Age 32, Pregnant
        
        Rx:
        Tab Amoxicillin 500mg TID x 7 days
        Tab Paracetamol 500mg TID PRN
        """
        
        print(f"\n📄 OCR Output:\n{prescription_text}")
        
        # Module 3: Normalize
        print("\n[Module 3] Normalizing drugs...")
        normalized = normalize_drug_list(prescription_text)
        print(f"  ✓ Found {len(normalized.get('drugs', []))} drugs")
        
        # Module 9: Check pregnancy safety
        print("\n[Module 9] Checking pregnancy safety...")
        result = check_pregnancy_safety(
            drug_list=normalized.get("drugs", []),
            is_pregnant=True,
            trimester="first"
        )
        
        print("\n✅ RESULT:")
        for drug in result.get("safety_assessment", []):
            print(f"  {drug['drug']}: "
                  f"Safe={'✓' if drug.get('safe_in_pregnancy') else '❌'}, "
                  f"Risk={drug.get('teratogenicity_risk')}")
        
        return result
        
    except ImportError as e:
        print(f"⚠️ Module 3 not available: {e}")
        return None


def main():
    """Run all integration examples."""
    print("\n" + "="*70)
    print("MODULE 9: PREGNANCY SAFETY CHECKER - INTEGRATION EXAMPLES")
    print("="*70)
    
    examples = [
        ("Pregnant with Infection", example_pregnant_with_infection),
        ("Contraindicated Medications", example_contraindicated_medications),
        ("Trimester-Specific Risks", example_trimester_specific),
        ("Breastfeeding Mother", example_breastfeeding_mother),
        ("Postpartum Transition", example_postpartum_transition),
        ("Pre-Conception Planning", example_preconception_planning),
        ("Integration with Module 3", example_with_module3),
    ]
    
    results = {}
    
    for name, func in examples:
        try:
            print(f"\n\n{'#' * 70}")
            print(f"# {name}")
            print(f"{'#' * 70}")
            results[name] = func()
            print("✅ Success\n")
        except Exception as e:
            print(f"❌ Error: {e}\n")
    
    print("\n" + "="*70)
    print("ALL EXAMPLES COMPLETED")
    print("="*70)
    
    return results


if __name__ == "__main__":
    main()
