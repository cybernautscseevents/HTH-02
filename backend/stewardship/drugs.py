"""Drug identity and reference data: name normalization, AWaRe tier, intrinsic resistance.

A typed or OCR-read drug name is accepted only on an exact match to a known generic, a
documented alias, or an Indian brand from a cited source. A near miss comes back AMBIGUOUS with
candidates for a person to confirm, because a confidently wrong drug (cefixime read as
cefuroxime) is worse than no answer. Every result carries the reason it was reached.

Sources (see data/reference/README.md):
- data/aware.csv: WHO AWaRe classification 2025; antibiotics WHO does not classify come from
  WHONET AMRIE with tier "Not classified".
- data/drug_aliases.csv: other spellings (Indian Pharmacopoeia, USAN, AMRIE) with their basis.
- data/brands_india.csv: brand names from Indian manufacturers' prescribing information.
- data/intrinsic_resistance.csv and AMRIE Organisms.txt: CLSI expected resistance.
"""

import csv
import logging
import re
from difflib import get_close_matches
from pathlib import Path
from typing import NamedTuple

from . import config
from .schemas import AwareTier, NormStatus, Route

logger = logging.getLogger(__name__)

_FORM_WORDS = re.compile(r"^(tab|tablet|cap|capsule|inj|injection|syp|syrup|susp|suspension)\b\.?")
_TIERS = {"access": AwareTier.ACCESS, "watch": AwareTier.WATCH, "reserve": AwareTier.RESERVE}
# A "+" followed by a letter after a strength ("Augmentin 625 + Metrogyl 400") means a second
# drug on the same line; "500+125 mg" strength notation does not match.
_SECOND_DRUG = re.compile(r"\d[^+]*\+\s*[a-z]")


class Normalized(NamedTuple):
    generic: str | None
    brand: str | None
    status: NormStatus
    candidates: tuple[str, ...] = ()
    reason: str = ""


def _key(name: str) -> str:
    """Comparable form of a name: lower case, separators as single spaces."""
    name = re.sub(r"[/\-+&,.]|\band\b|\bwith\b", " ", name.lower())
    return " ".join(name.split())


def _drug_name(raw_text: str) -> str:
    """The name part of a prescription line: no dosage form, strength or frequency."""
    text = _FORM_WORDS.sub("", raw_text.strip().lower()).strip()
    return re.split(r"\d", text, maxsplit=1)[0].strip(" .-")


def _read_csv(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=delimiter))


