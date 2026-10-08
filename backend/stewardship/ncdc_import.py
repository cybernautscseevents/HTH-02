"""Convert the NCDC 2025 dataset into rule-pack rows. Build-time only; the engine never runs this.

The dataset (data/reference/ncdc/syndromes_ncdc_2025.yaml) holds every regimen of the NCDC
guideline with its dose, frequency, route and duration parsed into fields. The manifest
(rulepack/ncdc_import.yaml) says which of its regimens make up each of our syndrome codes. This
module turns those regimens into rows in the format of rulepack/syndromes.yaml, so the existing
loader and rules R1, R3 and R5 consume them unchanged.

A number is carried over only when it converts exactly to what the rules compare: a fixed mg dose
times a fixed number of doses per day, and a whole number of days. Everything else (weight-based
doses, units, combination strengths like 800/160 mg, route-dependent doses, loading schedules,
single doses, phases) is left out, so R3/R5 return CANNOT_ASSESS for it. Every agent, regimen and
number that is left out is reported with the reason, never dropped silently.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .drugs import Catalog
from .schemas import NormStatus

ROUTES = {"oral": "PO", "intravenous": "IV", "intramuscular": "IM"}
MG_PER_UNIT = {"mg": 1.0, "g": 1000.0, "mcg": 0.001}
ROLES = {"first_line": "first_line", "alternative": "alternative"}
NO_ANTIBIOTIC = ("no_antibiotic", "no_empiric_antibiotic")
SOURCE_ID = "ncdc-ntg-2025"


class ManifestError(ValueError):
    """The manifest names a dataset row that does not exist or cannot be used as stated."""


@dataclass(frozen=True)
class Note:
    """A dataset item that was left out, or a number that was not carried over."""

    ref: str  # dataset key, e.g. "5.1/FL1"
    drug: str | None
    reason: str


@dataclass(frozen=True)
class Conflict:
    """A difference between a hand-checked row and the dataset. The hand-checked row is kept."""

    code: str
    generic: str
    route: str
    field: str
    hand_checked: object
    dataset: object


@dataclass
class ImportResult:
    syndromes: list[dict] = field(default_factory=list)
    skipped_agents: list[Note] = field(default_factory=list)
    withheld: list[Note] = field(default_factory=list)  # numbers not carried over
    merged: list[Note] = field(default_factory=list)  # same drug and route listed twice
    unassigned: list[Note] = field(default_factory=list)  # dataset rows used by no code
    conflicts: list[Conflict] = field(default_factory=list)
    compared: list[str] = field(default_factory=list)  # hand-checked codes compared


def load_yaml(path: Path) -> dict:
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    with path.open(encoding="utf-8") as f:
        return yaml.load(f, Loader=loader)  # noqa: S506 - safe loader


# --- numbers -----------------------------------------------------------------------------


def daily_dose_mg(agent: dict, regimen: dict) -> tuple[list[float] | None, str | None]:
    """[min, max] mg per day, or (None, reason) when it does not convert exactly."""
    if not (regimen["executable"] and regimen["dose_checkable"] and regimen["frequency_checkable"]):
        return None, "regimen not checkable in dataset: dose/frequency"
    dose = agent["dose_structured"]
    raw = dose.get("raw")
    if dose.get("parse_status") not in ("scalar", "range"):
        return None, f"dose not a single amount: '{raw}' ({dose.get('parse_status')})"
    if dose.get("per_kg") or dose.get("max_dose") is not None:
        return None, f"weight-based dose: '{raw}'"
    unit = dose.get("unit")
    if unit not in MG_PER_UNIT:
        return None, f"dose not in mg: '{raw}'"
    low, high = dose["min"] * MG_PER_UNIT[unit], dose["max"] * MG_PER_UNIT[unit]
    if dose.get("per_day"):
        return [low, high], None
    freq = agent["frequency_structured"]
    per_day = freq.get("doses_per_day")
    if freq.get("parse_status") in ("scalar", "single") and isinstance(per_day, int):
        return [low * per_day, high * per_day], None
    if freq.get("parse_status") == "range" and isinstance(per_day, dict):
        return [low * per_day["min"], high * per_day["max"]], None
    return None, f"frequency not fixed: '{freq.get('raw')}' ({freq.get('parse_status')})"


def duration_days(agent: dict, regimen: dict) -> tuple[list[int] | None, str | None]:
    """[min, max] whole days, or (None, reason)."""
    if not (regimen["executable"] and regimen["duration_checkable"]):
        return None, "regimen not checkable in dataset: duration"
    dur = agent["duration_structured"]
    status = dur.get("parse_status")
    if status not in ("scalar", "range"):
        return None, f"duration not a fixed range: '{dur.get('raw')}' ({status})"
    low, high = dur.get("min_days"), dur.get("max_days")
    if not (low and high and float(low).is_integer() and float(high).is_integer()):
        return None, f"duration not whole days: '{dur.get('raw')}'"
    return [int(low), int(high)], None


def routes(agent: dict) -> tuple[list[str], list[str]]:
    """(our routes, routes that have no equivalent in the engine)."""
    found = agent.get("route_structured", {}).get("routes") or []
    return [ROUTES[r] for r in found if r in ROUTES], [r for r in found if r not in ROUTES]


# --- rows ---------------------------------------------------------------------------------


def _quote(regimen: dict, agent: dict) -> str:
    text = (
        f"NCDC dataset {regimen['key']}: {agent['source_drug']} {agent.get('dose_source') or ''} "
        f"{agent.get('route_source') or ''} {agent.get('frequency_source') or ''}"
    )
    text = " ".join(text.split())
    if agent.get("duration_source"):
        text += f", {agent['duration_source']}"
    partners = [a["source_drug"] for a in regimen["agents"] if a is not agent]
    if partners:
        text += f" (given with {', '.join(dict.fromkeys(partners))})"
    if agent.get("condition"):
        text += f" [condition: {agent['condition']}]"
    if regimen.get("applies_when_raw"):
        text += f" [applies to: {regimen['applies_when_raw']}]"
    return text


def _agent_rows(
    regimen: dict, agent: dict, role: str, catalog: Catalog, result: ImportResult
) -> list[dict]:
    ref, drug = regimen["key"], agent["drug"]
    name = catalog.normalize(drug)
    if name.status is not NormStatus.ACCEPTED or name.generic is None:
        result.skipped_agents.append(Note(ref, drug, f"not in the drug catalog ({name.reason})"))
        return []
    if not catalog.is_antibiotic(name.generic):
        result.skipped_agents.append(Note(ref, drug, f"{agent['agent_type']}, not an antibiotic"))
        return []
    ours, other = routes(agent)
    if other:
        result.skipped_agents.append(Note(ref, drug, f"route {', '.join(other)} not supported"))
    if not ours:
        return []
    dose, dose_reason = daily_dose_mg(agent, regimen)
    days, days_reason = duration_days(agent, regimen)
    for reason in (dose_reason, days_reason):
        if reason:
            result.withheld.append(Note(ref, drug, reason))
    return [
        {
            "role": role,
            "generic": name.generic,
            "route": route,
            "route_basis": "dataset",
            "daily_dose_mg": dose,
            "duration_days": days,
            "quote": _quote(regimen, agent),
        }
        for route in ours
    ]


def _merge(rows: list[dict], ref: str, result: ImportResult) -> list[dict]:
    """One row per (drug, route). A field that differs between the copies is dropped (None), so
    the rules return CANNOT_ASSESS instead of picking one of the guideline's values."""
    merged: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["generic"], row["route"])
        if key not in merged:
            merged[key] = dict(row)
            continue
        kept = merged[key]
        if row["role"] == "first_line":
            kept["role"] = "first_line"
        for name in ("daily_dose_mg", "duration_days"):
            if kept[name] != row[name] and kept[name] is not None:
                result.merged.append(
                    Note(
                        ref,
                        row["generic"],
                        f"{row['route']} listed more than once with different {name} "
                        f"({kept[name]} vs {row[name]}); {name} not checked",
                    )
                )
                kept[name] = None
        if row["quote"] not in kept["quote"]:
            kept["quote"] += f" | {row['quote']}"
    return list(merged.values())


