"""Orchestrator to run Modules 1..9 in sequence for a prescription audit.

Function: audit_prescription(image_path) -> combined JSON audit

The flow:
 1. Module 1 (OCR) -> read_prescription(image_path)
 2. Module 2 (Drug Normalization) -> normalize_drug_list(corrected_text)
 3. Module 3 (NER) -> extract_med7_entities(corrected_text)
 4. Module 4 (Diagnosis Validator) -> validate_from_ner_output(ner_output)
 5. Module 5 (Drug Appropriateness) -> check_from_module_outputs(module2_normalized_drugs, module4_validation)
 6. Module 6 (Antibiotic Stewardship) -> check_from_module_outputs(module3_normalized_drugs, module4_validation)
 7. Module 7 (Dose Adjustment) -> check_from_module_outputs(module2_normalized_drugs, comorbidities_dict)
 8. Module 8 (DDI Checker) -> check_from_module_outputs(module2_normalized_drugs, module5_appropriateness)
 9. Module 9 (Pregnancy Safety) -> check_from_module_outputs(module3_normalized_drugs, module4_validation)

Each step is guarded so failures do not crash the pipeline; errors are recorded in the returned JSON.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

# Import module entrypoints (guard imports where appropriate)
try:
    from backend.modules.module1.qwen_ocr import read_prescription
except Exception:  # pragma: no cover - best-effort import
    read_prescription = None  # type: ignore

try:
    from backend.modules.module3.drug_normalization import normalize_drug_list
except Exception:
    normalize_drug_list = None  # type: ignore

try:
    from backend.modules.module2.med7_ner import extract_med7_entities
except Exception:
    extract_med7_entities = None  # type: ignore

try:
    from backend.modules.module4.diagnosis_validator import validate_from_ner_output
except Exception:
    validate_from_ner_output = None  # type: ignore

try:
    from backend.modules.module5.drug_appropriateness import check_from_module_outputs as check_appropriateness_from_outputs
except Exception:
    check_appropriateness_from_outputs = None  # type: ignore

try:
    from backend.modules.module6.antibiotic_stewardship import check_from_module_outputs as check_antibiotic_from_outputs
except Exception:
    check_antibiotic_from_outputs = None  # type: ignore

try:
    from backend.modules.module7.dose_adjustment import check_from_module_outputs as check_dose_from_outputs
except Exception:
    check_dose_from_outputs = None  # type: ignore

try:
    from backend.modules.module8.module_8_ddi_checker import check_from_module_outputs as check_ddi_from_outputs
except Exception:
    check_ddi_from_outputs = None  # type: ignore

try:
    from backend.modules.module9.pregnancy_safety import check_from_module_outputs as check_pregnancy_from_outputs
except Exception:
    check_pregnancy_from_outputs = None  # type: ignore


def _build_corrected_text_from_ocr(ocr_output: Dict[str, Any]) -> str:
    """Create a fallback corrected text blob for downstream modules.

    Prefer structured drugs formatting if present. Otherwise fallback to raw_text.
    """
    if not isinstance(ocr_output, dict):
        return ""

    drugs = ocr_output.get("drugs") or []
    if isinstance(drugs, list) and drugs:
        parts: List[str] = []

        # 1. Format Patient Info
        patient = ocr_output.get("patient")
        if isinstance(patient, dict):
            p_parts = []
            name = patient.get("name")
            if name:
                p_parts.append(f"Name: {name}")
            age = patient.get("age")
            if age:
                p_parts.append(f"Age: {age}")
            gender = patient.get("gender")
            if gender:
                p_parts.append(f"Gender: {gender}")
            if p_parts:
                parts.append(", ".join(p_parts))

        # 2. Format Diagnosis
        diag = ocr_output.get("diagnosis")
        if diag:
            parts.append(f"Diagnosis: {diag} Rx:")
        else:
            parts.append("Diagnosis: None Rx:")

        # 3. Format Comorbidities
        comorbid = ocr_output.get("comorbidities") or []
        if isinstance(comorbid, list) and comorbid:
            parts.append(f"Comorbidities: {', '.join([str(x) for x in comorbid])}")

        # 4. Format Pregnancy
        if ocr_output.get("pregnancy") is True or str(ocr_output.get("pregnancy")).lower() == "true":
            parts.append("Pregnancy: Yes")

        # 5. Format Drugs
        parts.append("Rx:")
        for d in drugs:
            if isinstance(d, dict):
                name = d.get("name") or d.get("generic") or d.get("original") or d.get("corrected_name")
                if not name:
                    continue
                d_str = f"Tab. {name}"
                dose = d.get("dose")
                if dose:
                    d_str += f" {dose}"
                route = d.get("route") or d.get("route_of_administration")
                if route:
                    d_str += f" {route}"
                freq = d.get("frequency")
                if freq:
                    d_str += f" {freq}"
                dur = d.get("duration")
                if dur:
                    d_str += f" for {dur}"
                parts.append(d_str)
            else:
                parts.append(f"Tab. {d}")

        return "\n".join(parts)

    if ocr_output.get("raw_text"):
        return str(ocr_output.get("raw_text"))

    return ""


def _build_comorbidities_dict(ocr_output: Dict[str, Any], ner_output: Dict[str, Any], module5_output: Dict[str, Any]) -> Dict[str, Any]:
    """Create a comorbidities dict usable by Module 7 dose adjustment.

    This is best-effort: set boolean flags for CKD and liver_disease when keywords appear.
    """
    combined: List[str] = []
    if isinstance(ocr_output, dict):
        combined.extend([str(x).lower() for x in ocr_output.get("comorbidities") or [] if x])

    if isinstance(ner_output, dict):
        # Extract diagnosis and entity texts
        diag = ner_output.get("diagnosis")
        if isinstance(diag, str) and diag:
            combined.append(diag.lower())
        entities = ner_output.get("entities") or []
        for ent in entities:
            txt = ent.get("text") if isinstance(ent, dict) else None
            if txt:
                combined.append(str(txt).lower())

    if isinstance(module5_output, dict):
        for key in ("comorbidities", "diagnoses", "conditions"):
            raw = module5_output.get(key, [])
            if isinstance(raw, list):
                combined.extend([str(x).lower() for x in raw if x])

    comorb_dict: Dict[str, Any] = {}
    joined = " ".join(combined)
    if any(k in joined for k in ("ckd", "renal", "creatinine", "egfr", "crcl", "kidney")):
        comorb_dict["ckd"] = True
    if any(k in joined for k in ("liver", "hepatic", "cirrhosis", "alt", "ast", "bilirubin")):
        comorb_dict["liver_disease"] = True
    # include raw list for other modules
    comorb_dict["conditions"] = list(dict.fromkeys([s for s in combined if s]))
    return comorb_dict


def _build_comorbidities_list(ocr_output: Dict[str, Any], ner_output: Dict[str, Any], module5_output: Dict[str, Any]) -> List[str]:
    """Build a flat comorbidity list for modules that expect conditions as strings."""
    comorb_dict = _build_comorbidities_dict(ocr_output, ner_output, module5_output)
    return list(comorb_dict.get("conditions") or [])


def audit_prescription(image_path: str) -> Dict[str, Any]:
    """Run end-to-end audit pipeline for a single prescription image.

    Returns a combined JSON dict containing each module's output and an overall summary.
    """
    result: Dict[str, Any] = {
        "image_path": image_path,
        "ocr": None,
        "normalized_drugs": None,
        "ner": None,
        "diagnosis_validation": None,
        "drug_appropriateness": None,
        "antibiotic_stewardship": None,
        "dose_adjustment": None,
        "ddi": None,
        "pregnancy_safety": None,
        "errors": [],
    }

    # -----------------
    # Module 1: OCR
    # -----------------
    ocr_out = None
    try:
        if read_prescription is None:
            raise RuntimeError("Module1 OCR not available (import failed)")
        ocr_out = read_prescription(image_path)
    except Exception as exc:
        ocr_out = {"status": "error", "error": str(exc)}
        result["errors"].append({"module": "ocr", "error": str(exc)})
    result["ocr"] = ocr_out

    # Build corrected text for downstream modules
    corrected_text = _build_corrected_text_from_ocr(ocr_out or {})

    # -----------------
    # Module 2: Drug Normalization
    # -----------------
    normalized = None
    try:
        if normalize_drug_list is None:
            raise RuntimeError("Module2 Drug Normalization not available (import failed)")
        normalized = normalize_drug_list(corrected_text)
    except Exception as exc:
        normalized = {"drugs": [], "meta": {}, "error": str(exc)}
        result["errors"].append({"module": "drug_normalization", "error": str(exc)})
    result["normalized_drugs"] = normalized

    # -----------------
    # Module 3: NER
    # -----------------
    ner_out = None
    try:
        if extract_med7_entities is None:
            raise RuntimeError("Module3 NER not available (import failed)")
        ner_out = extract_med7_entities(corrected_text)
    except Exception as exc:
        ner_out = {"status": "error", "error": str(exc)}
        result["errors"].append({"module": "ner", "error": str(exc)})
    result["ner"] = ner_out

    # -----------------
    # Module 4: Diagnosis Validator
    # -----------------
    diag_val = None
    try:
        if validate_from_ner_output is None:
            raise RuntimeError("Module4 Diagnosis Validator not available (import failed)")
        diag_val = validate_from_ner_output(ner_out or {})
    except Exception as exc:
        diag_val = {"status": "error", "error": str(exc)}
        result["errors"].append({"module": "diagnosis_validator", "error": str(exc)})
    result["diagnosis_validation"] = diag_val

    # -----------------
    # Module 5: Drug Appropriateness
    # -----------------
    app_out = None
    try:
        if check_appropriateness_from_outputs is None:
            raise RuntimeError("Module5 Appropriateness not available (import failed)")
        app_out = check_appropriateness_from_outputs(
            module2_normalized_drugs=normalized or {},
            module4_validation=diag_val or {},
        )
    except Exception as exc:
        app_out = {"drug_evaluation": [], "error": str(exc)}
        result["errors"].append({"module": "drug_appropriateness", "error": str(exc)})
    result["drug_appropriateness"] = app_out

    # -----------------
    # Module 6: Antibiotic Stewardship
    # -----------------
    abx_out = None
    try:
        if check_antibiotic_from_outputs is None:
            raise RuntimeError("Module6 Antibiotic Stewardship not available (import failed)")
        abx_out = check_antibiotic_from_outputs(
            module3_normalized_drugs=normalized or {},
            module4_validation=diag_val or {},
        )
    except Exception as exc:
        abx_out = {"antibiotics_detected": [], "error": str(exc)}
        result["errors"].append({"module": "antibiotic_stewardship", "error": str(exc)})
    result["antibiotic_stewardship"] = abx_out

    # -----------------
    # Module 7: Dose Adjustment
    # -----------------
    dose_out = None
    try:
        if check_dose_from_outputs is None:
            raise RuntimeError("Module7 Dose Adjustment not available (import failed)")
        comorb_dict = _build_comorbidities_dict(ocr_out or {}, ner_out or {}, app_out or {})
        dose_out = check_dose_from_outputs(
            module2_normalized_drugs=normalized or {},
            module3_comorbidities=comorb_dict,
        )
    except Exception as exc:
        dose_out = {"assessments": [], "error": str(exc)}
        result["errors"].append({"module": "dose_adjustment", "error": str(exc)})
    result["dose_adjustment"] = dose_out

    # -----------------
    # Module 8: DDI Checker
    # -----------------
    ddi_out = None
    try:
        if check_ddi_from_outputs is None:
            raise RuntimeError("Module8 DDI Checker not available (import failed)")
        comorb_list = _build_comorbidities_list(ocr_out or {}, ner_out or {}, app_out or {})
        ddi_out = check_ddi_from_outputs(
            module2_normalized_drugs=normalized or {},
            module5_appropriateness=app_out or {},
            comorbidities=comorb_list,
        )
    except Exception as exc:
        ddi_out = {"interactions": [], "drug_disease_interactions": [], "error": str(exc)}
        result["errors"].append({"module": "ddi_checker", "error": str(exc)})
    result["ddi"] = ddi_out

    # -----------------
    # Module 9: Pregnancy Safety
    # -----------------
    preg_out = None
    try:
        if check_pregnancy_from_outputs is None:
            raise RuntimeError("Module9 Pregnancy Safety not available (import failed)")
        # Detect pregnancy flags from OCR or NER
        is_pregnant = False
        is_lactating = False
        if isinstance(ocr_out, dict):
            if ocr_out.get("pregnancy") is True or str(ocr_out.get("pregnancy")).lower() == "true":
                is_pregnant = True
            if ocr_out.get("lactation") is True or str(ocr_out.get("lactation")).lower() == "true":
                is_lactating = True

        preg_out = check_pregnancy_from_outputs(
            module3_normalized_drugs=normalized or {},
            module4_validation=diag_val or {},
            is_pregnant=is_pregnant,
            is_lactating=is_lactating,
            trimester=None,
        )
    except Exception as exc:
        preg_out = {"safety_assessment": [], "error": str(exc)}
        result["errors"].append({"module": "pregnancy_safety", "error": str(exc)})
    result["pregnancy_safety"] = preg_out

    # -----------------
    # Final summary
    # -----------------
    result["summary"] = {
        "modules_executed": [
            "ocr",
            "normalized_drugs",
            "ner",
            "diagnosis_validation",
            "drug_appropriateness",
            "antibiotic_stewardship",
            "dose_adjustment",
            "ddi",
            "pregnancy_safety",
        ],
        "errors": result["errors"],
    }

    return result


if __name__ == "__main__":
    # Test block: run a single image through the pipeline and print JSON
    test_image = os.path.join("archive(2)", "data", "17.jpg")
    audit = audit_prescription(test_image)
    print(json.dumps(audit, indent=2, ensure_ascii=False))
