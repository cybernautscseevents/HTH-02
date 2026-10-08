#!/usr/bin/env python3
"""
Module 6: Antibiotic Stewardship Checker

Purpose:
- Validate prescribed antibiotics against hospital antibiotic policy.
- Classify antibiotic spectrum (narrow/moderate/broad) and check appropriateness.
- Check prescribed dose against policy dose ranges.
- Provide clinical reasoning via Mistral LLM (optional, graceful fallback).

Features:
- Load structured hospital policy from JSON template (hospital_policy_template.json).
- Retrieve policy guidance for diagnosis-antibiotic pairs.
- Classify antibiotics by spectrum (narrow/moderate/broad).
- Check diagnosis-indication appropriateness against guidelines.
- Validate dose against policy dose ranges.
- Return structured JSON with stewardship assessment.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# =========================================================
# 🔹 Configuration
# =========================================================

_MODULE_DIR = Path(__file__).resolve().parent

DEFAULT_OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral:7b-instruct-q4_K_M")
DEFAULT_POLICY_JSON = os.getenv(
    "HOSPITAL_ANTIBIOTIC_POLICY_JSON",
    str(_MODULE_DIR / "hospital_policy_template.json")
)
DEFAULT_TIMEOUT = float(os.getenv("STEWARDSHIP_TIMEOUT", "120"))

# =========================================================
# 🔹 Antibiotic Spectrum Classification
# =========================================================

NARROW_SPECTRUM = {
    "penicillin v",
    "penicillin g",
    "oxacillin",
    "nafcillin",
    "methicillin",
    "cloxacillin",
    "dicloxacillin",
    "amoxicillin",
    "erythromycin",
    "azithromycin",
    "clarithromycin",
}

MODERATE_SPECTRUM = {
    "amoxicillin clavulanate",
    "augmentin",
    "cephalexin",
    "cefadroxil",
    "cefuroxime",
    "cefixime",
    "ciprofloxacin",
    "levofloxacin",
    "trimethoprim sulfamethoxazole",
    "bactrim",
    "cotrim",
}

BROAD_SPECTRUM = {
    "piperacillin tazobactam",
    "zosyn",
    "meropenem",
    "ertapenem",
    "imipenem",
    "ceftriaxone",
    "cefotaxime",
    "cefepime",
    "ceftazidime",
    "aztreonam",
}

# Indication-antibiotic mapping (clinical guidelines)
INDICATION_ANTIBIOTICS = {
    "pneumonia": {
        "first_line": ["amoxicillin", "amoxicillin clavulanate"],
        "alternatives": ["cephalexin", "azithromycin"],
        "broad_spectrum": ["ceftriaxone", "cefotaxime"],
        "avoid": [],
    },
    "uti": {
        "first_line": ["trimethoprim sulfamethoxazole", "nitrofurantoin"],
        "alternatives": ["ciprofloxacin", "cephalexin"],
        "broad_spectrum": ["piperacillin tazobactam"],
        "avoid": [],
    },
    "urinary tract infection": {
        "first_line": ["trimethoprim sulfamethoxazole", "nitrofurantoin"],
        "alternatives": ["ciprofloxacin", "cephalexin"],
        "broad_spectrum": ["piperacillin tazobactam"],
        "avoid": [],
    },
    "skin infection": {
        "first_line": ["amoxicillin", "oxacillin"],
        "alternatives": ["cephalexin", "cloxacillin"],
        "broad_spectrum": ["ceftriaxone"],
        "avoid": [],
    },
    "throat infection": {
        "first_line": ["penicillin v", "amoxicillin"],
        "alternatives": ["erythromycin", "azithromycin"],
        "broad_spectrum": ["ceftriaxone"],
        "avoid": [],
    },
    "respiratory tract infection": {
        "first_line": ["amoxicillin", "azithromycin"],
        "alternatives": ["cephalexin", "erythromycin"],
        "broad_spectrum": ["ceftriaxone", "cefotaxime"],
        "avoid": [],
    },
    "sepsis": {
        "first_line": ["ceftriaxone", "piperacillin tazobactam"],
        "alternatives": ["meropenem", "ciprofloxacin"],
        "broad_spectrum": ["meropenem", "imipenem"],
        "avoid": [],
    },
    "meningitis": {
        "first_line": ["ceftriaxone", "cefotaxime"],
        "alternatives": ["meropenem", "ampicillin"],
        "broad_spectrum": ["meropenem"],
        "avoid": [],
    },
    "sinusitis": {
        "first_line": ["amoxicillin", "amoxicillin clavulanate"],
        "alternatives": ["cephalexin", "azithromycin"],
        "broad_spectrum": ["ceftriaxone", "levofloxacin"],
        "avoid": [],
    },
    "otitis media": {
        "first_line": ["amoxicillin", "amoxicillin clavulanate"],
        "alternatives": ["cephalexin", "azithromycin"],
        "broad_spectrum": ["ceftriaxone"],
        "avoid": [],
    },
    "bronchitis": {
        "first_line": ["azithromycin", "amoxicillin"],
        "alternatives": ["cephalexin", "erythromycin"],
        "broad_spectrum": ["ceftriaxone", "levofloxacin"],
        "avoid": [],
    },
    "cellulitis": {
        "first_line": ["cephalexin", "cloxacillin"],
        "alternatives": ["amoxicillin clavulanate", "clindamycin"],
        "broad_spectrum": ["ceftriaxone", "piperacillin tazobactam"],
        "avoid": [],
    },
}

# =========================================================
# 🔹 Antibiotic Metadata
# =========================================================

ANTIBIOTIC_METADATA = {
    "amoxicillin": {
        "class": "Beta-lactam",
        "spectrum": "narrow",
        "common_indications": ["otitis media", "pneumonia", "uti", "skin infection"],
    },
    "amoxicillin clavulanate": {
        "class": "Beta-lactam + Beta-lactamase inhibitor",
        "spectrum": "moderate",
        "common_indications": ["pneumonia", "skin infection", "sinusitis"],
    },
    "azithromycin": {
        "class": "Macrolide",
        "spectrum": "narrow",
        "common_indications": ["respiratory tract infection", "throat infection"],
    },
    "ciprofloxacin": {
        "class": "Fluoroquinolone",
        "spectrum": "moderate",
        "common_indications": ["uti", "respiratory tract infection"],
    },
    "ceftriaxone": {
        "class": "3rd gen Cephalosporin",
        "spectrum": "broad",
        "common_indications": ["pneumonia", "meningitis"],
    },
    "trimethoprim sulfamethoxazole": {
        "class": "Sulfonamide",
        "spectrum": "moderate",
        "common_indications": ["uti"],
    },
}

# =========================================================
# 🔹 JSON Policy Loader
# =========================================================

_POLICY_JSON: dict[str, Any] | None = None
_POLICY_JSON_ERROR: str | None = None


def _load_json_policy(
    json_path: str = DEFAULT_POLICY_JSON,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Load structured hospital antibiotic policy from JSON template.

    Returns (policy_dict, error_string).
    Policy dict mirrors the structure of hospital_policy_template.json.
    """
    global _POLICY_JSON, _POLICY_JSON_ERROR

    if _POLICY_JSON is not None:
        return _POLICY_JSON, None

    path = Path(json_path)
    if not path.exists():
        _POLICY_JSON_ERROR = f"Policy JSON not found at {path}. Using fallback guidelines."
        return None, _POLICY_JSON_ERROR

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        _POLICY_JSON = data.get("hospital_antibiotic_policy", data)
        return _POLICY_JSON, None
    except (json.JSONDecodeError, OSError) as exc:
        _POLICY_JSON_ERROR = f"Error loading policy JSON: {exc}"
        return None, _POLICY_JSON_ERROR


