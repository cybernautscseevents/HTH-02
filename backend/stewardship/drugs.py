"""Drug identity and reference data: name normalization, AWaRe tier, intrinsic resistance.

A typed or OCR-read drug name is accepted only when it matches a known generic or brand
exactly. A near miss comes back AMBIGUOUS with candidates for a person to confirm, because a
confidently wrong drug (cefixime read as cefuroxime) is worse than no answer.

Sources: data/aware.csv and data/intrinsic_resistance.csv are derived from WHONET AMRIE
(see data/reference/README.md); brand names come from data/indian_drug_lexicon.csv.
"""

import csv
import logging
import re
from difflib import get_close_matches
from pathlib import Path
from typing import NamedTuple

from . import config
from .schemas import AwareTier, NormStatus

logger = logging.getLogger(__name__)

# Alternative names, in key form (see _key), mapped to the generic names used in aware.csv.
SYNONYMS = {
    "amoxicillin clavulanate": "amoxicillin/clavulanic acid",
    "amoxicillin clavulanate potassium": "amoxicillin/clavulanic acid",
    "co amoxiclav": "amoxicillin/clavulanic acid",
    "cefalexin": "cephalexin",
    "co trimoxazole": "trimethoprim/sulfamethoxazole",
    "cotrimoxazole": "trimethoprim/sulfamethoxazole",
    "sulfamethoxazole trimethoprim": "trimethoprim/sulfamethoxazole",
    "piperacillin tazobactam": "piperacillin/tazobactam",
}

_FORM_WORDS = re.compile(r"^(tab|tablet|cap|capsule|inj|injection|syp|syrup|susp|suspension)\b\.?")
_TIERS = {"access": AwareTier.ACCESS, "watch": AwareTier.WATCH, "reserve": AwareTier.RESERVE}


class Normalized(NamedTuple):
    generic: str | None
    brand: str | None
    status: NormStatus
    candidates: tuple[str, ...] = ()


def _key(name: str) -> str:
    """Comparable form of a name: lower case, separators as single spaces."""
    name = re.sub(r"[/\-+&,]|\band\b", " ", name.lower())
    return " ".join(name.split())


def _drug_name(raw_text: str) -> str:
    """The name part of a prescription line: no dosage form, strength or frequency."""
    text = raw_text.strip().lower()
    text = _FORM_WORDS.sub("", text).strip()
    return re.split(r"\d", text, maxsplit=1)[0].strip(" .-")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


class Catalog:
    """Reference drug data behind the DrugCatalog port, plus drug name normalization."""

    def __init__(
        self,
        tiers: dict[str, AwareTier],
        brands: dict[str, frozenset[str]],
        intrinsic: frozenset[tuple[str, str]],
        other_generics: frozenset[str] = frozenset(),
    ) -> None:
        self._tiers = tiers
        self._intrinsic = intrinsic
        self._organisms = frozenset(org for org, _ in intrinsic)
        self._generics = {_key(g): g for g in (*tiers, *other_generics)}
        self._generics |= {k: v for k, v in SYNONYMS.items() if v in tiers}
        self._brands = {_key(b): g for b, g in brands.items()}

    @classmethod
    def load(
        cls,
        aware_csv: Path = config.AWARE_CSV,
        lexicon_csv: Path = config.LEXICON_CSV,
        intrinsic_csv: Path = config.INTRINSIC_RESISTANCE_CSV,
    ) -> "Catalog":
        """Load the catalog from the CSV files named in config."""
        tiers = {
            row["generic"]: _TIERS.get(row["aware_tier"].lower(), AwareTier.NOT_CLASSIFIED)
            for row in _read_csv(aware_csv)
        }
        intrinsic = frozenset((row["organism"], row["generic"]) for row in _read_csv(intrinsic_csv))
        brands: dict[str, set[str]] = {}
        other: set[str] = set()
        for row in _read_csv(lexicon_csv):
            generic = SYNONYMS.get(_key(row["generic_name"]), row["generic_name"].lower())
            brands.setdefault(row["brand_name"], set()).add(generic)
            if generic not in tiers:
                other.add(generic)
        frozen = {b: frozenset(g) for b, g in brands.items()}
        return cls(tiers, frozen, intrinsic, frozenset(other))

    def aware_tier(self, generic: str) -> AwareTier:
        """WHO AWaRe tier; NOT_CLASSIFIED for drugs missing from the table."""
        return self._tiers.get(generic, AwareTier.NOT_CLASSIFIED)

    def is_antibiotic(self, generic: str) -> bool:
        """True for systemic antibacterials (ATC J01) listed in aware.csv."""
        return generic in self._tiers

    def intrinsically_resistant(self, organism: str, generic: str) -> bool:
        """True when CLSI lists the organism as intrinsically resistant to the drug."""
        name = organism.strip().lower()
        if name not in self._organisms:
            logger.warning("Organism '%s' not in intrinsic resistance table", organism)
        return (name, generic) in self._intrinsic

    def normalize(self, raw_text: str) -> Normalized:
        """Map a written drug name to a generic, or say why it cannot be identified."""
        name = _drug_name(raw_text)
        key = _key(name)
        if key in self._generics:
            return Normalized(self._generics[key], None, NormStatus.ACCEPTED)
        if key in self._brands:
            generics = self._brands[key]
            if len(generics) == 1:
                return Normalized(next(iter(generics)), name, NormStatus.ACCEPTED)
            return Normalized(None, name, NormStatus.AMBIGUOUS, tuple(sorted(generics)))

        names = [*self._generics, *self._brands]
        close = get_close_matches(key, names, n=5, cutoff=config.FUZZY_CUTOFF)
        candidates: list[str] = []
        for match in close:
            found = {self._generics[match]} if match in self._generics else self._brands[match]
            candidates.extend(g for g in sorted(found) if g not in candidates)
        if candidates:
            return Normalized(None, None, NormStatus.AMBIGUOUS, tuple(candidates))
        return Normalized(None, None, NormStatus.NO_MATCH)