class Catalog:
    """Reference drug data behind the DrugCatalog port, plus drug name normalization."""

    def __init__(
        self,
        tiers: dict[tuple[str, str], AwareTier],
        aliases: dict[str, tuple[str, str]],
        brands: dict[str, tuple[frozenset[str], str]],
        intrinsic: frozenset[tuple[str, str]],
        organisms: frozenset[str],
        product_words: frozenset[str] = frozenset(),
    ) -> None:
        """tiers: (generic, route or "") -> tier. aliases: alias -> (generic, basis).
        brands: brand -> (generics, source). Organism names are lower case. product_words are
        the non-numeric words of listed product names ("duo", "dds") allowed beside a brand."""
        self._tiers = tiers
        self._intrinsic = intrinsic
        self._organisms = organisms
        self._generics = {_key(g): g for g, _ in tiers}
        self._aliases = {_key(a): v for a, v in aliases.items()}
        self._brands = {_key(b): v for b, v in brands.items()}
        self._product_words = product_words

    @classmethod
    def load(cls) -> "Catalog":
        """Load the catalog from the files named in config."""
        tiers = {
            (row["generic"], row["route"]): _TIERS.get(
                row["aware_tier"].lower(), AwareTier.NOT_CLASSIFIED
            )
            for row in _read_csv(config.AWARE_CSV)
        }
        aliases = {
            row["alias"]: (row["generic"], row["basis"])
            for row in _read_csv(config.DRUG_ALIASES_CSV)
        }
        brand_generics: dict[str, set[str]] = {}
        brand_sources: dict[str, str] = {}
        product_words: set[str] = set()
        for row in _read_csv(config.BRANDS_CSV):
            brand_generics.setdefault(row["brand"], set()).add(row["generic"])
            product_words.update(
                w for w in _key(row["product"]).split() if w != row["brand"] and w.isalpha()
            )
            brand_sources.setdefault(
                row["brand"], f"{row['manufacturer']} prescribing information ({row['source_url']})"
            )
        brands = {b: (frozenset(g), brand_sources[b]) for b, g in brand_generics.items()}
        intrinsic = frozenset(
            (row["organism"], row["generic"]) for row in _read_csv(config.INTRINSIC_RESISTANCE_CSV)
        )
        organisms = frozenset(
            row["ORGANISM"].lower()
            for row in _read_csv(config.ORGANISMS_TXT, delimiter="\t")
            if row["ORGANISM"]
        )
        return cls(tiers, aliases, brands, intrinsic, organisms, frozenset(product_words))

    def aware_tier(self, generic: str, route: Route | None = None) -> AwareTier:
        """WHO AWaRe 2025 tier. Route-specific entries (fosfomycin, minocycline) need the route;
        a drug whose tiers differ by route and whose route is missing or unlisted (for example
        IM) is NOT_CLASSIFIED."""
        if (generic, "") in self._tiers:
            return self._tiers[(generic, "")]
        by_route = {r: t for (g, r), t in self._tiers.items() if g == generic}
        if route is not None and str(route) in by_route:
            return by_route[str(route)]
        tiers = set(by_route.values())
        return tiers.pop() if len(tiers) == 1 else AwareTier.NOT_CLASSIFIED

    def is_antibiotic(self, generic: str) -> bool:
        """True for antibiotics in the WHO AWaRe list or AMRIE's human ATC J01 list."""
        return any(g == generic for g, _ in self._tiers)

    def knows_organism(self, organism: str) -> bool:
        """True when the organism is in the AMRIE organism list."""
        return organism.strip().lower() in self._organisms

    def intrinsically_resistant(self, organism: str, generic: str) -> bool:
        """True when CLSI lists the organism as intrinsically resistant to the drug.

        Returns False for organisms not in the reference list; C9 reports those separately.
        """
        return (organism.strip().lower(), generic) in self._intrinsic

    def normalize(self, raw_text: str) -> Normalized:
        """Map a written drug name to a generic, or say why it cannot be identified."""
        if _SECOND_DRUG.search(raw_text.lower()):
            first = self.normalize(_drug_name(raw_text))
            return Normalized(
                None,
                None,
                NormStatus.AMBIGUOUS,
                (first.generic,) if first.generic else first.candidates,
                reason="The line appears to name more than one drug; enter each as its own order.",
            )
        name = _drug_name(raw_text)
        key = _key(name)
        if not key:
            return Normalized(None, None, NormStatus.NO_MATCH, reason="No drug name found.")
        if key in self._generics:
            generic = self._generics[key]
            return Normalized(generic, None, NormStatus.ACCEPTED, reason="Exact generic name.")
        if key in self._aliases:
            generic, basis = self._aliases[key]
            return Normalized(
                generic, None, NormStatus.ACCEPTED, reason=f"Alias of {generic}: {basis}."
            )
        words = key.split()
        brand_key = (
            key if key in self._brands else next((w for w in words if w in self._brands), None)
        )
        if brand_key is not None:
            generics, source = self._brands[brand_key]
            extra = [w for w in words if w != brand_key and w not in self._product_words]
            if extra and brand_key != key:
                return Normalized(
                    None,
                    brand_key,
                    NormStatus.AMBIGUOUS,
                    tuple(sorted(generics)),
                    reason=f"Brand {brand_key} with unlisted words '{' '.join(extra)}'; may be "
                    "a different product.",
                )
            if len(generics) == 1:
                generic = next(iter(generics))
                return Normalized(
                    generic, brand_key, NormStatus.ACCEPTED, reason=f"Brand {brand_key}: {source}."
                )
            return Normalized(
                None,
                brand_key,
                NormStatus.AMBIGUOUS,
                tuple(sorted(generics)),
                reason=f"Brand {brand_key} maps to more than one generic.",
            )

        candidates: list[str] = []
        names = [*self._generics, *self._aliases, *self._brands]
        for match in get_close_matches(key, names, n=5, cutoff=config.FUZZY_CUTOFF):
            if match in self._generics:
                found = [self._generics[match]]
            elif match in self._aliases:
                found = [self._aliases[match][0]]
            else:
                found = sorted(self._brands[match][0])
            candidates.extend(g for g in found if g not in candidates)
        if candidates:
            return Normalized(
                None,
                None,
                NormStatus.AMBIGUOUS,
                tuple(candidates),
                reason=f"'{name}' is not an exact match; close to: {', '.join(candidates)}.",
            )
        return Normalized(
            None, None, NormStatus.NO_MATCH, reason=f"'{name}' matches no known drug or brand."
        )