def _diagnosis_matches(diag_lower: str, key: str) -> bool:
    """Check if a diagnosis matches a guideline key using word-boundary matching.
    Avoids false positives like 'uti' matching 'brutish'."""
    if diag_lower == key:
        return True
    if re.search(r'(?<!\w)' + re.escape(key) + r'(?!\w)', diag_lower):
        return True
    if re.search(r'(?<!\w)' + re.escape(diag_lower) + r'(?!\w)', key):
        return True
    return False


def _find_policy_for_diagnosis(
    policy: dict[str, Any],
    diagnosis: str,
) -> dict[str, Any] | None:
    """Find the policy section matching a diagnosis."""
    diag_lower = diagnosis.lower().strip()
    sections = policy.get("policy_sections", [])
    for section in sections:
        variants = [v.lower() for v in section.get("variants", [])]
        if any(_diagnosis_matches(diag_lower, v) for v in variants):
            return section
    return None


def _find_drug_in_section(
    section: dict[str, Any],
    drug_name: str,
) -> tuple[str, dict[str, Any]] | None:
    """Find a drug within a policy section's recommendations.
    Returns (category, drug_info) tuple or None."""
    drug_lower = drug_name.lower().strip()
    recs = section.get("antibiotic_recommendations", {})
    for category in ("first_line", "alternatives", "severe_hospitalized", "avoid"):
        drugs = recs.get(category, [])
        for entry in drugs:
            if isinstance(entry, dict) and entry.get("drug", "").lower().strip() == drug_lower:
                return category, entry
            if isinstance(entry, str) and entry.lower().strip() == drug_lower:
                return category, {"drug": entry}
    return None


