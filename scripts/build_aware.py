#!/usr/bin/env python3
"""Build data/aware.csv and data/drug_aliases.csv.

AWaRe tiers come only from the WHO AWaRe classification 2025 spreadsheet
(data/reference/who/B09489-eng.xlsx, sheet "AWaRe classification 2025"). Antibiotics that WHO
does not classify but WHONET AMRIE lists as human ATC J01 agents are added with tier
"Not classified", so the engine still recognises them as antibiotics instead of skipping them.

Canonical generic names follow WHO spelling (lower case, hyphens as spaces, route suffix moved
to its own column). Other spellings (AMRIE/USAN names, Indian Pharmacopoeia spellings) become
rows in data/drug_aliases.csv, each with the basis for the mapping.

Usage: python scripts/build_aware.py   (standard library only)
"""

import csv
import re
import zipfile
from difflib import SequenceMatcher
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WHO_XLSX = ROOT / "data" / "reference" / "who" / "B09489-eng.xlsx"
WHO_SHEET = "AWaRe classification 2025"
AMRIE_ANTIBIOTICS = ROOT / "data" / "reference" / "amrie" / "Antibiotics.txt"
AWARE_CSV = ROOT / "data" / "aware.csv"
ALIASES_CSV = ROOT / "data" / "drug_aliases.csv"

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
ROUTES = {"iv": "IV", "oral": "PO"}

# Spellings used in Indian prescriptions and guidelines, with the document that uses them.
INDIAN_ALIASES = [
    (
        "amoxycillin",
        "amoxicillin",
        "Indian Pharmacopoeia spelling; GSK India Augmentin PI: 'Amoxycillin and Potassium "
        "Clavulanate Tablets IP'",
    ),
    (
        "amoxycillin and potassium clavulanate",
        "amoxicillin/clavulanic acid",
        "GSK India Augmentin 625/1g Duo PI, section 1 Generic Name",
    ),
    (
        "amoxycillin clavulanate",
        "amoxicillin/clavulanic acid",
        "Short form of the Indian Pharmacopoeia name 'Amoxycillin and Potassium Clavulanate' "
        "(GSK India Augmentin PI)",
    ),
    (
        "amoxicillin and clavulanate potassium",
        "amoxicillin/clavulanic acid",
        "US FDA label generic name (DailyMed)",
    ),
    (
        "amoxicillin clavulanate",
        "amoxicillin/clavulanic acid",
        "Short form of 'amoxicillin and clavulanate potassium' (US FDA label generic name)",
    ),
    (
        "cotrimoxazole",
        "sulfamethoxazole/trimethoprim",
        "NCDC National Treatment Guidelines v2.0 (2025), section 5.1: 'Cotrimoxazole 960 mg BD'",
    ),
    (
        "co-trimoxazole",
        "sulfamethoxazole/trimethoprim",
        "ICMR Treatment Guidelines 2019, Table 9.2: 'Co-trimoxazole'",
    ),
]

# AMRIE names whose WHO name is too different for same_drug(), checked by hand. Each pair also
# shares an ATC code (asserted in main).
REVIEWED_SYNONYMS = {
    "penicillin v": "phenoxymethylpenicillin",
    "sulfisoxazole": "sulfafurazole",
    "moxalactam (latamoxef)": "latamoxef",
    "cefetamet": "cefetamet pivoxil",
}


def canonical(who_name: str) -> tuple[str, str]:
    """WHO name -> (generic, route). 'Fosfomycin_oral' -> ('fosfomycin', 'PO')."""
    name, _, suffix = who_name.strip().partition("_")
    return name.lower().replace("-", " "), ROUTES.get(suffix.lower(), "")


def same_drug(amrie_name: str, who_generic: str) -> bool:
    """Every component of the AMRIE name resembles a component of the WHO name.

    Shared ATC codes alone are not enough: AMRIE gives ridinilazole the ATC code of cefaloridine,
    and lab-only combinations such as ceftazidime/clavulanic acid share a code with
    ceftazidime/avibactam.
    """
    name = re.sub(r"\(.*?\)|-high$", "", amrie_name).strip()
    who_parts = who_generic.split("/")
    return all(
        max(SequenceMatcher(None, part.strip(), w).ratio() for w in who_parts) >= 0.7
        for part in name.split("/")
    )


