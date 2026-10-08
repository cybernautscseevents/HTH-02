"""Dose adjustment checker (Module 7)

Rule-based logic using offline FDA label JSON data.

Main entry: check_dose_adjustment(drug_list, comorbidities)

Expectations:
- `drug_list`: list of dicts from module 2 normalization, e.g. [{"generic": "amoxicillin", "original_dose": "500 mg"}, ...]
- `comorbidities`: dict with keys like "ckd" (with eGFR or crcl), "liver_disease" (bool), "age", etc.

Output per drug:
{
  "drug": str,
  "adjustment_needed": bool,
  "reason": str|null,
  "recommended_dose": str|null,
  "original_dose": str|null,
  "severity": "low|moderate|high|unknown"
}
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

DEFAULT_DB_PATH = os.environ.get(
    "FDA_LABEL_DATABASE",
    os.path.join(Path.cwd(), "data", "fda_label_database.json"),
)


def _load_database(path: Optional[str] = None) -> Dict[str, Any]:
    p = path or DEFAULT_DB_PATH
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Expecting schema: {"drugs": {"generic_name": { ... }}}
            return data.get("drugs", {}) if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


_FDA_LABELS = _load_database()


def _normalize_name(name: str) -> str:
    return (name or "").strip().lower()


def get_drug_label_info(drug_name: str) -> Optional[Dict[str, Any]]:
    """Return label entry for a drug by exact or partial match.

    Simple matching: exact generic name (case-insensitive) first, then substring match.
    """
    if not drug_name:
        return None
    q = _normalize_name(drug_name)
    # Exact match
    if q in _FDA_LABELS:
        return _FDA_LABELS[q]
    # Try to match by key that contains q
    for k, v in _FDA_LABELS.items():
        if q == k or q in k:
            return v
    # Try looking into "aliases"
    for k, v in _FDA_LABELS.items():
        aliases = v.get("aliases", []) or []
        for a in aliases:
            if q == _normalize_name(a) or q in _normalize_name(a):
                return v
    return None


def _evaluate_ckd_rule(drug_label: Dict[str, Any], comorbidities: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Check CKD/renal impairment rules from label.

    Expects `drug_label` to contain key `dose_adjustments` which is a list of dicts:
      {"condition": "ckd", "criteria": "eGFR<30", "recommended_dose": "avoid or reduce", "severity": "high"}
    """
    if not drug_label:
        return None
    adjustments = drug_label.get("dose_adjustments", []) or []
    for adj in adjustments:
        cond = (adj.get("condition") or "").lower()
        if "ckd" in cond or "renal" in cond:
            # If patient has CKD information
            ckd = comorbidities.get("ckd")
            # Allow ckd to be bool or dict with {'egfr': value, 'crcl': value}
            if isinstance(ckd, dict):
                egfr = ckd.get("egfr")
                crcl = ckd.get("crcl")
                threshold = adj.get("criteria", "")
                # simple parsing for numeric threshold like 'egfr<30' or 'crcl<50'
                try:
                    if "egfr<" in threshold and egfr is not None:
                        if float(egfr) < float(threshold.split("<")[1]):
                            return adj
                    if "crcl<" in threshold and crcl is not None:
                        if float(crcl) < float(threshold.split("<")[1]):
                            return adj
                except Exception:
                    # If parsing fails, default to returning the rule so clinician reviews
                    return adj
            elif ckd:  # boolean flag
                return adj
    return None


