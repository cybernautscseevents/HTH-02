"""Typed prescriptions from the open PhysioNet demo databases -> the existing stewardship pipeline.

Each antibiotic order row becomes one typed line built only from the row's own text fields,
joined with spaces and not rewritten (MIMIC: drug, dose, unit, route, frequency; eICU: drugname,
dosage, routeadmin, frequency). The lines then go through the same path as the API:

    EpisodeRequest -> intake (parse_prescription_lines, Catalog.normalize) -> Episode
    -> evaluate_episode (R0-R6, culture rules) -> findings, actions, guideline evidence

Nothing here identifies a drug, reads a dose or decides anything clinical.

Data (not included, Open Data Commons ODbL v1.0, de-identified, no credentialing needed):
  MIMIC-IV Clinical Database Demo 2.2   https://physionet.org/content/mimic-iv-demo/2.2/
  eICU Collaborative Research DB Demo   https://physionet.org/content/eicu-crd-demo/2.0.1/

Usage:
  python scripts/typed_rx_eval.py --mimic DIR [--eicu DIR] [--cases 12] [--out report.md]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import UTC, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.stewardship.audit import JsonlAuditLog  # noqa: E402
from backend.stewardship.drugs import Catalog  # noqa: E402
from backend.stewardship.evidence import build_store  # noqa: E402
from backend.stewardship.intake import EpisodeRequest  # noqa: E402
from backend.stewardship.renal import RenalDosing  # noqa: E402
from backend.stewardship.rulepack import YamlRulePack  # noqa: E402
from backend.stewardship.schemas import NormStatus, Route  # noqa: E402
from backend.stewardship.service import StewardshipService  # noqa: E402
from prescription_ocr.orders import build_order  # noqa: E402
from prescription_ocr.transcript import parse_prescription_lines  # noqa: E402

# Row selection only (which rows to try); identity always comes from Catalog.normalize.
ANTIBIOTIC = re.compile(
    r"cillin|cef|ceph|penem|mycin|floxacin|cycline|sulfameth|metronidazole|flagyl|linezolid|"
    r"vancomycin|nitrofurantoin|fosfomycin|tazobactam|zosyn|unasyn|ancef|rocephin|levaquin|"
    r"clindamycin|aztreonam|colistin|polymyxin|tigecycline",
    re.I,
)
INFECTION = re.compile(
    r"urinary tract infection|cystitis|pyelonephritis|pneumonia|cellulitis|acute bronchitis|"
    r"obstructive chronic bronchitis with \(acute\) exacerbation|"
    r"chronic obstructive pulmonary disease with \(acute\) exacerbation|gastroenteritis",
    re.I,
)
# Simulated clinician choice for run B: the ICD title alone does not name an NCDC syndrome.
SIMULATED_CODE = [
    (re.compile(r"pyelonephritis", re.I), "pyelonephritis"),
    (re.compile(r"urinary tract infection|cystitis", re.I), "cystitis"),
    (re.compile(r"chronic .*exacerbation", re.I), "copd_exacerbation"),
    (re.compile(r"acute bronchitis", re.I), "acute_bronchitis"),
    (re.compile(r"cellulitis", re.I), "cellulitis_moderate_severe"),
    (re.compile(r"^(?!.*ventilator)(?!.*aspergill).*pneumonia", re.I), "cap_ward"),
]
CREATININE_ITEMID = 50912
CULTURE_SPECIMENS = re.compile(r"^(blood culture|urine|sputum|swab|tissue|bronchoalveolar)", re.I)
SIR_VALUES = {"S", "I", "R"}


def _text(*values) -> str:
    return " ".join(str(v).strip() for v in values if pd.notna(v) and str(v).strip())


def _num(value) -> str | None:
    if pd.isna(value):
        return None
    return str(value).strip()


# --- Typed lines ------------------------------------------------------------------------


def mimic_lines(mimic: Path) -> pd.DataFrame:
    rx = pd.read_csv(mimic / "prescriptions.csv.gz", low_memory=False)
    ph = pd.read_csv(mimic / "pharmacy.csv.gz", usecols=["pharmacy_id", "frequency"])
    rx = rx[rx.drug.str.contains(ANTIBIOTIC, na=False)].merge(ph, on="pharmacy_id", how="left")
    rx["line"] = [
        _text(r.drug, _num(r.dose_val_rx), r.dose_unit_rx, r.route, r.frequency)
        for r in rx.itertuples()
    ]
    return rx


def eicu_lines(eicu: Path) -> pd.DataFrame:
    med = pd.read_csv(eicu / "medication.csv.gz", low_memory=False)
    med = med[med.drugname.str.contains(ANTIBIOTIC, na=False)]
    med["line"] = [_text(r.drugname, r.dosage, r.routeadmin, r.frequency) for r in med.itertuples()]
    return med


# --- Parser coverage, scored against the dataset's own structured fields --------------------

_ROUTE_TRUTH = {"IV": Route.IV, "PO": Route.PO, "PO/NG": Route.PO, "IM": Route.IM}


def _truth_dose(row) -> float | None:
    try:
        value = float(row.dose_val_rx)
    except (TypeError, ValueError):
        return None
    unit = str(row.dose_unit_rx).strip().lower()
    return value if unit == "mg" else value * 1000 if unit == "g" else None


def read_line(line: str, catalog: Catalog, started_at):
    """One typed line through the existing parser and catalog: (order, reason) or an error."""
    parsed = parse_prescription_lines(line)
    if not parsed:
        return None, "parser found no medicine line"
    try:
        reading = build_order(parsed[0], catalog, order_id="rx-1", started_at=started_at)
    except Exception as exc:  # noqa: BLE001 - reported, not hidden
        return None, f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
    return reading.order, reading.reason


def coverage(df: pd.DataFrame, catalog: Catalog, *, truth: bool) -> dict:
    started_at = pd.Timestamp("2100-01-01", tz=UTC).to_pydatetime()
    lines = df.drop_duplicates("line")
    stats = Counter()
    errors = Counter()
    unidentified = Counter()
    for row in lines.itertuples():
        order, reason = read_line(row.line, catalog, started_at)
        stats["lines"] += 1
        if order is None:
            errors[reason] += 1
            continue
        stats["orders"] += 1
        stats[f"status_{order.norm_status.value}"] += 1
        if order.norm_status is not NormStatus.ACCEPTED:
            unidentified[row.line.split(" ")[0]] += 1
        for field in ("dose_mg", "freq_per_day", "route", "duration_days"):
            stats[f"has_{field}"] += getattr(order, field) is not None
        if truth:
            want = {
                "dose_mg": _truth_dose(row),
                "freq_per_day": row.doses_per_24_hrs if pd.notna(row.doses_per_24_hrs) else None,
                "route": _ROUTE_TRUTH.get(str(row.route).strip()),
            }
            for field, expected in want.items():
                if expected is None or expected == 0:
                    continue
                got = getattr(order, field)
                stats[f"truth_{field}"] += 1
                if got is None:
                    stats[f"missed_{field}"] += 1
                elif got == expected:
                    stats[f"right_{field}"] += 1
                else:
                    stats[f"wrong_{field}"] += 1
    return {"stats": stats, "errors": errors, "unidentified": unidentified}


# --- End to end: MIMIC admissions -> EpisodeRequest -> StewardshipService ------------------


def _cultures(micro: pd.DataFrame, catalog: Catalog, start, skipped: Counter) -> list[dict]:
    window = micro[
        (micro.when >= start - timedelta(hours=48)) & (micro.when <= start + timedelta(hours=48))
    ]
    window = window[window.spec_type_desc.str.match(CULTURE_SPECIMENS, na=False)]
    cultures = []
    for _, spec in window.groupby("micro_specimen_id"):
        first = spec.iloc[0]
        organisms = spec[spec.org_name.notna()]
        isolates = []
        for organism, rows in organisms.groupby("org_name"):
            panel = {}
            for r in rows[rows.ab_name.notna()].itertuples():
                if r.interpretation not in SIR_VALUES:
                    continue
                if catalog.normalize(r.ab_name).status not in (
                    NormStatus.ACCEPTED,
                    NormStatus.CONFIRMED,
                ):
                    skipped[r.ab_name] += 1
                    continue
                panel[r.ab_name] = r.interpretation
            isolates.append({"organism": organism, "susceptibilities": panel})
        if not isolates:
            status = "NO_GROWTH"
        elif any(i["susceptibilities"] for i in isolates):
            status = "FINAL"
        else:
            status = "GROWTH_NO_AST"
        cultures.append(
            {
                "specimen_type": first.spec_type_desc,
                "status": status,
                "collected_at": first.when.isoformat(),
                "isolates": isolates,
            }
        )
    return cultures


def mimic_cases(mimic: Path, catalog: Catalog, n: int):
    rx = mimic_lines(mimic)
    rx["start"] = pd.to_datetime(rx.starttime).dt.tz_localize(UTC)
    dx = pd.read_csv(mimic / "diagnoses_icd.csv.gz").merge(
        pd.read_csv(mimic / "d_icd_diagnoses.csv.gz"), on=["icd_code", "icd_version"]
    )
    dx = dx[dx.long_title.str.contains(INFECTION, na=False)]
    patients = pd.read_csv(mimic / "patients.csv.gz").set_index("subject_id")
    labs = pd.read_csv(
        mimic / "labevents.csv.gz", usecols=["hadm_id", "itemid", "charttime", "valuenum"]
    )
    labs = labs[(labs.itemid == CREATININE_ITEMID) & labs.valuenum.gt(0)]
    labs["when"] = pd.to_datetime(labs.charttime).dt.tz_localize(UTC)
    micro = pd.read_csv(mimic / "microbiologyevents.csv.gz")
    micro["when"] = pd.to_datetime(micro.charttime.fillna(micro.chartdate)).dt.tz_localize(UTC)

    hadms = sorted(set(rx.hadm_id.dropna()) & set(dx.hadm_id))
    has_ast = set(micro[micro.ab_name.notna()].hadm_id)
    hadms = sorted(hadms, key=lambda h: (h not in has_ast, h))[:n]
    skipped: Counter = Counter()
    for k, hadm in enumerate(hadms, start=1):
        orders = rx[rx.hadm_id == hadm].sort_values("start")
        start = orders.start.iloc[0]
        first_day = orders[orders.start <= start + timedelta(hours=24)]
        lines = list(dict.fromkeys(first_day.line))
        subject = int(orders.subject_id.iloc[0])
        pt = patients.loc[subject]
        scr = labs[(labs.hadm_id == hadm) & (labs.when <= start)].sort_values("when")
        titles = list(dict.fromkeys(dx[dx.hadm_id == hadm].sort_values("seq_num").long_title))
        diagnosis = "; ".join(titles)
        request = {
            "patient": {
                "id": f"mimic-demo-{k:02d}",
                "age_years": int(pt.anchor_age),
                "sex": pt.gender,
                "serum_creatinine_mg_dl": float(scr.valuenum.iloc[-1]) if len(scr) else None,
                "allergy_status": "UNKNOWN",  # the demo has no allergy table
            },
            "setting": "WARD",
            "diagnosis_text": diagnosis,
            "prescription": "\n".join(lines),
            "started_at": start.isoformat(),
            "cultures": _cultures(micro[micro.hadm_id == hadm], catalog, start, skipped),
        }
        simulated = next((code for pat, code in SIMULATED_CODE if pat.search(titles[0])), None)
        yield f"case-{k:02d}", request, simulated, start
    if skipped:
        print(f"# AST agents not in catalog (left out of panels): {dict(skipped)}", file=sys.stderr)


def run_case(case_id, body, syndrome_code, start, catalog, pack, renal, store, tmp: Path):
    service = StewardshipService(
        catalog=catalog,
        rulepack=pack,
        renal=renal,
        audit=JsonlAuditLog(tmp / f"{case_id}.jsonl"),
        retriever=store,
        clock=lambda: start.to_pydatetime() + timedelta(hours=48),
    )
    request = EpisodeRequest.model_validate(body | {"syndrome_code": syndrome_code})
    return service.evaluate_request(request)


# --- Report ---------------------------------------------------------------------------


def _pct(a: int, b: int) -> str:
    return f"{a}/{b} ({100 * a / b:.0f}%)" if b else "0/0"


def coverage_md(name: str, cov: dict, truth: bool) -> list[str]:
    s = cov["stats"]
    out = [
        f"### {name}",
        "",
        f"- distinct typed lines: {s['lines']}; orders built: {_pct(s['orders'], s['lines'])}",
        f"- drug identified (ACCEPTED): {_pct(s['status_ACCEPTED'], s['orders'])}; "
        f"AMBIGUOUS {s['status_AMBIGUOUS']}; NO_MATCH {s['status_NO_MATCH']}",
    ]
    for field in ("dose_mg", "freq_per_day", "route", "duration_days"):
        line = f"- {field} read: {_pct(s[f'has_{field}'], s['orders'])}"
        if truth and field != "duration_days":
            line += (
                f"; vs dataset field: right {s[f'right_{field}']}, wrong {s[f'wrong_{field}']}, "
                f"missed {s[f'missed_{field}']} of {s[f'truth_{field}']}"
            )
        out.append(line)
    if cov["errors"]:
        out.append(f"- lines with no order: {dict(cov['errors'])}")
    out.append(f"- most common unidentified names: {cov['unidentified'].most_common(12)}")
    return [*out, ""]


def report_md(case_id, body, run, report) -> list[str]:
    out = [
        f"#### {case_id} · run {run}",
        "",
        f"Diagnosis (ICD titles): {body['diagnosis_text']}",
        f"Syndrome: `{report.syndrome.code}` ({report.syndrome.resolution}) · "
        f"status **{report.status.value}** · cultures: {len(body['cultures'])}",
        "",
        "```",
        body["prescription"],
        "```",
        "",
        "| order | generic | status | dose mg | /day | route | days |",
        "|---|---|---|---|---|---|---|",
    ]
    for o in report.orders:
        out.append(
            f"| {o.id} | {o.generic or '–'} | {o.norm_status.value} | {o.dose_mg or '–'} | "
            f"{o.freq_per_day or '–'} | {o.route or '–'} | {o.duration_days or '–'} |"
        )
    out += ["", "| rule | outcome | order | message | action | evidence | passages |"]
    out.append("|---|---|---|---|---|---|---|")
    for f in report.items:
        msg = f.message.replace("|", "/")[:140]
        out.append(
            f"| {f.rule_id} | {f.outcome.value} | {f.order_id or '–'} | {msg} | "
            f"{f.action or '–'} | {len(f.evidence)} | {len(f.guideline_passages)} |"
        )
    if report.warnings:
        out += ["", "Warnings: " + " / ".join(report.warnings)]
    return [*out, ""]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mimic", type=Path, required=True)
    ap.add_argument("--eicu", type=Path)
    ap.add_argument("--cases", type=int, default=12)
    ap.add_argument("--out", type=Path, default=Path("typed_rx_report.md"))
    args = ap.parse_args()

    catalog, pack, renal = Catalog.load(), YamlRulePack(), RenalDosing.load()
    store = build_store(pack, name="typed-rx-eval")
    md = ["# Typed prescription evaluation (PhysioNet demo data)", "", "## Parser coverage", ""]
    md += coverage_md("MIMIC-IV demo", coverage(mimic_lines(args.mimic), catalog, truth=True), True)
    if args.eicu:
        md += coverage_md("eICU demo", coverage(eicu_lines(args.eicu), catalog, truth=False), False)

    detail: list[str] = []
    summary = [
        "| case | first diagnosis | orders | identified | cultures | run | syndrome | flags |",
        "|---|---|---|---|---|---|---|---|",
    ]
    tally = Counter()
    tmp = args.out.parent / "audit"
    tmp.mkdir(parents=True, exist_ok=True)
    for case_id, body, simulated, start in mimic_cases(args.mimic, catalog, args.cases):
        runs = [("A: diagnosis text only", None)]
        if simulated:
            runs.append((f"B: simulated clinician choice `{simulated}`", simulated))
        for run, code in runs:
            try:
                report = run_case(case_id, body, code, start, catalog, pack, renal, store, tmp)
            except Exception as exc:  # noqa: BLE001 - a failing case is a result
                tally["errors"] += 1
                detail += [f"#### {case_id} · run {run}", "", f"**ERROR** {exc!r}", ""]
                continue
            tally["runs"] += 1
            for f in report.items:
                tally[f"{f.rule_id} {f.outcome.value}"] += 1
            flags = Counter(f.rule_id.split("_")[0] for f in report.items if f.outcome == "FLAG")
            identified = sum(o.norm_status is NormStatus.ACCEPTED for o in report.orders)
            cells = [
                case_id,
                body["diagnosis_text"].split(";")[0][:45],
                len(report.orders),
                identified,
                len(body["cultures"]),
                run[0],
                report.syndrome.code or "–",
                ", ".join(f"{k}×{v}" for k, v in sorted(flags.items())) or "–",
            ]
            summary.append("| " + " | ".join(map(str, cells)) + " |")
            detail += report_md(case_id, body, run, report)
    md += ["## End to end (MIMIC-IV demo admissions)", "", *summary, "", *detail]
    md += ["## Finding tally", "", *(f"- {k}: {v}" for k, v in sorted(tally.items())), ""]
    args.out.write_text("\n".join(md))
    print(f"wrote {args.out}: {tally['runs']} runs, {tally['errors']} errors")


if __name__ == "__main__":
    main()