def read_sheet(path: Path, sheet_name: str) -> list[list[str]]:
    z = zipfile.ZipFile(path)
    shared = [
        "".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t"))
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS)
    ]
    workbook = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {
        r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    }
    sheet = next(s for s in workbook.find("m:sheets", NS) if s.get("name") == sheet_name)
    target = rels[sheet.get(f"{{{NS['r']}}}id")].lstrip("/").removeprefix("xl/")
    rows = []
    for row in ET.fromstring(z.read(f"xl/{target}")).iter(f"{{{NS['m']}}}row"):
        cells = {}
        for c in row.findall("m:c", NS):
            v = c.find("m:v", NS)
            col = 0
            for ch in re.match(r"[A-Z]+", c.get("r")).group():
                col = col * 26 + ord(ch) - 64
            text = "" if v is None else (shared[int(v.text)] if c.get("t") == "s" else v.text)
            cells[col - 1] = text.strip()
        rows.append([cells.get(i, "") for i in range(max(cells, default=-1) + 1)])
    return rows


def main() -> None:
    rows = read_sheet(WHO_XLSX, WHO_SHEET)
    header = next(i for i, r in enumerate(rows) if r and r[0] == "Antibiotic")
    who = []
    for r in rows[header + 1 :]:
        if not r or not r[0]:
            continue
        generic, route = canonical(r[0])
        who.append(
            dict(
                generic=generic,
                route=route,
                who_name=r[0],
                atc_code=r[2].strip(),
                drug_class=r[1],
                aware_tier=r[3],
                eml_2025=r[4],
                source="WHO AWaRe 2025",
            )
        )
    who_generics = {w["generic"] for w in who}

    with AMRIE_ANTIBIOTICS.open(encoding="utf-8-sig") as f:
        amrie = [
            a
            for a in csv.DictReader(f, delimiter="\t")
            if a["HUMAN"] == "X" and a["ATC_CODE"].startswith("J01")
        ]

    aliases = {}
    codes: dict[str, set[str]] = {}
    extra = {}
    for a in amrie:
        name = a["ANTIBIOTIC"].lower()
        if name in who_generics:
            generic = name
        elif name in REVIEWED_SYNONYMS:
            generic = REVIEWED_SYNONYMS[name]
            assert any(w["generic"] == generic and w["atc_code"] == a["ATC_CODE"] for w in who)
            aliases[name] = (
                generic,
                f"same ATC code {a['ATC_CODE']}; USAN/INN synonym (reviewed by hand)",
            )
        else:
            same_atc = {
                w["generic"]
                for w in who
                if w["atc_code"] == a["ATC_CODE"] and same_drug(name, w["generic"])
            }
            if len(same_atc) == 1:
                generic = same_atc.pop()
                aliases[name] = (
                    generic,
                    f"same ATC code {a['ATC_CODE']} (WHONET AMRIE name vs WHO AWaRe 2025 name)",
                )
            else:
                generic = name
                extra.setdefault(
                    name,
                    dict(
                        generic=name,
                        route="",
                        who_name="",
                        atc_code=a["ATC_CODE"],
                        drug_class=a["CLASS"],
                        aware_tier="Not classified",
                        eml_2025="",
                        source="WHONET AMRIE (not in WHO AWaRe 2025)",
                    ),
                )
        codes.setdefault(generic, set()).add(a["WHONET_ABX_CODE"])
    for alias, generic, basis in INDIAN_ALIASES:
        assert generic in who_generics, generic
        aliases[alias] = (generic, basis)

    fields = [
        "generic",
        "route",
        "who_name",
        "atc_code",
        "drug_class",
        "aware_tier",
        "eml_2025",
        "whonet_codes",
        "source",
    ]
    with AWARE_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in sorted([*who, *extra.values()], key=lambda r: (r["generic"], r["route"])):
            writer.writerow(row | {"whonet_codes": "|".join(sorted(codes.get(row["generic"], ())))})
    with ALIASES_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["alias", "generic", "basis"])
        writer.writerows((a, g, b) for a, (g, b) in sorted(aliases.items()))
    print(f"{len(who)} WHO rows, {len(extra)} AMRIE-only rows, {len(aliases)} aliases")


if __name__ == "__main__":
    main()