def _regimen(section: dict, local_id: str) -> dict:
    for regimen in section["regimens"]:
        if regimen["id"] == local_id:
            return regimen
    raise ManifestError(f"{section['id']}: no regimen '{local_id}' in the dataset")


def _rows(section: dict, local_ids: list[str], catalog: Catalog, result: ImportResult) -> list:
    rows = []
    for local_id in local_ids:
        regimen = _regimen(section, local_id)
        role = ROLES.get(regimen["category"])
        if role is None:
            raise ManifestError(f"{regimen['key']} is '{regimen['category']}', not a treatment")
        for agent in regimen["agents"]:
            rows.extend(_agent_rows(regimen, agent, role, catalog, result))
    return _merge(rows, f"{section['id']}", result)


def _source(section: dict) -> dict:
    return {
        "id": SOURCE_ID,
        "section": section["source"]["section"],
        "page": section["source"]["pages"],
    }


def _syndrome(entry: dict, section: dict, catalog: Catalog, result: ImportResult) -> dict:
    out = {
        "code": entry.get("code") or entry["covered_by"],
        "name": entry.get("name") or section["syndrome"],
        "ncdc": section["id"],
        "source": _source(section),
    }
    if "no_antibiotic" in entry:
        regimen = _regimen(section, entry["no_antibiotic"])
        if regimen["category"] not in NO_ANTIBIOTIC:
            raise ManifestError(f"{regimen['key']} is '{regimen['category']}', not no-antibiotic")
        label = regimen.get("applies_when_raw") or section["syndrome"]
        out |= {
            "antibiotics_indicated": False,
            "culture_required": False,
            "quote": f"NCDC dataset {regimen['key']}: {label}: no antibiotic",
            "regimens": [],
        }
        return out
    basis = entry.get("culture_basis")
    if basis and basis not in (section.get("diagnostics_and_culture") or []):
        raise ManifestError(f"{section['id']}: culture_basis is not the dataset's own text")
    out |= {"antibiotics_indicated": True, "culture_required": bool(basis)}
    if basis:
        out["culture_basis"] = basis
    out["regimens"] = _rows(section, entry["regimens"], catalog, result)
    return out


