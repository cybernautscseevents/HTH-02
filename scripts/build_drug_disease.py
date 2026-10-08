#!/usr/bin/env python3
"""Build data/drug_disease_labels.csv and data/drug_disease.csv from US FDA drug labels.

Ported from RxGuard module 8's openFDA drug-disease layer (legacy/rxguard/backend/modules/
module8), with three changes: it runs once at build time instead of on every request, it keeps
the exact label sentence as the quote, and it only reads the sections where a label states who
should not get the drug or who needs caution (Contraindications, Boxed Warning, Warnings).

For each antibiotic in the rule pack and the renal table, the script takes the most recent
systemic (oral, IV or IM) label from openFDA and writes:
  drug_disease_labels.csv  one row per drug: which label was read (set id, date, link)
  drug_disease.csv         one row per drug, condition and section: the first label sentence
                           that names the condition

Renal impairment and pregnancy are left out on purpose: rule R4 covers kidney function from cited
renal dosing tables and rule R7 covers pregnancy from data/pregnancy_caution.csv.
A keyword match is not a clinical judgement; rule R8 shows the sentence to the pharmacist.

Usage: python scripts/build_drug_disease.py   (needs network; standard library + PyYAML)
"""

import csv
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RULEPACK_DIR = ROOT / "backend" / "stewardship" / "rulepack"
RENAL_CSV = ROOT / "data" / "renal_dosing.csv"
LABELS_CSV = ROOT / "data" / "drug_disease_labels.csv"
FINDINGS_CSV = ROOT / "data" / "drug_disease.csv"

API = "https://api.fda.gov/drug/label.json"
SYSTEMIC_ROUTES = {"ORAL", "INTRAVENOUS", "INTRAMUSCULAR"}

# WHO generic name (as used in the engine) -> US label generic name, where they differ.
US_NAMES = {
    "amoxicillin/clavulanic acid": "amoxicillin and clavulanate potassium",
    "ampicillin/sulbactam": "ampicillin and sulbactam",
    "benzylpenicillin": "penicillin g potassium",
    "cefalexin": "cephalexin",
    "colistin": "colistimethate",
    "imipenem/cilastatin": "imipenem and cilastatin",
    "phenoxymethylpenicillin": "penicillin v potassium",
    "piperacillin/tazobactam": "piperacillin and tazobactam",
    "sulfamethoxazole/trimethoprim": "sulfamethoxazole and trimethoprim",
}

# Label section key -> (name shown to the pharmacist, kind). "contraindication" sections become
# HIGH findings in R8, "warning" sections MODERATE.
SECTIONS = {
    "contraindications": ("Contraindications", "contraindication"),
    "boxed_warning": ("Boxed Warning", "contraindication"),
    "warnings_and_cautions": ("Warnings and Precautions", "warning"),
    "warnings": ("Warnings", "warning"),
}

# Condition code (schemas.Comorbidity) -> phrases that name it in label text. Kept narrow: a
# broad phrase ("blood glucose", "thyroid") matches sentences about something else.
CONDITIONS = {
    "LIVER_DISEASE": (
        "hepatic impairment", "hepatic dysfunction", "hepatic disease", "hepatic insufficiency",
        "liver disease", "cirrhosis",
    ),
    # Not "convulsions": it appears in adverse-reaction lists (aminoglycoside neurotoxicity),
    # not in cautions about patients who have a seizure disorder.
    "SEIZURE_DISORDER": ("seizure", "epilep"),
    "MYASTHENIA_GRAVIS": ("myasthenia gravis",),
    "QT_PROLONGATION": ("qt prolongation", "prolongation of the qt", "qt interval", "torsade"),
    "DIABETES": ("diabetes", "diabetic"),
    "G6PD_DEFICIENCY": ("g6pd", "glucose-6-phosphate dehydrogenase"),
    "AORTIC_ANEURYSM": ("aortic aneurysm",),
}  # fmt: skip

MAX_QUOTE = 400


def engine_generics() -> list[str]:
    names: set[str] = set()
    for path in RULEPACK_DIR.glob("syndromes*.yaml"):
        for syndrome in yaml.safe_load(path.read_text(encoding="utf-8"))["syndromes"]:
            for regimen in (*syndrome.get("first_line", ()), *syndrome.get("alternatives", ())):
                names.add(regimen["generic"])
    with RENAL_CSV.open(encoding="utf-8") as f:
        names.update(row["generic"] for row in csv.DictReader(f))
    return sorted(names)