def _evaluate_liver_rule(drug_label: Dict[str, Any], comorbidities: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not drug_label:
        return None
    adjustments = drug_label.get("dose_adjustments", []) or []
    for adj in adjustments:
        cond = (adj.get("condition") or "").lower()
        if "liver" in cond or "hepatic" in cond:
            if comorbidities.get("liver_disease"):
                return adj
    return None


def _evaluate_other_rules(drug_label: Dict[str, Any], comorbidities: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not drug_label:
        return None
    adjustments = drug_label.get("dose_adjustments", []) or []
    for adj in adjustments:
        cond = (adj.get("condition") or "").lower()
        # Age-based
        if "age>=" in cond or "age>" in cond:
            age = comorbidities.get("age")
            try:
                if age is not None:
                    thresh = int(cond.split(">=")[1]) if ">=" in cond else int(cond.split(">")[1])
                    if (">=" in cond and age >= thresh) or (">" in cond and age > thresh):
                        return adj
            except Exception:
                return adj
        # Other named conditions
        for key in comorbidities.keys():
            if key and key.lower() in cond and comorbidities.get(key):
                return adj
    return None


def check_dose_adjustment(drug_list: List[Dict[str, Any]], comorbidities: Dict[str, Any]) -> Dict[str, Any]:
    """Main entry point.

    Returns:
      {"assessments": [ ... ], "summary": {...}}
    """
    assessments = []
    for drug in drug_list or []:
        name = drug.get("generic") or drug.get("corrected_name") or drug.get("name")
        original_dose = drug.get("original_dose") or drug.get("dose")
        label = get_drug_label_info(name)
        entry = {
            "drug": name,
            "adjustment_needed": False,
            "reason": None,
            "recommended_dose": None,
            "original_dose": original_dose,
            "severity": "unknown",
        }

        if label is None:
            entry.update({
                "adjustment_needed": False,
                "reason": "Drug label not found in local FDA DB",
                "severity": "unknown",
            })
            assessments.append(entry)
            continue

        # Evaluate CKD rules first
        rule = _evaluate_ckd_rule(label, comorbidities)
        if rule:
            entry.update({
                "adjustment_needed": True,
                "reason": rule.get("notes") or rule.get("criteria") or rule.get("condition"),
                "recommended_dose": rule.get("recommended_dose"),
                "severity": rule.get("severity") or "high",
            })
            assessments.append(entry)
            continue

        # Evaluate hepatic rules
        rule = _evaluate_liver_rule(label, comorbidities)
        if rule:
            entry.update({
                "adjustment_needed": True,
                "reason": rule.get("notes") or rule.get("criteria") or rule.get("condition"),
                "recommended_dose": rule.get("recommended_dose"),
                "severity": rule.get("severity") or "moderate",
            })
            assessments.append(entry)
            continue

        # Other rules (age, pregnancy, etc.)
        rule = _evaluate_other_rules(label, comorbidities)
        if rule:
            entry.update({
                "adjustment_needed": True,
                "reason": rule.get("notes") or rule.get("criteria") or rule.get("condition"),
                "recommended_dose": rule.get("recommended_dose"),
                "severity": rule.get("severity") or "low",
            })
            assessments.append(entry)
            continue

        # No adjustment found
        entry.update({
            "adjustment_needed": False,
            "reason": "No dose adjustment required per local FDA label DB",
            "severity": "low",
        })
        assessments.append(entry)

    # Summary
    total = len(assessments)
    needs = sum(1 for a in assessments if a.get("adjustment_needed"))
    summary = {
        "total_drugs": total,
        "adjustments_needed": needs,
        "requires_review": needs > 0,
    }
    return {"assessments": assessments, "summary": summary}


def check_from_module_outputs(module2_normalized_drugs: Dict[str, Any], module3_comorbidities: Dict[str, Any]) -> Dict[str, Any]:
    """Wrapper to accept outputs from upstream modules.

    - `module2_normalized_drugs` expected to be {'drugs': [ ... ]}
    - `module3_comorbidities` expected to be a dict of comorbidities
    """
    drugs = module2_normalized_drugs.get("drugs") if isinstance(module2_normalized_drugs, dict) else module2_normalized_drugs
    return check_dose_adjustment(drugs or [], module3_comorbidities or {})


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run dose adjustment checks (Module 7)")
    parser.add_argument("--db", help="Path to FDA label database JSON", default=None)
    parser.add_argument("--drugs-json", help="JSON array of drugs", default=None)
    parser.add_argument("--comorbidities-json", help="JSON object of comorbidities", default=None)
    args = parser.parse_args()

    if args.db:
        # reload DB
        _FDA_LABELS = _load_database(args.db)

    drugs = []
    comorbidities = {}
    if args.drugs_json:
        drugs = json.loads(args.drugs_json)
    if args.comorbidities_json:
        comorbidities = json.loads(args.comorbidities_json)

    result = check_dose_adjustment(drugs, comorbidities)
    print(json.dumps(result, indent=2))
