# backend/modules/module9/test_module9.py
"""Testing Module 9: Pregnancy Safety Checker"""

import json
from backend.modules.module9.pregnancy_safety import (
    check_pregnancy_safety,
    get_drug_pllr_info,
    list_all_drugs_in_database,
)


def run_test_case():
    """Run a sample pregnancy safety check."""
    
    print("\n" + "="*70)
    print("MODULE 9: PREGNANCY SAFETY CHECKER - TEST")
    print("="*70)
    
    # Test 1: Safe drugs in pregnancy
    print("\n" + "-"*70)
    print("TEST 1: Safe Drugs in Pregnancy (2nd Trimester)")
    print("-"*70)
    
    drugs_safe = [
        {
            "generic": "amoxicillin",
            "corrected_name": "amoxicillin",
            "structured": {"dose": "500mg", "route": "oral"}
        },
        {
            "generic": "acetaminophen",
            "corrected_name": "acetaminophen",
            "structured": {"dose": "500mg", "route": "oral"}
        },
        {
            "generic": "paracetamol",
            "corrected_name": "paracetamol",
            "structured": {"dose": "500mg", "route": "oral"}
        }
    ]
    
    result1 = check_pregnancy_safety(
        drug_list=drugs_safe,
        is_pregnant=True,
        trimester="second"
    )
    
    print("\n✅ RESULT:")
    for drug in result1.get("safety_assessment", []):
        print(f"\n  Drug: {drug['drug']}")
        print(f"    Safe in pregnancy: {drug.get('safe_in_pregnancy')}")
        print(f"    Teratogenicity risk: {drug.get('teratogenicity_risk')}")
        print(f"    FDA Category: {drug.get('fda_category')}")
        print(f"    Requires review: {drug.get('requires_review')}")
    
    summary = result1.get("summary", {})
    print(f"\n  Summary: {summary['safe_count']} safe, {summary['unsafe_count']} unsafe")
    
    # Test 2: Contraindicated drugs
    print("\n" + "-"*70)
    print("TEST 2: Contraindicated Drugs in Pregnancy")
    print("-"*70)
    
    drugs_unsafe = [
        {
            "generic": "tetracycline",
            "corrected_name": "tetracycline",
            "structured": {"dose": "500mg", "route": "oral"}
        },
        {
            "generic": "methotrexate",
            "corrected_name": "methotrexate",
            "structured": {"dose": "5mg", "route": "oral"}
        },
        {
            "generic": "warfarin",
            "corrected_name": "warfarin",
            "structured": {"dose": "5mg", "route": "oral"}
        }
    ]
    
    result2 = check_pregnancy_safety(
        drug_list=drugs_unsafe,
        is_pregnant=True,
        trimester="first"
    )
    
    print("\n⚠️ RESULT:")
    for drug in result2.get("safety_assessment", []):
        print(f"\n  Drug: {drug['drug']}")
        print(f"    Safe in pregnancy: {drug.get('safe_in_pregnancy')}")
        print(f"    Teratogenicity risk: {drug.get('teratogenicity_risk')}")
        print(f"    FDA Category: {drug.get('fda_category')}")
        print(f"    Requires review: {drug.get('requires_review')}")
        if drug.get("alternatives"):
            print(f"    Alternatives: {', '.join(drug['alternatives'])}")
        if drug.get("trimester_warnings"):
            for warning in drug["trimester_warnings"]:
                print(f"    ⚠️  {warning}")
    
    summary = result2.get("summary", {})
    print(f"\n  Summary: {summary['safe_count']} safe, {summary['unsafe_count']} unsafe")
    print(f"  Requires review: {summary['requires_review']}")
    
    # Test 3: Trimester-specific risks
    print("\n" + "-"*70)
    print("TEST 3: Trimester-Specific Risks (NSAIDs in Trimesters)")
    print("-"*70)
    
    drugs_nsaid = [
        {
            "generic": "ibuprofen",
            "corrected_name": "ibuprofen",
            "structured": {"dose": "400mg", "route": "oral"}
        }
    ]
    
    for trimester in ["first", "second", "third"]:
        print(f"\n  Testing ibuprofen in {trimester.upper()} trimester:")
        result = check_pregnancy_safety(
            drug_list=drugs_nsaid,
            is_pregnant=True,
            trimester=trimester
        )
        drug = result["safety_assessment"][0]
        print(f"    Safe: {drug.get('safe_in_pregnancy')}")
        print(f"    Risk: {drug.get('teratogenicity_risk')}")
        if drug.get("trimester_warnings"):
            for w in drug["trimester_warnings"]:
                print(f"    ⚠️  {w}")
    
    # Test 4: Lactation safety
    print("\n" + "-"*70)
    print("TEST 4: Lactation Safety")
    print("-"*70)
    
    drugs_lactation = [
        {
            "generic": "amoxicillin",
            "corrected_name": "amoxicillin",
            "structured": {"dose": "500mg", "route": "oral"}
        },
        {
            "generic": "methotrexate",
            "corrected_name": "methotrexate",
            "structured": {"dose": "5mg", "route": "oral"}
        }
    ]
    
    result4 = check_pregnancy_safety(
        drug_list=drugs_lactation,
        is_lactating=True
    )
    
    print("\n🍼 RESULT:")
    for drug in result4.get("safety_assessment", []):
        print(f"\n  Drug: {drug['drug']}")
        print(f"    Safe for breastfeeding: {drug.get('safe_in_lactation')}")
        print(f"    Lactation risk: {drug.get('lactation_risk')}")
        print(f"    Status: {drug.get('lactation_status')}")
        print(f"    Requires review: {drug.get('requires_review')}")
    
    # Test 5: Look up specific drug
    print("\n" + "-"*70)
    print("TEST 5: Detailed Drug Information")
    print("-"*70)
    
    drug_info = get_drug_pllr_info("fluoxetine")
    if drug_info:
        print("\n  Fluoxetine (SSRI):")
        print(f"    FDA Category: {drug_info.get('fda_category')}")
        print(f"    PLLR Category: {drug_info.get('pllr_pregnancy')}")
        print(f"    Pregnancy Risk: {drug_info.get('pregnancy_risk')}")
        print(f"    Lactation: {drug_info.get('lactation')}")
        print(f"    Comments: {drug_info.get('comments')}")
    
    # Test 6: List available drugs
    print("\n" + "-"*70)
    print("TEST 6: Drugs in Database")
    print("-"*70)
    
    drugs_list = list_all_drugs_in_database()
    print(f"\n  Total drugs in database: {len(drugs_list)}")
    print(f"  Available: {', '.join(drugs_list[:10])}...")
    
    print("\n" + "="*70)
    print("ALL TESTS COMPLETED")
    print("="*70 + "\n")
    
    return {
        "test_safe": result1,
        "test_unsafe": result2,
        "test_lactation": result4,
        "available_drugs": drugs_list,
    }


if __name__ == "__main__":
    run_test_case()