def _retrieve_policy_guidance(
    diagnosis: str,
    drug_name: str,
    policy_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Retrieve policy guidance for diagnosis-antibiotic pair.
    Uses structured JSON policy first, falls back to hardcoded guidelines.
    """
    guidance = {
        "has_policy": False,
        "guidance": "",
        "confidence": 0.0,
        "source": "fallback",
        "dose_range": None,
        "route": None,
        "evidence_level": None,
    }

    # Try structured JSON policy first
    if policy_json:
        section = _find_policy_for_diagnosis(policy_json, diagnosis)
        if section:
            result = _find_drug_in_section(section, drug_name)
            if result:
                category, drug_info = result
                guidance["has_policy"] = True
                guidance["policy_category"] = category

                dose_range = drug_info.get("dose_range")
                route = drug_info.get("route")
                evidence = drug_info.get("evidence_level")
                notes = drug_info.get("notes", "")
                reason = drug_info.get("reason", "")

                guidance["dose_range"] = dose_range
                guidance["route"] = route
                guidance["evidence_level"] = evidence

                if category == "first_line":
                    guidance["guidance"] = f"{drug_name} is first-line for {diagnosis}"
                    if notes:
                        guidance["guidance"] += f". {notes}"
                    guidance["confidence"] = 0.90
                elif category == "alternatives":
                    guidance["guidance"] = f"{drug_name} is an alternative for {diagnosis}"
                    if notes:
                        guidance["guidance"] += f". {notes}"
                    guidance["confidence"] = 0.75
                elif category == "severe_hospitalized":
                    guidance["guidance"] = (
                        f"{drug_name} is reserved for severe/hospitalized {diagnosis}"
                    )
                    if notes:
                        guidance["guidance"] += f". {notes}"
                    guidance["confidence"] = 0.70
                elif category == "avoid":
                    guidance["guidance"] = f"{drug_name} should be avoided for {diagnosis}"
                    if reason:
                        guidance["guidance"] += f". Reason: {reason}"
                    guidance["confidence"] = 0.95

                if dose_range:
                    guidance["guidance"] += f" [Recommended dose: {dose_range}]"
                guidance["source"] = "json_policy"
                return guidance

    # Fallback: hardcoded indication guidelines
    diag_lower = (diagnosis or "").lower().strip()
    for key, rules in INDICATION_ANTIBIOTICS.items():
        if _diagnosis_matches(diag_lower, key):
            drug_lower = (drug_name or "").lower().strip()

            if drug_lower in rules.get("first_line", []):
                guidance["guidance"] = f"{drug_name} is first-line for {diagnosis}"
                guidance["has_policy"] = True
                guidance["policy_category"] = "first_line"
                guidance["confidence"] = 0.90
                guidance["source"] = "guidelines"
                return guidance

            if drug_lower in rules.get("alternatives", []):
                guidance["guidance"] = f"{drug_name} is an alternative for {diagnosis}"
                guidance["has_policy"] = True
                guidance["policy_category"] = "alternatives"
                guidance["confidence"] = 0.75
                guidance["source"] = "guidelines"
                return guidance

            if drug_lower in rules.get("broad_spectrum", []):
                guidance["guidance"] = (
                    f"{drug_name} is broad-spectrum and should be reserved for {diagnosis}"
                )
                guidance["has_policy"] = True
                guidance["policy_category"] = "broad_spectrum"
                guidance["confidence"] = 0.70
                guidance["source"] = "guidelines"
                return guidance

            if drug_lower in rules.get("avoid", []):
                guidance["guidance"] = f"{drug_name} should be avoided for {diagnosis}"
                guidance["has_policy"] = True
                guidance["policy_category"] = "avoid"
                guidance["confidence"] = 0.95
                guidance["source"] = "guidelines"
                return guidance

    return guidance


# =========================================================
# 🔹 Dose Checking
# =========================================================


def _parse_dose_mg(dose_str: str) -> float | None:
    """Parse a dose string to a milligram numeric value.
    Handles formats: '500mg', '2g', '160/800 mg', '500-1000 mg'.
    """
    if not dose_str:
        return None
    text = dose_str.lower().replace(" ", "")

    # Range like "500-1000 mg" — take the midpoint
    range_match = re.match(r"(\d+)\s*[-–]\s*(\d+)\s*(mg|mcg|g|ml|iu)", text)
    if range_match:
        low = float(range_match.group(1))
        high = float(range_match.group(2))
        unit = range_match.group(3)
        mid = (low + high) / 2
        if unit == "g":
            return mid * 1000
        if unit == "mcg":
            return mid / 1000
        return mid

    # Single value like "500mg" or "2g"
    match = re.match(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|iu)", text)
    if match:
        val = float(match.group(1))
        unit = match.group(2)
        if unit == "g":
            return val * 1000
        if unit == "mcg":
            return val / 1000
        return val

    # Fraction like "160/800 mg" — take the lower component
    frac_match = re.match(r"(\d+)/(\d+)", text)
    if frac_match:
        return float(frac_match.group(1))

    return None


def _check_dose(
    drug_name: str,
    prescribed_dose: str,
    policy_dose_range: str | None,
) -> list[str]:
    """Check if the prescribed dose is within the recommended policy range.
    Returns a list of dose issue descriptions (empty = no issues)."""
    if not prescribed_dose or not policy_dose_range:
        return []

    parsed_rx = _parse_dose_mg(prescribed_dose)
    if parsed_rx is None:
        return []

    issues: list[str] = []

    # Check range like "500-1000 mg"
    range_match = re.match(
        r"(\d+)\s*[-–]\s*(\d+)\s*(mg|mcg|g|ml|iu)",
        policy_dose_range.lower().replace(" ", ""),
    )
    if range_match:
        low = float(range_match.group(1))
        high = float(range_match.group(2))
        unit = range_match.group(3)
        low_mg = low * 1000 if unit == "g" else low / 1000 if unit == "mcg" else low
        high_mg = high * 1000 if unit == "g" else high / 1000 if unit == "mcg" else high

        if parsed_rx < low_mg:
            issues.append(
                f"Dose {prescribed_dose} is below recommended range {policy_dose_range} for {drug_name}"
            )
        elif parsed_rx > high_mg:
            issues.append(
                f"Dose {prescribed_dose} exceeds recommended range {policy_dose_range} for {drug_name}"
            )
        return issues

    # Single value like "500mg" or "2g"
    single_match = re.match(
        r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|iu)",
        policy_dose_range.lower().replace(" ", ""),
    )
    if single_match:
        expected = float(single_match.group(1))
        unit = single_match.group(2)
        expected_mg = (
            expected * 1000 if unit == "g"
            else expected / 1000 if unit == "mcg"
            else expected
        )
        tolerance = expected_mg * 0.5  # 50% tolerance for approximate matching

        if parsed_rx < expected_mg - tolerance:
            issues.append(
                f"Dose {prescribed_dose} is much lower than recommended {policy_dose_range} for {drug_name}"
            )
        elif parsed_rx > expected_mg + tolerance:
            issues.append(
                f"Dose {prescribed_dose} is much higher than recommended {policy_dose_range} for {drug_name}"
            )
        return issues

    return issues

def reset_cache() -> None:
    """Reset cached policy data (useful for reloading after file changes)."""
    global _POLICY_JSON, _POLICY_JSON_ERROR
    _POLICY_JSON = None
    _POLICY_JSON_ERROR = None


# =========================================================
# 🔹 Spectrum Classification
# =========================================================


def _classify_spectrum(drug_name: str) -> str:
    """Classify antibiotic by spectrum (narrow/moderate/broad)."""
    drug_lower = (drug_name or "").lower().strip()

    if drug_lower in NARROW_SPECTRUM:
        return "narrow"
    if drug_lower in MODERATE_SPECTRUM:
        return "moderate"
    if drug_lower in BROAD_SPECTRUM:
        return "broad"

    # Heuristic: check for keywords
    if "broad" in drug_lower or "carbapenem" in drug_lower:
        return "broad"
    if "cephalosporin" in drug_lower or "fluoroquinolone" in drug_lower:
        return "moderate"

    return "unknown"


# =========================================================
# 🔹 Indication Matching
# =========================================================


def _is_antibiotic_indicated(diagnosis: str, drug_name: str) -> bool | None:
    """Check if antibiotic is indicated for diagnosis (basic heuristic)."""
    diag_lower = (diagnosis or "").lower().strip()
    drug_lower = (drug_name or "").lower().strip()

    for key, rules in INDICATION_ANTIBIOTICS.items():
        if _diagnosis_matches(diag_lower, key):
            # Check all recommendation lists
            all_recommended = (
                rules.get("first_line", [])
                + rules.get("alternatives", [])
                + rules.get("broad_spectrum", [])
            )
            if drug_lower in [d.lower() for d in all_recommended]:
                return True

            # Not in recommendations
            if drug_lower not in rules.get("avoid", []):
                return None  # Unknown
            return False

    return None  # No guideline found for diagnosis


def _detect_antibiotics(drug_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter drug list to antibiotic entries.
    Uses spectrum classification sets + keyword heuristics."""
    all_known: set[str] = set()
    all_known.update(NARROW_SPECTRUM)
    all_known.update(MODERATE_SPECTRUM)
    all_known.update(BROAD_SPECTRUM)

    antibiotics: list[dict[str, Any]] = []

    for drug in drug_list:
        if not isinstance(drug, dict):
            continue

        drug_name = (
            drug.get("generic") or drug.get("name") or drug.get("corrected_name") or ""
        ).lower().strip()

        if not drug_name:
            continue

        # Check spectrum sets first
        if drug_name in all_known:
            antibiotics.append(drug)
            continue

        # Heuristic: check drug class or name patterns
        antibiotic_keywords = [
            "antibiotic", "amoxicillin", "azithromycin", "ciprofloxacin",
            "cephalosporin", "penicillin", "cephalexin", "fluoroquinolone",
            "erythromycin", "tetracycline", "sulfonamide", "mycin", "cillin",
            "cycline", "floxacin", "cef", "mero", "bactrim", "septra",
        ]
        if any(keyword in drug_name for keyword in antibiotic_keywords):
            antibiotics.append(drug)

    return antibiotics


# =========================================================
# 🔹 Ollama Mistral Integration
# =========================================================


def _call_mistral_reasoning(
    prompt: str,
    model: str = DEFAULT_MISTRAL_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    timeout_sec: float = DEFAULT_TIMEOUT,
) -> str:
    """Call Mistral LLM via Ollama for reasoning."""
    url = f"{host}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "temperature": 0.3,
        "top_p": 0.9,
    }

    try:
        req = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", "").strip()
    except (HTTPError, URLError, Exception) as e:
        return f"Error calling Mistral: {str(e)}"


