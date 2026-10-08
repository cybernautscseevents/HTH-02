"""Generate a professional medical PDF audit report from the orchestrator JSON output.

Function: generate_audit_report(audit_json, output_path)

This module uses reportlab to build a clean PDF. It handles missing modules/data gracefully.
"""
from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        PageBreak,
    )
except Exception:  # pragma: no cover - allow file to be imported without reportlab
    # We'll let the generate function raise a helpful error when called
    SimpleDocTemplate = None  # type: ignore


def _safe_get(d: Dict[str, Any], *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
    return cur


def _extract_patient_info(audit_json: Dict[str, Any]) -> Dict[str, str]:
    ner = audit_json.get("ner") or {}
    patient = ner.get("patient") or ner.get("patient_info") or {}
    if isinstance(patient, dict):
        name = patient.get("name") or patient.get("full_name") or "Unknown"
        age = patient.get("age") or patient.get("patient_age") or ""
        gender = patient.get("gender") or patient.get("sex") or ""
    else:
        # fallback: try top-level fields
        name = audit_json.get("patient_name") or "Unknown"
        age = audit_json.get("patient_age") or ""
        gender = audit_json.get("patient_gender") or ""
    return {"name": str(name), "age": str(age), "gender": str(gender)}


def _extract_generic_name(drug: Dict[str, Any]) -> str:
    """Return the best available generic name from a normalized drug record."""
    for key in ("generic_name", "generic", "mapped_generic", "brand_name", "corrected_name", "original", "name"):
        value = drug.get(key)
        if value:
            return str(value)
    return ""


def _compute_flags_for_drugs(audit_json: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Return mapping drug_name -> flag info and collected messages.

    The mapping contains: {'flag': 'CRITICAL'|'WARNING'|'SAFE', 'reasons': [str,...]}
    """
    flags: Dict[str, Dict[str, Any]] = {}

    # initialize from normalized drugs
    normalized = audit_json.get("normalized_drugs") or {}
    drugs = normalized.get("drugs") or []
    for d in drugs:
        if isinstance(d, dict):
            name = _extract_generic_name(d)
        else:
            name = str(d)
        name = str(name).lower()
        flags[name] = {"flag": "SAFE", "reasons": [], "meta": d}

    # Module 8 interactions
    ddi = audit_json.get("ddi") or {}
    interactions = ddi.get("interactions") or []
    for it in interactions:
        a = (it.get("drug_a") or "").lower()
        b = (it.get("drug_b") or "").lower()
        sev = (it.get("severity") or "").lower()
        desc = it.get("description") or it.get("mechanism") or "Interaction detected"
        src = it.get("source")
        msg = f"DDI ({src}): {desc} [severity={sev}]"
        for name in (a, b):
            if not name:
                continue
            if name not in flags:
                flags[name] = {"flag": "SAFE", "reasons": [], "meta": {}}
            if sev in ("major", "high", "severe"):
                flags[name]["flag"] = "CRITICAL"
            elif sev in ("moderate",):
                if flags[name]["flag"] != "CRITICAL":
                    flags[name]["flag"] = "WARNING"
            flags[name]["reasons"].append(msg)

    # Module 7 dose adjustments
    dose = audit_json.get("dose_adjustment") or {}
    assessments = dose.get("assessments") or []
    for a in assessments:
        dname = (a.get("drug") or "").lower()
        adj_needed = a.get("adjustment_needed")
        severity = (a.get("severity") or "").lower()
        reason = a.get("reason") or a.get("note") or "Dose adjustment recommended"
        msg = f"Dose Adjustment: {reason} [severity={severity}]"
        if not dname:
            continue
        if dname not in flags:
            flags[dname] = {"flag": "SAFE", "reasons": [], "meta": {}}
        if adj_needed:
            if severity in ("high", "severe"): 
                flags[dname]["flag"] = "CRITICAL"
            else:
                if flags[dname]["flag"] != "CRITICAL":
                    flags[dname]["flag"] = "WARNING"
            flags[dname]["reasons"].append(msg)

    # Module 9 pregnancy safety
    preg = audit_json.get("pregnancy_safety") or {}
    safes = preg.get("safety_assessment") or []
    for s in safes:
        dname = (s.get("drug") or "").lower()
        risk = (s.get("risk") or s.get("classification") or "").lower()
        note = s.get("note") or s.get("explanation") or "Pregnancy/lactation safety concern"
        msg = f"Pregnancy Safety: {note} [risk={risk}]"
        if not dname:
            continue
        if dname not in flags:
            flags[dname] = {"flag": "SAFE", "reasons": [], "meta": {}}
        if risk in ("contraindicated", "major", "high"):
            flags[dname]["flag"] = "CRITICAL"
        else:
            if flags[dname]["flag"] != "CRITICAL":
                flags[dname]["flag"] = "WARNING"
        flags[dname]["reasons"].append(msg)

    # Module 6 antibiotic stewardship
    abx = audit_json.get("antibiotic_stewardship") or {}
    abx_detected = abx.get("antibiotics_detected") or []
    for entry in abx_detected:
        if isinstance(entry, dict):
            dname = (entry.get("drug") or entry.get("name") or "").lower()
        else:
            dname = str(entry).lower()
        if not dname:
            continue
        if dname not in flags:
            flags[dname] = {"flag": "SAFE", "reasons": [], "meta": {}}

        # Check dose issues
        dose_issues = entry.get("dose_issues") or []
        if dose_issues:
            if flags[dname]["flag"] != "CRITICAL":
                flags[dname]["flag"] = "WARNING"
            for issue in dose_issues:
                flags[dname]["reasons"].append(f"Dose issue: {issue}")

        # Check spectrum appropriateness
        spectrum_appropriate = entry.get("spectrum_appropriate")
        if spectrum_appropriate is False:
            spectrum_type = entry.get("spectrum_type", "unknown")
            if flags[dname]["flag"] != "CRITICAL":
                flags[dname]["flag"] = "WARNING"
            flags[dname]["reasons"].append(
                f"Broad-spectrum ({spectrum_type}) may not be justified — consider narrower alternative"
            )

        # Check needs_review flag
        if entry.get("needs_review") and not any(
            r.startswith("Dose issue") or r.startswith("Antibiotic interaction")
            for r in flags[dname]["reasons"]
        ):
            if flags[dname]["flag"] != "CRITICAL":
                flags[dname]["flag"] = "WARNING"
            flags[dname]["reasons"].append("Antibiotic stewardship flagged for review")

    # Module 5 appropriateness warnings
    app = audit_json.get("drug_appropriateness") or {}
    app_eval = app.get("drug_evaluation") or []
    for e in app_eval:
        dname = (e.get("drug") or e.get("name") or "").lower()
        warning = e.get("warning") or e.get("note")
        if not dname:
            continue
        if dname not in flags:
            flags[dname] = {"flag": "SAFE", "reasons": [], "meta": {}}
        if warning:
            if flags[dname]["flag"] != "CRITICAL":
                flags[dname]["flag"] = "WARNING"
            flags[dname]["reasons"].append(f"Appropriateness: {warning}")

    return flags


def _flag_label(flag: str) -> str:
    if flag == "CRITICAL":
        return "❌ CRITICAL"
    if flag == "WARNING":
        return "⚠️ WARNING"
    return "✅ SAFE"


def generate_audit_report(audit_json: Dict[str, Any], output_path: str) -> None:
    """Generate a multi-section PDF audit report from `audit_json` and write to `output_path`.

    Raises RuntimeError if reportlab is not installed.
    """
    if SimpleDocTemplate is None:
        raise RuntimeError("reportlab is required to generate PDF. Install with: pip install reportlab")

    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    heading = ParagraphStyle("Heading", parent=styles["Heading2"], spaceAfter=6)

    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
    story: List[Any] = []

    # Header
    hospital = "KSHEMA Prescription Audit System"
    date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    patient = _extract_patient_info(audit_json)

    story.append(Paragraph(f"<b>{hospital}</b>", styles["Title"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Date: {date_str}", normal))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Patient: <b>{patient.get('name','Unknown')}</b> — Age: <b>{patient.get('age','')}</b> — Gender: <b>{patient.get('gender','')}</b>", normal))
    story.append(Spacer(1, 12))

    # Clinical Summary (Module 4)
    story.append(Paragraph("<b>Clinical Summary</b>", heading))
    diag_val = audit_json.get("diagnosis_validation") or {}
    diag_text = diag_val.get("validated_diagnosis") or diag_val.get("diagnosis") or diag_val.get("summary") or "No validated diagnosis available."
    plaus = (
        diag_val.get("plausibility_score")
        or diag_val.get("plausibility")
        or diag_val.get("confidence")
        or diag_val.get("confidence_score")
        or "N/A"
    )
    story.append(Paragraph(f"Validated diagnosis: <b>{diag_text}</b>", normal))
    story.append(Paragraph(f"Plausibility / confidence: <b>{plaus}</b>", normal))
    story.append(Spacer(1, 12))

    app = audit_json.get("drug_appropriateness") or {}
    app_eval = app.get("drug_evaluation") or []
    story.append(Paragraph("<b>Appropriateness Review</b>", heading))
    if app_eval:
        story.append(Paragraph(f"Drugs evaluated: <b>{len(app_eval)}</b>", normal))
    else:
        story.append(Paragraph("No appropriateness findings were returned by Module 5.", normal))
    story.append(Spacer(1, 8))

    preg_summary = audit_json.get("pregnancy_safety") or {}
    story.append(Paragraph("<b>Pregnancy / Lactation Review</b>", heading))
    if preg_summary.get("warning"):
        story.append(Paragraph(f"Status: <b>{preg_summary.get('warning')}</b>", normal))
    elif preg_summary.get("safety_assessment"):
        story.append(Paragraph(f"Drugs evaluated: <b>{len(preg_summary.get('safety_assessment') or [])}</b>", normal))
    else:
        story.append(Paragraph("No pregnancy/lactation assessment returned.", normal))
    story.append(Spacer(1, 12))

    # Drug Breakdown Table
    story.append(Paragraph("<b>Drug Breakdown</b>", heading))
    normalized = audit_json.get("normalized_drugs") or {}
    drugs = normalized.get("drugs") or []

    flags = _compute_flags_for_drugs(audit_json)

    table_data = [["Drug", "Generic", "Dose/Route", "Risk"]]
    for d in drugs:
        if isinstance(d, dict):
            name = d.get("name") or d.get("original") or ""
            generic = _extract_generic_name(d)
            dose = d.get("dose") or d.get("sig") or d.get("strength") or ""
        else:
            name = str(d)
            generic = ""
            dose = ""
        key = str((generic or name)).lower()
        flag_info = flags.get(key) or flags.get(name.lower()) or {"flag": "SAFE"}
        flag_label = _flag_label(flag_info.get("flag", "SAFE"))
        table_data.append([str(name), str(generic), str(dose), flag_label])

    t = Table(table_data, colWidths=[120 * mm * 0.35, 120 * mm * 0.25, 120 * mm * 0.2, 120 * mm * 0.2])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 12))

    # Detailed Findings
    story.append(Paragraph("<b>Detailed Findings</b>", heading))
    if not flags:
        story.append(Paragraph("No drugs found or no detailed findings available.", normal))
    else:
        for drug_key, info in sorted(flags.items()):
            display_name = (info.get("meta") or {}).get("name") or drug_key
            story.append(Paragraph(f"<b>{display_name}</b> — {_flag_label(info.get('flag','SAFE'))}", normal))
            reasons = info.get("reasons") or []
            if reasons:
                for r in reasons:
                    story.append(Paragraph(f"- {r}", normal))
            else:
                story.append(Paragraph("- No specific warnings recorded.", normal))
            story.append(Spacer(1, 6))

    story.append(Spacer(1, 18))

    # Footer / signature line
    story.append(Spacer(1, 24))
    story.append(Paragraph("Reviewed by:", normal))
    story.append(Spacer(1, 18))
    story.append(Paragraph("______________________________", normal))
    story.append(Paragraph("Pharmacist signature", ParagraphStyle("sig", parent=normal, alignment=1)))

    # Build PDF
    doc.build(story)


if __name__ == "__main__":
    # Test block with a mock audit JSON to verify PDF creation
    out_pdf = os.path.join("backend", "test_audit_report.pdf")
    mock = {
        "ner": {"patient": {"name": "Jane Doe", "age": 42, "gender": "F"}},
        "diagnosis_validation": {"validated_diagnosis": "Acute bronchitis", "plausibility_score": 0.85},
        "normalized_drugs": {
            "drugs": [
                {"name": "Amoxicillin", "generic": "amoxicillin", "dose": "500 mg TID"},
                {"name": "Metformin", "generic": "metformin", "dose": "500 mg BID"},
                {"name": "Warfarin", "generic": "warfarin", "dose": "5 mg nightly"},
            ]
        },
        "ddi": {
            "interactions": [
                {"drug_a": "amoxicillin", "drug_b": "warfarin", "severity": "major", "description": "Increased INR and bleeding risk", "source": "drugbank"},
            ]
        },
        "dose_adjustment": {"assessments": [{"drug": "metformin", "adjustment_needed": True, "reason": "eGFR 25 mL/min", "recommended_dose": "Reduce dose to 500 mg daily", "original_dose": "500 mg BID", "severity": "high"}]},
        "pregnancy_safety": {"safety_assessment": [{"drug": "warfarin", "risk": "contraindicated", "note": "Teratogenic - avoid in pregnancy"}]},
        "antibiotic_stewardship": {"antibiotics_detected": [{"drug": "amoxicillin", "policy_mismatch": True, "note": "Local guideline recommends doxycycline"}]},
        "drug_appropriateness": {"drug_evaluation": [{"drug": "metformin", "warning": "Renal impairment caution"}]}
    }

    try:
        generate_audit_report(mock, out_pdf)
        print(f"Test report written to: {out_pdf}")
    except Exception as e:
        print(f"Failed to generate report: {e}")
