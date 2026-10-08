#!/usr/bin/env python3
"""
Module 9: Pregnancy Safety Checker

Purpose:
- Check drug safety in pregnancy using FDA PLLR (Pregnancy and Lactation Labeling Rule).
- Evaluate teratogenicity risk, lactation risk, and trimester-specific concerns.
- Provide evidence-based recommendations for pregnant/lactating patients.

Features:
- Load FDA PLLR data from local JSON database.
- Trimester-specific safety assessment (1st, 2nd, 3rd trimester).
- Teratogenicity risk classification.
- Lactation safety evaluation.
- Evidence-based clinical recommendations.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# =========================================================
# 🔹 Configuration
# =========================================================

DEFAULT_PLLR_DATABASE = os.getenv(
    "FDA_PLLR_DATABASE",
    "/home/kart/Desktop/Kshema/data/fda_pllr_database.json"
)

# =========================================================
# 🔹 FDA PLLR Risk Categories
# =========================================================

# Teratogenicity Risk Categories (FDA Legacy System)
# X: Contraindicated in pregnancy
# D: Negative evidence of fetal risk (but benefits may warrant use)
# C: No human studies; animal studies show adverse effects or no data
# B: No adverse effects in animal studies; no human data or adverse in animals but not humans
# A: Adequate human studies show no fetal risk

TERATOGENICITY_CATEGORIES = {
    "A": {
        "name": "Adequate and well-controlled studies",
        "description": "Adequate and well-controlled studies in pregnant women have failed to demonstrate risk to the fetus in any trimester",
        "risk_level": "minimal",
        "safe_in_pregnancy": True,
    },
    "B": {
        "name": "Animal studies show no risk",
        "description": "Animal reproduction studies have failed to demonstrate risk to the fetus and there are no adequate and well-controlled studies in pregnant women",
        "risk_level": "low",
        "safe_in_pregnancy": True,
    },
    "C": {
        "name": "Animal studies show adverse effects",
        "description": "Animal reproduction studies have shown an adverse effect on the fetus and there are no adequate and well-controlled studies in humans",
        "risk_level": "moderate",
        "safe_in_pregnancy": False,
    },
    "D": {
        "name": "Evidence of fetal risk",
        "description": "There is positive evidence of human fetal risk, but the benefits from use in pregnant women may be acceptable despite potential risks",
        "risk_level": "high",
        "safe_in_pregnancy": False,
    },
    "X": {
        "name": "Contraindicated in pregnancy",
        "description": "Studies in animals or humans have demonstrated fetal abnormalities and/or there is positive evidence of human fetal risk, and the risks involved in use of the drug in pregnant women clearly outweigh potential benefits",
        "risk_level": "very_high",
        "safe_in_pregnancy": False,
    },
}

# PLLR Risk Categories (FDA New System, more detailed)
PLLR_PREGNANCY_CATEGORIES = {
    "Category 1": {
        "name": "Adequate human studies",
        "description": "Adequate and well-controlled human studies have not shown an increased risk of abnormalities",
        "risk_level": "minimal",
    },
    "Category 2": {
        "name": "Limited human data",
        "description": "Human data are available but either limited or cannot rule out small increases in fetal abnormalities",
        "risk_level": "low",
    },
    "Category 3": {
        "name": "Animal data only",
        "description": "Animal data are available, but limited human data, or no human data",
        "risk_level": "moderate",
    },
    "Not Recommended": {
        "name": "Contraindicated",
        "description": "Studies or post-marketing data have demonstrated fetal abnormalities and/or there is positive evidence of human fetal risk",
        "risk_level": "very_high",
    },
}

LACTATION_CATEGORIES = {
    "Safe": {
        "description": "Compatible with breastfeeding; minimally absorbed by infant",
        "risk_level": "minimal",
    },
    "Probably Safe": {
        "description": "Limited data; likely safe for breastfeeding",
        "risk_level": "low",
    },
    "Unknown": {
        "description": "Insufficient data; use caution during breastfeeding",
        "risk_level": "moderate",
    },
    "Probably Unsafe": {
        "description": "Some evidence of harm; consider avoiding breastfeeding",
        "risk_level": "high",
    },
    "Contraindicated": {
        "description": "Evidence of significant harm; do not breastfeed",
        "risk_level": "very_high",
    },
}

# =========================================================
# 🔹 Hardcoded PLLR Database (Fallback)
# =========================================================

DEFAULT_PLLR_DATA = {
    "database_version": "1.0",
    "last_updated": "2026-05-27",
    "source": "FDA PLLR and Clinical References",
    "drugs": {
        "amoxicillin": {
            "generic_name": "amoxicillin",
            "fda_category": "B",
            "pllr_pregnancy": "Category 1",
            "pregnancy_risk": "Adequate studies show no increased fetal risk",
            "teratogenicity_risk": "minimal",
            "lactation": "Safe",
            "lactation_risk": "minimal",
            "trimester_specific": {
                "first": {
                    "safe": True,
                    "risk": "minimal",
                    "notes": "No increased risk of birth defects"
                },
                "second": {
                    "safe": True,
                    "risk": "minimal",
                    "notes": "Safe throughout pregnancy"
                },
                "third": {
                    "safe": True,
                    "risk": "minimal",
                    "notes": "Safe in labor and delivery"
                }
            },
            "recommended_alternatives": [],
            "comments": "First-line antibiotic for pregnant women with infections"
        },
        "azithromycin": {
            "generic_name": "azithromycin",
            "fda_category": "B",
            "pllr_pregnancy": "Category 1",
            "pregnancy_risk": "Limited data; likely safe",
            "teratogenicity_risk": "low",
            "lactation": "Safe",
            "lactation_risk": "minimal",
            "trimester_specific": {
                "first": {
                    "safe": True,
                    "risk": "low",
                    "notes": "No increased risk of malformations"
                },
                "second": {
                    "safe": True,
                    "risk": "low",
                    "notes": "Safe for maternal infections"
                },
                "third": {
                    "safe": True,
                    "risk": "low",
                    "notes": "Safe before delivery"
                }
            },
            "recommended_alternatives": [],
            "comments": "Good alternative to amoxicillin if allergy present"
        },
        "tetracycline": {
            "generic_name": "tetracycline",
            "fda_category": "D",
            "pllr_pregnancy": "Not Recommended",
            "pregnancy_risk": "Teratogenic; causes dental staining and bone hypoplasia",
            "teratogenicity_risk": "high",
            "lactation": "Probably Unsafe",
            "lactation_risk": "moderate",
            "trimester_specific": {
                "first": {
                    "safe": False,
                    "risk": "high",
                    "notes": "Avoid - possible skeletal effects"
                },
                "second": {
                    "safe": False,
                    "risk": "high",
                    "notes": "Causes permanent dental staining"
                },
                "third": {
                    "safe": False,
                    "risk": "high",
                    "notes": "Avoid - dental staining in fetus"
                }
            },
            "recommended_alternatives": ["amoxicillin", "azithromycin", "cephalexin"],
            "comments": "Contraindicated throughout pregnancy"
        },
        "methotrexate": {
            "generic_name": "methotrexate",
            "fda_category": "X",
            "pllr_pregnancy": "Not Recommended",
            "pregnancy_risk": "Teratogenic; causes multiple birth defects",
            "teratogenicity_risk": "very_high",
            "lactation": "Contraindicated",
            "lactation_risk": "very_high",
            "trimester_specific": {
                "first": {
                    "safe": False,
                    "risk": "very_high",
                    "notes": "Contraindicated - severe malformations"
                },
                "second": {
                    "safe": False,
                    "risk": "very_high",
                    "notes": "Contraindicated - adverse fetal effects"
                },
                "third": {
                    "safe": False,
                    "risk": "very_high",
                    "notes": "Contraindicated - adverse effects"
                }
            },
            "recommended_alternatives": [],
            "comments": "Absolute contraindication in pregnancy - highly teratogenic"
        },
        "ibuprofen": {
            "generic_name": "ibuprofen",
            "fda_category": "C",
            "pllr_pregnancy": "Category 2",
            "pregnancy_risk": "Safe in first/second trimester; avoid in third",
            "teratogenicity_risk": "low",
            "lactation": "Safe",
            "lactation_risk": "minimal",
            "trimester_specific": {
                "first": {
                    "safe": True,
                    "risk": "minimal",
                    "notes": "Acceptable; limited data but likely safe"
                },
                "second": {
                    "safe": True,
                    "risk": "low",
                    "notes": "Safe but preferred alternatives available"
                },
                "third": {
                    "safe": False,
                    "risk": "high",
                    "notes": "AVOID - increases risk of closure of PDA, oligohydramnios"
                }
            },
            "recommended_alternatives": ["acetaminophen"],
            "comments": "Use acetaminophen preferentially; avoid NSAIDs in third trimester"
        },
        "acetaminophen": {
            "generic_name": "acetaminophen",
            "fda_category": "A",
            "pllr_pregnancy": "Category 1",
            "pregnancy_risk": "Safe; most studied analgesic in pregnancy",
            "teratogenicity_risk": "minimal",
            "lactation": "Safe",
            "lactation_risk": "minimal",
            "trimester_specific": {
                "first": {
                    "safe": True,
                    "risk": "minimal",
                    "notes": "First-line analgesic/antipyretic"
                },
                "second": {
                    "safe": True,
                    "risk": "minimal",
                    "notes": "Safe throughout pregnancy"
                },
                "third": {
                    "safe": True,
                    "risk": "minimal",
                    "notes": "Safe in labor and delivery"
                }
            },
            "recommended_alternatives": [],
            "comments": "Preferred analgesic/antipyretic for all pregnancies"
        },
        "lisinopril": {
            "generic_name": "lisinopril",
            "fda_category": "D",
            "pllr_pregnancy": "Not Recommended",
            "pregnancy_risk": "Renal dysgenesis and oligohydramnios, especially 2nd/3rd trimester",
            "teratogenicity_risk": "high",
            "lactation": "Safe",
            "lactation_risk": "minimal",
            "trimester_specific": {
                "first": {
                    "safe": True,
                    "risk": "low",
                    "notes": "Possibly safe; most risk in 2nd/3rd trimester"
                },
                "second": {
                    "safe": False,
                    "risk": "high",
                    "notes": "AVOID - risk of renal dysgenesis"
                },
                "third": {
                    "safe": False,
                    "risk": "high",
                    "notes": "AVOID - adverse renal effects, oligohydramnios"
                }
            },
            "recommended_alternatives": ["labetalol", "nifedipine", "hydralazine"],
            "comments": "Switch to safer alternatives in pregnancy"
        },
        "fluoxetine": {
            "generic_name": "fluoxetine",
            "fda_category": "C",
            "pllr_pregnancy": "Category 2",
            "pregnancy_risk": "Limited data; generally safe but continued surveillance recommended",
            "teratogenicity_risk": "low",
            "lactation": "Probably Safe",
            "lactation_risk": "low",
            "trimester_specific": {
                "first": {
                    "safe": True,
                    "risk": "low",
                    "notes": "No clear increased risk of major malformations"
                },
                "second": {
                    "safe": True,
                    "risk": "low",
                    "notes": "Safe; may continue treatment"
                },
                "third": {
                    "safe": True,
                    "risk": "low",
                    "notes": "Some neonatal effects possible; monitor"
                }
            },
            "recommended_alternatives": [],
            "comments": "Benefits of treatment usually outweigh risks"
        },
        "warfarin": {
            "generic_name": "warfarin",
            "fda_category": "X",
            "pllr_pregnancy": "Not Recommended",
            "pregnancy_risk": "Teratogenic; causes fetal warfarin syndrome",
            "teratogenicity_risk": "very_high",
            "lactation": "Safe",
            "lactation_risk": "minimal",
            "trimester_specific": {
                "first": {
                    "safe": False,
                    "risk": "very_high",
                    "notes": "Causes nasal hypoplasia, bone abnormalities"
                },
                "second": {
                    "safe": False,
                    "risk": "high",
                    "notes": "CNS and eye malformations possible"
                },
                "third": {
                    "safe": False,
                    "risk": "high",
                    "notes": "Fetal hemorrhage risk"
                }
            },
            "recommended_alternatives": ["heparin", "low molecular weight heparin"],
            "comments": "Use heparin instead during pregnancy"
        },
        "paracetamol": {
            "generic_name": "paracetamol",
            "fda_category": "A",
            "pllr_pregnancy": "Category 1",
            "pregnancy_risk": "Safe; extensively used in pregnancy",
            "teratogenicity_risk": "minimal",
            "lactation": "Safe",
            "lactation_risk": "minimal",
            "trimester_specific": {
                "first": {
                    "safe": True,
                    "risk": "minimal",
                    "notes": "No increased risk of defects"
                },
                "second": {
                    "safe": True,
                    "risk": "minimal",
                    "notes": "Safe; first-line analgesic"
                },
                "third": {
                    "safe": True,
                    "risk": "minimal",
                    "notes": "Safe in labor; does not affect bleeding"
                }
            },
            "recommended_alternatives": [],
            "comments": "Preferred pain reliever in pregnancy"
        },
        "doxycycline": {
            "generic_name": "doxycycline",
            "fda_category": "D",
            "pllr_pregnancy": "Not Recommended",
            "pregnancy_risk": "Dental staining; enamel hypoplasia",
            "teratogenicity_risk": "moderate",
            "lactation": "Safe",
            "lactation_risk": "minimal",
            "trimester_specific": {
                "first": {
                    "safe": False,
                    "risk": "moderate",
                    "notes": "Avoid if possible"
                },
                "second": {
                    "safe": False,
                    "risk": "high",
                    "notes": "Causes dental staining"
                },
                "third": {
                    "safe": False,
                    "risk": "high",
                    "notes": "Permanent dental discoloration"
                }
            },
            "recommended_alternatives": ["amoxicillin", "cephalexin"],
            "comments": "Contraindicated; use alternative antibiotics"
        },
    }
}

# =========================================================
# 🔹 PLLR Database Management
# =========================================================

_PLLR_DATABASE: dict[str, Any] | None = None
_PLLR_LOAD_ERROR: str | None = None


def _load_pllr_database(database_path: str = DEFAULT_PLLR_DATABASE) -> tuple[dict[str, Any] | None, str | None]:
    """Load FDA PLLR database from JSON file. Falls back to hardcoded data."""
    global _PLLR_DATABASE, _PLLR_LOAD_ERROR

    if _PLLR_DATABASE is not None:
        return _PLLR_DATABASE, None

    # Try to load from file
    if Path(database_path).exists():
        try:
            with open(database_path, "r") as f:
                _PLLR_DATABASE = json.load(f)
                return _PLLR_DATABASE, None
        except Exception as e:
            err = f"Error loading PLLR database: {str(e)}"
            _PLLR_LOAD_ERROR = err

    # Use default hardcoded database
    _PLLR_DATABASE = DEFAULT_PLLR_DATA
    return _PLLR_DATABASE, _PLLR_LOAD_ERROR


# =========================================================
# 🔹 Drug Lookup
# =========================================================


def _get_drug_pllr_data(drug_name: str) -> dict[str, Any] | None:
    """Retrieve PLLR data for a drug."""
    db, _ = _load_pllr_database()

    if not db:
        return None

    drug_lower = (drug_name or "").lower().strip()
    drugs = db.get("drugs", {})

    # Direct match
    if drug_lower in drugs:
        return drugs[drug_lower]

    # Partial match
    for key, data in drugs.items():
        if drug_lower in key or key in drug_lower:
            return data
        if data.get("generic_name", "").lower() == drug_lower:
            return data

    return None


# =========================================================
# 🔹 Safety Assessment Functions
# =========================================================


def _assess_teratogenicity(
    drug_pllr: dict[str, Any],
    trimester: str | None = None
) -> dict[str, Any]:
    """Assess teratogenicity risk from PLLR data."""
    fda_category = drug_pllr.get("fda_category", "Unknown")
    pllr_pregnancy = drug_pllr.get("pllr_pregnancy", "Unknown")

    # Get category info
    category_info = TERATOGENICITY_CATEGORIES.get(fda_category, {})

    risk_level = category_info.get("risk_level", "unknown")
    safe = category_info.get("safe_in_pregnancy", False)

    # Trimester-specific assessment
    trimester_data = {}
    if trimester:
        ts = drug_pllr.get("trimester_specific", {}).get(trimester.lower())
        if ts:
            trimester_data = {
                "trimester": trimester,
                "safe": ts.get("safe", None),
                "risk": ts.get("risk", "unknown"),
                "notes": ts.get("notes", "")
            }

    return {
        "fda_category": fda_category,
        "pllr_category": pllr_pregnancy,
        "risk_level": risk_level,
        "safe_in_pregnancy": safe,
        "trimester_specific": trimester_data,
        "description": category_info.get("description", ""),
    }


def _assess_lactation(drug_pllr: dict[str, Any]) -> dict[str, Any]:
    """Assess lactation safety from PLLR data."""
    lactation_status = drug_pllr.get("lactation", "Unknown")
    lactation_info = LACTATION_CATEGORIES.get(lactation_status, {})

    return {
        "lactation_status": lactation_status,
        "risk_level": lactation_info.get("risk_level", "unknown"),
        "description": lactation_info.get("description", ""),
        "lactation_risk": drug_pllr.get("lactation_risk", "unknown"),
    }


def _check_trimester_warnings(
    drug_pllr: dict[str, Any],
    trimester: str | None = None
) -> list[str]:
    """Generate trimester-specific warnings."""
    warnings = []

    trimester_data = drug_pllr.get("trimester_specific", {})

    if trimester:
        ts = trimester_data.get(trimester.lower())
        if ts:
            if not ts.get("safe", False):
                warnings.append(f"Not safe in {trimester} trimester")
            if ts.get("notes"):
                warnings.append(ts.get("notes", ""))
    else:
        # Generate general warnings for all trimesters
        for tri, ts in trimester_data.items():
            if not ts.get("safe", False):
                warnings.append(f"Caution in {tri} trimester: {ts.get('notes', '')}")

    return warnings


# =========================================================
# 🔹 Main Pregnancy Safety Check
# =========================================================


def check_pregnancy_safety(
    *,
    drug_list: list[dict[str, Any]],
    is_pregnant: bool = False,
    is_lactating: bool = False,
    trimester: str | None = None,
) -> dict[str, Any]:
    """
    Check pregnancy and lactation safety of drugs.

    Args:
        drug_list: List of drugs (from module 3)
        is_pregnant: Is patient pregnant?
        is_lactating: Is patient lactating?
        trimester: Current trimester ('first', 'second', 'third') - only if pregnant

    Returns:
        JSON with pregnancy safety assessment per drug
    """
    if not is_pregnant and not is_lactating:
        return {
            "safety_assessment": [],
            "summary": {
                "total_drugs": len(drug_list),
                "safe_count": 0,
                "unsafe_count": 0,
                "requires_review": False,
            },
            "warning": "Not evaluated for pregnancy/lactation - neither flag set",
            "error": None,
        }

    # Validate trimester if pregnant
    if is_pregnant and trimester:
        trimester = trimester.lower().strip()
        if trimester not in ("first", "second", "third", "1st", "2nd", "3rd"):
            return {
                "safety_assessment": [],
                "summary": {"total_drugs": len(drug_list)},
                "error": f"Invalid trimester: {trimester}. Use 'first', 'second', or 'third'",
            }
        # Normalize trimester
        trimester = {"1st": "first", "2nd": "second", "3rd": "third"}.get(trimester, trimester)

    results: list[dict[str, Any]] = []
    safe_count = 0
    unsafe_count = 0

    for drug in drug_list:
        if not isinstance(drug, dict):
            continue

        drug_name = (
            drug.get("generic")
            or drug.get("name")
            or drug.get("corrected_name")
            or ""
        ).strip()

        if not drug_name:
            continue

        # Lookup PLLR data
        drug_pllr = _get_drug_pllr_data(drug_name)

        result = {
            "drug": drug_name,
            "found_in_database": drug_pllr is not None,
        }

        if not drug_pllr:
            # Drug not found in database
            result.update({
                "safe_in_pregnancy": None,
                "safe_in_lactation": None,
                "teratogenicity_risk": "unknown",
                "lactation_risk": "unknown",
                "trimester_warnings": ["Drug not found in PLLR database - manual review required"],
                "recommendation": "MANUAL REVIEW REQUIRED - Consult clinical references",
                "requires_review": True,
            })
        else:
            # Assess teratogenicity
            terato = _assess_teratogenicity(drug_pllr, trimester if is_pregnant else None)

            # Assess lactation
            lactation = _assess_lactation(drug_pllr)

            # Get trimester warnings
            warnings = _check_trimester_warnings(drug_pllr, trimester if is_pregnant else None)

            # Determine safety flags
            safe_pregnancy = terato["safe_in_pregnancy"] if is_pregnant else None
            safe_lactation = lactation["lactation_status"] in ("Safe", "Probably Safe") if is_lactating else None

            # Generate recommendation
            recommendations = []
            if is_pregnant:
                if not safe_pregnancy:
                    recommendations.append(
                        f"❌ NOT SAFE IN PREGNANCY - {drug_pllr.get('pregnancy_risk', '')}"
                    )
                    if drug_pllr.get("recommended_alternatives"):
                        recommendations.append(
                            f"Consider alternatives: {', '.join(drug_pllr['recommended_alternatives'])}"
                        )
                else:
                    recommendations.append(
                        f"✓ Safe in pregnancy - {drug_pllr.get('pregnancy_risk', '')}"
                    )

            if is_lactating:
                if not safe_lactation:
                    recommendations.append(
                        f"❌ NOT SAFE FOR BREASTFEEDING - {lactation.get('description', '')}"
                    )
                else:
                    recommendations.append(
                        f"✓ Safe for breastfeeding - {lactation.get('description', '')}"
                    )

            if drug_pllr.get("comments"):
                recommendations.append(f"Note: {drug_pllr.get('comments')}")

            result.update({
                "safe_in_pregnancy": safe_pregnancy,
                "safe_in_lactation": safe_lactation,
                "teratogenicity_risk": terato.get("risk_level", "unknown"),
                "fda_category": terato.get("fda_category", "Unknown"),
                "pllr_category": terato.get("pllr_category", "Unknown"),
                "lactation_risk": lactation.get("risk_level", "unknown"),
                "lactation_status": lactation.get("lactation_status", "Unknown"),
                "trimester_warnings": warnings,
                "pregnancy_risk_description": drug_pllr.get("pregnancy_risk", ""),
                "lactation_risk_description": lactation.get("description", ""),
                "recommendation": " ".join(recommendations) if recommendations else "Consult clinical guidelines",
                "requires_review": (
                    (is_pregnant and not safe_pregnancy) or
                    (is_lactating and not safe_lactation) or
                    len(warnings) > 0 or
                    drug_pllr.get("fda_category") in ("D", "X", "C")
                ),
                "alternatives": drug_pllr.get("recommended_alternatives", []),
            })

            # Count safety status
            if is_pregnant and safe_pregnancy:
                safe_count += 1
            elif is_lactating and safe_lactation:
                safe_count += 1
            else:
                unsafe_count += 1

        results.append(result)

    requires_review = any(r.get("requires_review", False) for r in results)

    return {
        "safety_assessment": results,
        "summary": {
            "total_drugs": len(drug_list),
            "drugs_evaluated": len(results),
            "safe_count": safe_count,
            "unsafe_count": unsafe_count,
            "requires_review": requires_review,
            "is_pregnant": is_pregnant,
            "is_lactating": is_lactating,
            "trimester": trimester if is_pregnant else None,
            "database_source": "PLLR - FDA Pregnancy and Lactation Labeling Rule",
        },
        "error": None,
    }


# =========================================================
# 🔹 Integration Helper
# =========================================================


def check_from_module_outputs(
    *,
    module3_normalized_drugs: dict[str, Any],
    module4_validation: dict[str, Any],
    is_pregnant: bool = False,
    is_lactating: bool = False,
    trimester: str | None = None,
) -> dict[str, Any]:
    """
    Convenience wrapper to use module 3 & 4 outputs directly.

    Expects:
    - module3_normalized_drugs: Output from drug normalization (module 3)
    - module4_validation: Diagnosis validation output (module 4)
    - is_pregnant: Is patient pregnant?
    - is_lactating: Is patient lactating?
    - trimester: Current trimester if pregnant
    """
    drugs = module3_normalized_drugs.get("drugs", [])

    return check_pregnancy_safety(
        drug_list=drugs,
        is_pregnant=is_pregnant,
        is_lactating=is_lactating,
        trimester=trimester,
    )


# =========================================================
# 🔹 Utility Functions
# =========================================================


def get_drug_pllr_info(drug_name: str) -> dict[str, Any] | None:
    """Get full PLLR information for a drug."""
    return _get_drug_pllr_data(drug_name)


def list_all_drugs_in_database() -> list[str]:
    """List all drugs available in PLLR database."""
    db, _ = _load_pllr_database()
    if not db:
        return []
    return sorted(list(db.get("drugs", {}).keys()))


# =========================================================
# 🔹 CLI
# =========================================================


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Module 9: Pregnancy Safety Checker")
    parser.add_argument("--drugs-json", required=True, help="JSON string of drugs")
    parser.add_argument("--pregnant", action="store_true", help="Patient is pregnant")
    parser.add_argument("--lactating", action="store_true", help="Patient is lactating")
    parser.add_argument("--trimester", help="Trimester (first/second/third)")
    args = parser.parse_args()

    try:
        drugs = json.loads(args.drugs_json)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"Invalid drugs JSON: {exc}"}, indent=2))
        return 1

    result = check_pregnancy_safety(
        drug_list=drugs.get("drugs", []) if isinstance(drugs, dict) else drugs,
        is_pregnant=args.pregnant,
        is_lactating=args.lactating,
        trimester=args.trimester,
    )

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