def _build_stewardship_prompt(
    diagnosis: str,
    drug_name: str,
    spectrum: str,
    policy_guidance: str,
    patient_age: int | None = None,
    patient_gender: str | None = None,
) -> str:
    """Build clinical reasoning prompt for Mistral."""
    return f"""
You are an antibiotic stewardship expert. Assess the appropriateness of the prescribed antibiotic.

DIAGNOSIS: {diagnosis}
PRESCRIBED ANTIBIOTIC: {drug_name}
SPECTRUM: {spectrum}
PATIENT AGE: {patient_age if patient_age else "unknown"}
PATIENT GENDER: {patient_gender if patient_gender else "unknown"}

HOSPITAL POLICY GUIDANCE:
{policy_guidance if policy_guidance else "No specific policy found; use clinical judgment."}

TASK:
1. Is this antibiotic appropriate for this diagnosis?
2. Is the spectrum choice justified? (Avoid unnecessary broad-spectrum use)
3. Are there safer or narrower alternatives?
4. Any red flags or concerns?

Respond ONLY as strict JSON with:
{{
  "appropriate": true|false,
  "spectrum_justified": true|false,
  "rationale": "brief explanation",
  "alternatives": ["suggestion1", "suggestion2"] or [],
  "concerns": ["concern1"] or [],
}}
"""