# --- comparison with the hand-checked pack -------------------------------------------------


def _compare(hand: dict, dataset: dict, result: ImportResult) -> None:
    code = hand["code"]
    result.compared.append(code)
    if hand["antibiotics_indicated"] != dataset["antibiotics_indicated"]:
        result.conflicts.append(
            Conflict(
                code,
                "-",
                "-",
                "antibiotics_indicated",
                hand["antibiotics_indicated"],
                dataset["antibiotics_indicated"],
            )
        )
    ours = {(r["generic"], r["route"]): r for r in hand["regimens"]}
    theirs = {(r["generic"], r["route"]): r for r in dataset["regimens"]}
    for key in sorted(ours.keys() | theirs.keys()):
        a, b = ours.get(key), theirs.get(key)
        if a is None or b is None:
            result.conflicts.append(Conflict(code, *key, "listed", a is not None, b is not None))
            continue
        for name in ("role", "daily_dose_mg", "duration_days"):
            if a.get(name) != b.get(name):
                result.conflicts.append(Conflict(code, *key, name, a.get(name), b.get(name)))


# --- entry point -----------------------------------------------------------------------------


def convert(source: dict, manifest: dict, hand_checked: dict, catalog: Catalog) -> ImportResult:
    """Build the imported syndromes, the comparison with the hand-checked pack, and the list of
    everything that was not imported."""
    result = ImportResult()
    sections = {s["id"]: s for s in source["syndromes"]}
    hand = {s["code"]: s for s in hand_checked["syndromes"]}
    used: set[str] = set()
    for entry in manifest["syndromes"]:
        section = sections.get(entry["ncdc"])
        if section is None:
            raise ManifestError(f"no dataset section '{entry['ncdc']}'")
        ids = [
            *entry.get("regimens", []),
            *([entry["no_antibiotic"]] if "no_antibiotic" in entry else []),
        ]
        used.update(f"{section['id']}/{i}" for i in ids)
        if "covered_by" in entry:
            if entry["covered_by"] not in hand:
                raise ManifestError(f"covered_by '{entry['covered_by']}' is not hand-checked")
            # Rows of a compared section are not part of the import, so their notes are not
            # reported as import gaps.
            _compare(
                hand[entry["covered_by"]],
                _syndrome(entry, section, catalog, ImportResult()),
                result,
            )
            continue
        if entry["code"] in hand:
            raise ManifestError(f"'{entry['code']}' is already a hand-checked code")
        result.syndromes.append(_syndrome(entry, section, catalog, result))
    codes = [s["code"] for s in result.syndromes]
    if len(codes) != len(set(codes)):
        raise ManifestError("duplicate code in the manifest")
    excluded = {e["ncdc"]: e["reason"] for e in manifest.get("excluded", [])}
    for section in source["syndromes"]:
        for regimen in section["regimens"]:
            if regimen["key"] in used:
                continue
            drugs = ", ".join(a["drug"] for a in regimen["agents"]) or None
            reason = excluded.get(section["id"]) or (
                f"{regimen['category']} row ({regimen.get('applies_when_raw') or 'no sub-group'}); "
                "not part of any imported table"
            )
            result.unassigned.append(Note(regimen["key"], drugs, reason))
    for section in source["syndromes"]:
        if not section["regimens"] and section["id"] not in {
            e["ncdc"] for e in manifest["syndromes"]
        }:
            result.unassigned.append(
                Note(section["id"], None, excluded.get(section["id"]) or "section has no regimens")
            )
    return result