def fetch_labels(us_name: str) -> list[dict]:
    query = urllib.parse.urlencode({"search": f'openfda.generic_name:"{us_name}"', "limit": 100})
    try:
        with urllib.request.urlopen(f"{API}?{query}", timeout=30) as response:
            return json.load(response)["results"]
    except urllib.error.HTTPError as exc:
        if exc.code == 404:  # openFDA answers "no matches" with 404
            return []
        raise


def pick_label(labels: list[dict]) -> dict | None:
    """Most recent systemic label, preferring the current (PLR) format with a Warnings and
    Precautions section over older labels."""
    systemic = [
        label
        for label in labels
        if SYSTEMIC_ROUTES & set(label.get("openfda", {}).get("route", ()))
        and any(key in label for key in SECTIONS)
    ]
    if not systemic:
        return None
    return max(
        systemic, key=lambda lb: ("warnings_and_cautions" in lb, lb.get("effective_time", ""))
    )


def sentences(text: str) -> list[str]:
    """Split label text into sentences, also before numbered subsection headings ("5.2 Seizures")
    that the API joins onto the previous sentence."""
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.;])\s+(?=[A-Z(•])|\s+(?=\d{1,2}\.\d{1,2} [A-Z])", text)
    return [s.strip() for s in parts if s.strip()]


def first_mention(text: str, phrases: tuple[str, ...]) -> str | None:
    """First sentence naming the condition; a long one is cut to a window around the match so the
    quote always shows the words that matched."""
    for sentence in sentences(text):
        lower = sentence.lower()
        hits = [lower.find(p) for p in phrases if p in lower]
        if not hits:
            continue
        if len(sentence) <= MAX_QUOTE:
            return sentence
        start = max(0, min(min(hits) - MAX_QUOTE // 3, len(sentence) - MAX_QUOTE + 6))
        end = start + MAX_QUOTE - 6
        return ("..." if start else "") + sentence[start:end].strip() + "..."
    return None


def row_kind(kind: str, quote: str, us_name: str) -> str:
    """A contraindication for a reaction "associated with" this drug before (e.g. cholestatic
    jaundice on a previous course) is about the patient's history with the drug, which a
    condition code cannot express; it is kept as a warning so it is shown, not escalated."""
    drug = re.escape(us_name.split()[0])
    if kind == "contraindication" and re.search(
        rf"associated with (prior use of )?{drug}", quote, re.IGNORECASE
    ):
        return "warning"
    return kind


def main() -> None:
    label_rows, finding_rows = [], []
    for generic in engine_generics():
        us_name = US_NAMES.get(generic, generic)
        label = pick_label(fetch_labels(us_name))
        time.sleep(0.3)  # openFDA allows 240 requests a minute without a key
        if label is None:
            print(f"no systemic FDA label: {generic} ({us_name})")
            continue
        openfda = label["openfda"]
        brand = (openfda.get("brand_name") or [us_name])[0]
        date = label.get("effective_time", "")
        label_rows.append(
            {
                "generic": generic,
                "set_id": label["set_id"],
                "title": f"US FDA label: {brand} ({us_name}), "
                f"{'/'.join(sorted(openfda.get('route', ()))).lower()}, "
                f"effective {date[:4]}-{date[4:6]}-{date[6:]}",
                "effective_time": date,
                "url": f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={label['set_id']}",
            }
        )
        for key, (section, kind) in SECTIONS.items():
            text = " ".join(label.get(key, ()))
            for condition, phrases in CONDITIONS.items():
                quote = first_mention(text, phrases)
                if quote:
                    finding_rows.append(
                        {
                            "generic": generic,
                            "condition": condition,
                            "kind": row_kind(kind, quote, us_name),
                            "section": section,
                            "quote": quote,
                        }
                    )
        print(f"{generic}: {label['set_id']} {date}")

    for path, rows in ((LABELS_CSV, label_rows), (FINDINGS_CSV, finding_rows)):
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {len(rows)} rows to {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