def _parse_mistral_json(response: str) -> dict[str, Any]:
    """Safely parse JSON from Mistral response."""
    try:
        # Extract JSON object from response
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception:
        pass

    # Fallback if parsing fails
    return {
        "appropriate": None,
        "spectrum_justified": None,
        "rationale": response,
        "alternatives": [],
        "concerns": ["Could not parse LLM response"],
    }


def _resolve_model(requested_model: str, host: str) -> str:
    try:
        from urllib.request import Request, urlopen
        import json
        url = host.rstrip("/") + "/api/tags"
        req = Request(url)
        with urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = [m["name"] for m in data.get("models", [])]
        if requested_model in models:
            return requested_model
        req_base = requested_model.split(":")[0]
        for m in models:
            if m == requested_model or m.split(":")[0] == req_base:
                return m
        for m in models:
            if "mistral" in m.lower():
                return m
        if models:
            non_vision = [m for m in models if "vl" not in m.lower()]
            if non_vision:
                return non_vision[0]
            return models[0]
    except Exception:
        pass
    return requested_model


def check_antibiotic_stewardship(
    *,
    drug_list: list[dict[str, Any]],
    diagnosis: str,
    patient_age: int | None = None,
    patient_gender: str | None = None,
    model: str = DEFAULT_MISTRAL_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    timeout_sec: float = DEFAULT_TIMEOUT,
    policy_json_path: str = DEFAULT_POLICY_JSON,
) -> dict[str, Any]:
    """
    Main antibiotic stewardship check.

    Args:
        drug_list: List of prescribed drugs (from module 3).
        diagnosis: Clinical diagnosis.
        patient_age: Patient age (optional).
        patient_gender: Patient gender (optional).
        model: Mistral model tag.
        host: Ollama host.
        timeout_sec: LLM timeout.
        policy_json_path: Path to hospital policy JSON.

    Returns:
        JSON with stewardship assessment:
        {
          "antibiotics_detected": [
            {
              "drug": str,
              "antibiotic_needed": bool,
              "policy_compliant": bool,
              "spectrum_appropriate": bool,
              "dose_issues": [str],
              "llm_reasoning": {...},
              "recommendation": str,
              "needs_review": bool,
              "confidence": float,
            }
          ],
          "summary": {
            "total_drugs": int,
            "antibiotics_found": int,
            "policy_compliant_count": int,
            "requires_review": bool,
          },
          "error": str|null,
        }
    """
    policy_json, policy_error = _load_json_policy(policy_json_path)

    antibiotics = _detect_antibiotics(drug_list)

    if not diagnosis or not diagnosis.strip():
        return {
            "antibiotics_detected": [],
            "summary": {
                "total_drugs": len(drug_list),
                "antibiotics_found": len(antibiotics),
                "policy_compliant_count": 0,
                "requires_review": False,
                "policy_source": "json_policy" if policy_json else "fallback",
                "policy_error": policy_error,
            },
            "error": "Missing or empty diagnosis",
        }

    results: list[dict[str, Any]] = []
    policy_compliant_count = 0

    for drug in antibiotics:
        drug_name = (
            drug.get("generic")
            or drug.get("name")
            or drug.get("corrected_name")
            or ""
        ).strip()

        if not drug_name:
            continue

        structured = drug.get("structured", {}) or {}
        prescribed_dose = structured.get("dose", "") if isinstance(structured, dict) else ""

        antibiotic_needed = _is_antibiotic_indicated(diagnosis, drug_name)
        spectrum = _classify_spectrum(drug_name)
        policy_guidance = _retrieve_policy_guidance(diagnosis, drug_name, policy_json)

        dose_issues = _check_dose(
            drug_name,
            prescribed_dose,
            policy_guidance.get("dose_range"),
        )

        policy_compliant = (
            policy_guidance["has_policy"]
            and policy_guidance["source"] in ("json_policy", "guidelines")
            and antibiotic_needed is not False
        )

        prompt = _build_stewardship_prompt(
            diagnosis,
            drug_name,
            spectrum,
            policy_guidance.get("guidance", ""),
            patient_age,
            patient_gender,
        )
        llm_response = _call_mistral_reasoning(prompt, model, host, timeout_sec)
        llm_reasoning = _parse_mistral_json(llm_response)

        policy_category = policy_guidance.get("policy_category")
        spectrum_appropriate = (
            spectrum != "broad"
            or policy_category in ("first_line", "alternatives")
            or bool(llm_reasoning.get("spectrum_justified"))
        )

        recommendation_parts: list[str] = []

        if antibiotic_needed is False:
            recommendation_parts.append(
                f"Antibiotic may not be needed for {diagnosis}. "
                f"Consider non-antibiotic treatment."
            )
        elif antibiotic_needed is None:
            recommendation_parts.append(
                f"Uncertain whether antibiotic is needed for {diagnosis}. "
                f"Clinical review advised."
            )
        elif not spectrum_appropriate and spectrum == "broad":
            recommendation_parts.append(
                f"Broad-spectrum {drug_name} may not be justified. "
                f"Consider narrower alternatives: "
                f"{', '.join(llm_reasoning.get('alternatives', []))}"
            )
        elif policy_compliant:
            recommendation_parts.append(
                f"{drug_name} is compliant with hospital policy for {diagnosis}."
            )
        else:
            recommendation_parts.append(
                policy_guidance.get("guidance", "No policy guidance available.")
            )

        if dose_issues:
            recommendation_parts.append("Dose issue: " + "; ".join(dose_issues))

        recommendation = (
            " | ".join(recommendation_parts) if recommendation_parts else "No issues detected."
        )

        needs_review = (
            antibiotic_needed is False
            or not policy_compliant
            or not spectrum_appropriate
            or len(dose_issues) > 0
            or (llm_reasoning.get("concerns") and len(llm_reasoning["concerns"]) > 0)
        )

        if policy_compliant:
            policy_compliant_count += 1

        results.append(
            {
                "drug": drug_name,
                "antibiotic_needed": antibiotic_needed,
                "policy_compliant": policy_compliant,
                "spectrum_appropriate": spectrum_appropriate,
                "spectrum_type": spectrum,
                "policy_source": policy_guidance.get("source", "unknown"),
                "dose_issues": dose_issues,
                "prescribed_dose": prescribed_dose or None,
                "recommended_dose": policy_guidance.get("dose_range"),
                "llm_reasoning": llm_reasoning,
                "recommendation": recommendation,
                "needs_review": needs_review,
                "confidence": policy_guidance.get("confidence", 0.5),
            }
        )

    requires_review = any(r.get("needs_review", False) for r in results)
    total_dose_issues = sum(len(r.get("dose_issues", [])) for r in results)

    return {
        "antibiotics_detected": results,
        "summary": {
            "total_drugs": len(drug_list),
            "antibiotics_found": len(antibiotics),
            "antibiotics_evaluated": len(results),
            "policy_compliant_count": policy_compliant_count,
            "requires_review": requires_review,
            "total_dose_issues": total_dose_issues,
            "policy_source": "json_policy" if policy_json else "fallback",
            "policy_error": policy_error,
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
) -> dict[str, Any]:
    """
    Convenience wrapper to use module 3 & 4 outputs directly.

    Expects:
    - module3_normalized_drugs: Output from drug normalization (module 3)
    - module4_validation: Diagnosis validation output (module 4)
    """
    diagnosis = (
        module4_validation.get("diagnosis")
        or module4_validation.get("input_diagnosis")
        or ""
    ).strip()

    patient = module4_validation.get("patient", {})
    age = patient.get("age") if isinstance(patient, dict) else None
    gender = patient.get("gender") if isinstance(patient, dict) else None

    drugs = module3_normalized_drugs.get("drugs", [])

    return check_antibiotic_stewardship(
        drug_list=drugs,
        diagnosis=diagnosis,
        patient_age=age,
        patient_gender=gender,
    )


# =========================================================
# 🔹 CLI
# =========================================================


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Module 6: Antibiotic Stewardship Checker")
    parser.add_argument("--drugs-json", required=True, help="JSON string of normalized drugs")
    parser.add_argument("--diagnosis", required=True, help="Patient diagnosis")
    parser.add_argument("--age", type=int, help="Patient age")
    parser.add_argument("--gender", help="Patient gender (M/F)")
    args = parser.parse_args()

    try:
        drugs = json.loads(args.drugs_json)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"Invalid drugs JSON: {exc}"}, indent=2))
        return 1

    result = check_antibiotic_stewardship(
        drug_list=drugs.get("drugs", []) if isinstance(drugs, dict) else drugs,
        diagnosis=args.diagnosis,
        patient_age=args.age,
        patient_gender=args.gender,
    )

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
