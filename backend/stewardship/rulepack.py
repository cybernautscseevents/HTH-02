"""Guideline rule pack loaded from rulepack/syndromes.yaml (rules R1, R3 and R5).

The YAML holds every regimen with the page of the Indian guideline it was read from. Loading
fails loudly on a malformed or ambiguous entry, so a data error stops start-up instead of
silently weakening a check. A syndrome, drug or route that is not in the file is simply absent:
the rules then return CANNOT_ASSESS, and nothing is ever filled in from outside the guideline.
"""

import hashlib
from pathlib import Path

import yaml

from . import config
from .schemas import DrugRegimen, Evidence, Route, SyndromeRule


class RulePackError(ValueError):
    """The rule pack file is malformed or contains an ambiguous entry."""


def _range(code: str, label: str, value, kind) -> tuple:
    if value is None:
        return None, None
    try:
        low, high = value
    except (TypeError, ValueError) as exc:
        raise RulePackError(f"{code}: {label} must be [min, max] or null") from exc
    if not 0 <= low <= high or (kind is float and low == 0):
        raise RulePackError(f"{code}: {label} range {value} is not valid")
    return kind(low), kind(high)


def _evidence(source: dict, sources: dict, code: str, quote: str | None) -> Evidence:
    ref = sources.get(source["id"])
    if ref is None:
        raise RulePackError(f"{code}: unknown source '{source['id']}'")
    return Evidence(
        source_id=source["id"],
        title=f"{ref['title'].strip()}, section {source['section']}",
        page=f"p. {source['page']}",
        quote=quote,
    )


def _regimen(entry: dict, syndrome_source: dict, sources: dict, code: str) -> DrugRegimen:
    dose = _range(code, "daily_dose_mg", entry.get("daily_dose_mg"), float)
    days = _range(code, "duration_days", entry.get("duration_days"), int)
    route_basis = entry.get("route_basis")
    if route_basis not in ("stated", "inferred"):
        raise RulePackError(f"{code}: {entry['generic']} needs route_basis stated|inferred")
    quote = entry["quote"]
    if route_basis == "inferred":
        quote += " [route not printed in the guideline; read as oral]"
    return DrugRegimen(
        generic=entry["generic"],
        route=Route(entry["route"]),
        daily_dose_mg_min=dose[0],
        daily_dose_mg_max=dose[1],
        duration_days_min=days[0],
        duration_days_max=days[1],
        evidence=_evidence(syndrome_source, sources, code, quote),
    )


def _syndrome(raw: dict, sources: dict) -> SyndromeRule:
    code = raw["code"]
    source = raw["source"]
    first, alternatives = [], []
    for entry in raw["regimens"]:
        role = entry["role"]
        if role not in ("first_line", "alternative"):
            raise RulePackError(f"{code}: unknown role '{role}'")
        (first if role == "first_line" else alternatives).append(
            _regimen(entry, source, sources, code)
        )
    if not raw["antibiotics_indicated"] and (first or alternatives):
        raise RulePackError(f"{code}: antibiotics not indicated but regimens are listed")
    keys = [(r.generic, r.route) for r in (*first, *alternatives)]
    if len(keys) != len(set(keys)):
        raise RulePackError(f"{code}: a drug is listed twice for the same route")
    return SyndromeRule(
        code=code,
        name=raw["name"],
        antibiotics_indicated=raw["antibiotics_indicated"],
        first_line=tuple(first),
        alternatives=tuple(alternatives),
        culture_required=raw["culture_required"],
        evidence=_evidence(source, sources, code, raw.get("quote")),
    )


class YamlRulePack:
    """RulePack backed by the guideline YAML. `version` changes whenever the file changes, so
    every stored evaluation names the exact guideline data it ran against."""

    def __init__(self, path: Path = config.SYNDROMES_YAML) -> None:
        content = path.read_bytes()
        data = yaml.safe_load(content)
        sources = data["sources"]
        syndromes = [_syndrome(raw, sources) for raw in data["syndromes"]]
        self._syndromes = {s.code: s for s in syndromes}
        if len(self._syndromes) != len(syndromes):
            raise RulePackError("duplicate syndrome code")
        self.version = f"ncdc-ntg-2025:{hashlib.sha256(content).hexdigest()[:12]}"

    def syndrome(self, code: str) -> SyndromeRule | None:
        return self._syndromes.get(code)

    def codes(self) -> tuple[str, ...]:
        """Syndrome codes the pack covers, for UIs and documentation."""
        return tuple(self._syndromes)
