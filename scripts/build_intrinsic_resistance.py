#!/usr/bin/env python3
"""Build data/intrinsic_resistance.csv from the WHONET AMRIE reference tables.

AMRIE states expected (intrinsic) resistance as rules over organism groups (family, genus,
species group, single organism) and antibiotic groups (single WHONET code or an ATC class
prefix), with exceptions. The engine needs a plain lookup, so this script expands every CLSI
rule into one row per organism name and generic antibiotic from data/aware.csv (canonical WHO names; build that first with scripts/build_aware.py).

CLSI is used because ICMR's AMR surveillance network reports against CLSI breakpoints.

Usage: python scripts/build_intrinsic_resistance.py
"""

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AMRIE = ROOT / "data" / "reference" / "amrie"
AWARE_CSV = ROOT / "data" / "aware.csv"
OUT_CSV = ROOT / "data" / "intrinsic_resistance.csv"
GUIDELINE = "CLSI"


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def split_codes(value: str, sep: str = ",") -> set[str]:
    return {c.strip() for c in value.split(sep) if c.strip()}


def matches(organism: dict[str, str], code_type: str, codes: set[str]) -> bool:
    return organism.get(code_type, "") in codes


def main() -> None:
    organisms = [o for o in read_tsv(AMRIE / "Organisms.txt") if not o["REPLACED_BY"]]
    with AWARE_CSV.open(encoding="utf-8") as f:
        drugs = list(csv.DictReader(f))
    by_whonet = {code: d["generic"] for d in drugs for code in split_codes(d["whonet_codes"], "|")}

    rows = set()
    for rule in read_tsv(AMRIE / "ExpectedResistancePhenotypes.txt"):
        if rule["GUIDELINE"] != GUIDELINE:
            continue
        excluded_abx = split_codes(rule["ANTIBIOTIC_EXCEPTIONS"])
        if rule["ABX_CODE_TYPE"] == "ATC_CODE":
            generics = {
                d["generic"]
                for d in drugs
                if d["atc_code"].startswith(rule["ABX_CODE"])
                and not split_codes(d["whonet_codes"], "|") <= excluded_abx
            }
        else:
            generics = {by_whonet[rule["ABX_CODE"]]} if rule["ABX_CODE"] in by_whonet else set()
        if not generics:
            continue

        org_codes = split_codes(rule["ORGANISM_CODE"])
        exc_codes = split_codes(rule["EXCEPTION_ORGANISM_CODE"])
        for org in organisms:
            if not matches(org, rule["ORGANISM_CODE_TYPE"], org_codes):
                continue
            if exc_codes and matches(org, rule["EXCEPTION_ORGANISM_CODE_TYPE"], exc_codes):
                continue
            for generic in generics:
                rows.add((org["ORGANISM"].lower(), org["WHONET_ORG_CODE"], generic,
                          rule["REFERENCE_TABLE"]))

    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["organism", "whonet_org_code", "generic", "reference_table"])
        writer.writerows(sorted(rows))
    print(f"Wrote {len(rows)} rows to {OUT_CSV}")


if __name__ == "__main__":
    main()
