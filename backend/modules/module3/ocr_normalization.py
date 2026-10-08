#!/usr/bin/env python3
"""
backend/modules/module3/ocr_normalization.py
============================================
M3 — OCR Drug Name Normalization / Error-Recovery Module
=========================================================

Takes a raw PaddleOCR token (one word / short phrase) and resolves it to a
known drug name with a calibratable confidence score, or flags it as
AMBIGUOUS / NEEDS REVIEW.

Pipeline (five inspectable stages):
  1. generate_candidates  — fuzzy match + OCR-substitution expansion
  2. score_candidates     — composite scoring (similarity + OCR-aware bonuses)
  3. validate_with_context — optional dosage/formulation context signal
  4. decide               — threshold + ambiguity-gap logic -> ACCEPTED / AMBIGUOUS / NO_MATCH
  5. lookup_generic       — brand -> generic mapping as a separate, auditable step

Key design decisions
--------------------
* NEVER silently pick a wrong drug when uncertain.  If confidence is too low
  or two candidates are within `ambiguity_gap` of each other, return AMBIGUOUS
  with the candidate list rather than making a best-guess.
* Confidence threshold is a CONFIGURABLE PARAMETER (NormConfig.confidence_threshold).
  The default (0.72) is an UNCALIBRATED PLACEHOLDER — run the benchmark script
  with --threshold-sweep to calibrate against a labelled set.
* OCR substitution errors (O/0, l/1/I, rn/m, cl/d …) are used as a SCORING
  SIGNAL that increases confidence when they explain the edit distance.  They
  are NOT used to silently rewrite the token before matching.
* Brand→generic mapping is Stage 5, completely separate from the fuzzy match
  in Stage 1/2, so every step of "OCR text -> matched drug -> generic" is
  independently auditable.
* Every call produces a structured audit_log dict with all intermediate state.

Dependency: RapidFuzz (pip install rapidfuzz)  — already in venv.
No network calls.  Fully offline.

Usage
-----
    from backend.modules.module3.ocr_normalization import normalize_ocr_token, NormConfig

    result = normalize_ocr_token("Nixcil")
    print(result.status, result.matched_name, result.generic_name, result.confidence)

    # Tune the decision thresholds without changing code:
    cfg = NormConfig(confidence_threshold=0.80, ambiguity_gap=0.08, top_n=5)
    result = normalize_ocr_token("Metro", config=cfg)
"""

from __future__ import annotations

import csv
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from rapidfuzz import fuzz, process as rf_process
from rapidfuzz.distance import Levenshtein

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OCR confusion table
# ---------------------------------------------------------------------------
# Maps a character (or digraph) that OCR commonly reads *as* the key
# to the set of characters it might actually be on the page.
# These are used in Stage 1 to generate OCR-variant candidates and in
# Stage 2 to score how well the OCR error model explains the edit distance.
#
# Format: OCR_CONFUSIONS[ocr_char] = [possible_true_chars]
OCR_CONFUSIONS: Dict[str, List[str]] = {
    "0": ["O", "o", "Q"],
    "O": ["0", "Q"],
    "o": ["0", "a", "y"],
    "1": ["l", "I", "i", "|"],
    "l": ["1", "I", "i"],
    "I": ["1", "l", "i"],
    "rn": ["m"],
    "m": ["rn", "in"],
    "cl": ["d"],
    "d": ["cl"],
    "ri": ["n"],
    "n": ["ri"],
    "vv": ["w"],
    "w": ["vv"],
    "ii": ["n", "u"],
    "u": ["ii"],
    "e": ["c", "o"],
    "c": ["e", "o"],
    "f": ["t"],
    "t": ["f"],
    "g": ["q", "9"],
    "9": ["g", "q"],
    "£": ["E", "e"],
    "$": ["S", "s"],
    "|": ["l", "1", "I"],
    "/": ["l", "1"],
    "\\": ["l", "1"],
    ".": [""],          # trailing dots are common OCR artefacts
    ",": [""],
    "y": ["v", "o"],    # y/o in handwriting (e.g. Thorox→Thyrox, Mhary→Traxy)
    "v": ["y", "u"],    # v/y/u confusion in connected script
    "h": ["n", "li"],   # h/n confusion in low-res OCR
    "a": ["o", "e"],    # a/o confusion (e.g. Nopa→Napa)
}

# Flat set of all (from_char, to_char) OCR substitution pairs for fast lookup
_OCR_PAIRS: set[tuple[str, str]] = set()
for _src, _tgts in OCR_CONFUSIONS.items():
    for _tgt in _tgts:
        _OCR_PAIRS.add((_src.lower(), _tgt.lower()))
        _OCR_PAIRS.add((_tgt.lower(), _src.lower()))


# ---------------------------------------------------------------------------
# Lexicon loading
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LexiconEntry:
    brand_name: str          # canonical capitalisation from CSV
    brand_lower: str         # lowercased, for matching
    generic_name: str
    common_forms: List[str]  # e.g. ["tablet", "syrup"]


def load_lexicon(csv_path: Optional[str] = None) -> List[LexiconEntry]:
    """
    Load the drug lexicon from a CSV file.

    CSV must have columns: brand_name, generic_name, common_forms
    common_forms is a pipe-separated list (e.g. "tablet|syrup").

    Falls back to the bundled placeholder lexicon at
    data/indian_drug_lexicon.csv relative to the repo root.
    """
    if csv_path is None:
        # Locate repo root (go up from this file's location)
        here = Path(__file__).resolve()
        repo_root = here.parent.parent.parent.parent  # …/module3/modules/backend/Kshema
        csv_path = str(repo_root / "data" / "indian_drug_lexicon.csv")

    entries: List[LexiconEntry] = []
    seen_lower: set[str] = set()

    try:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                brand = row.get("brand_name", "").strip()
                generic = row.get("generic_name", "").strip()
                forms_raw = row.get("common_forms", "").strip()
                if not brand:
                    continue
                forms = [f.strip() for f in forms_raw.split("|") if f.strip()]
                brand_l = brand.lower()
                if brand_l in seen_lower:
                    continue          # deduplicate by brand name (keep first)
                seen_lower.add(brand_l)
                entries.append(LexiconEntry(
                    brand_name=brand,
                    brand_lower=brand_l,
                    generic_name=generic,
                    common_forms=forms,
                ))
    except FileNotFoundError:
        logger.warning(
            "Drug lexicon CSV not found at %s — returning empty lexicon. "
            "Pass csv_path= to load_lexicon() to specify a different location.",
            csv_path,
        )

    logger.debug("Loaded %d lexicon entries from %s", len(entries), csv_path)
    return entries


# Module-level default lexicon (lazy-loaded once on first use)
_DEFAULT_LEXICON: Optional[List[LexiconEntry]] = None


def _get_default_lexicon() -> List[LexiconEntry]:
    global _DEFAULT_LEXICON
    if _DEFAULT_LEXICON is None:
        _DEFAULT_LEXICON = load_lexicon()
    return _DEFAULT_LEXICON


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class NormConfig:
    """
    All tunable parameters for the normalization pipeline in one place.

    confidence_threshold : float
        Minimum composite score (0–1) for ACCEPTED status.
        DEFAULT IS AN UNCALIBRATED PLACEHOLDER (0.72).
        Run normalization_benchmark.py --threshold-sweep to calibrate.

    ambiguity_gap : float
        Minimum gap between top and second candidate scores for a
        single unambiguous ACCEPTED result.  If top_score - second_score
        < ambiguity_gap, returns AMBIGUOUS even if top_score >=
        confidence_threshold.
        DEFAULT IS UNCALIBRATED (0.10).

    top_n : int
        Number of candidates to return in the result.candidates list.

    scorer : str
        RapidFuzz scorer to use for base similarity.
        Supported: "ratio", "partial_ratio", "token_sort_ratio",
                   "token_set_ratio", "WRatio".
        "WRatio" (weighted ratio) is the default — it combines multiple
        strategies and tends to work best for short drug names.

    weights : dict
        Scoring weight overrides. Keys: "base", "prefix", "ocr", "len_penalty".
    """
    confidence_threshold: float = 0.72    # UNCALIBRATED — needs calibration
    ambiguity_gap: float = 0.10           # UNCALIBRATED — needs calibration
    top_n: int = 3
    scorer: str = "WRatio"
    diff_generic_max_edit_distance: int = 2  # Max brand edit distance for different-generic ambiguity

    # Weights for composite score (see score_candidates)
    weights: Dict[str, float] = field(default_factory=lambda: {
        "base": 0.70,        # raw RapidFuzz similarity
        "prefix": 0.12,      # bonus for shared first 3 chars
        "ocr": 0.10,         # bonus when OCR confusions explain the diff
        "len_penalty": 0.08, # penalty for length mismatch
    })


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CandidateScore:
    """Scored candidate from the lexicon."""
    brand_name: str          # canonical name from lexicon
    brand_lower: str
    generic_name: str
    common_forms: List[str]
    base_similarity: float   # raw RapidFuzz score (0–1)
    prefix_bonus: float      # how much the shared-prefix bonus added
    ocr_bonus: float         # how much the OCR-confusion bonus added
    len_penalty: float       # how much the length penalty subtracted
    composite_score: float   # final weighted score (0–1)
    ocr_variant_used: Optional[str] = None  # which variant triggered the OCR bonus


@dataclass
class NormResult:
    """
    Final output of normalize_ocr_token().

    status:
        "ACCEPTED"  — one clear winner above threshold, confident pick
        "AMBIGUOUS" — top score is above threshold but two+ candidates
                      are within ambiguity_gap of each other, OR
                      multiple candidates barely above threshold
        "NO_MATCH"  — no candidate reached the confidence threshold

    raw_ocr:      the original, unmodified OCR token
    matched_name: the winning brand name (None if AMBIGUOUS / NO_MATCH)
    generic_name: result of Stage 5 brand->generic lookup (None if unavailable)
    confidence:   composite score of the top candidate
    candidates:   top-N CandidateScore objects (always populated)
    audit_log:    full intermediate state for debugging / audit
    """
    status: Literal["ACCEPTED", "AMBIGUOUS", "NO_MATCH"]
    raw_ocr: str
    matched_name: Optional[str]
    generic_name: Optional[str]
    confidence: float
    candidates: List[CandidateScore]
    audit_log: Dict


# ---------------------------------------------------------------------------
# Stage 0: Text normalisation helpers (NON-DESTRUCTIVE — originals preserved)
# ---------------------------------------------------------------------------

def _normalise_token(raw: str) -> str:
    """
    Produce a cleaned, lowercased version of the OCR token for matching.

    This is used ONLY for matching — the raw token is always preserved
    separately and never silently rewritten.
    """
    # Unicode normalise (handle £, accented chars, etc.)
    token = unicodedata.normalize("NFKD", raw)
    # Strip leading/trailing whitespace + punctuation
    token = token.strip()
    token = re.sub(r"^[^\w]+|[^\w]+$", "", token)
    # Collapse internal whitespace
    token = re.sub(r"\s+", " ", token)
    return token.lower()


def _apply_ocr_substitutions(token_lower: str) -> List[str]:
    """
    Generate OCR-variant strings by applying single substitution rules.

    These variants are used in Stage 1 as ADDITIONAL candidate-generation
    queries — NOT as rewrites of the original token.  The source of each
    match is tagged 'ocr_variant' in the audit log.
    """
    variants: List[str] = []

    # Single-character substitutions
    for i, ch in enumerate(token_lower):
        if ch in OCR_CONFUSIONS:
            for replacement in OCR_CONFUSIONS[ch]:
                variant = token_lower[:i] + replacement.lower() + token_lower[i + 1:]
                if variant != token_lower:
                    variants.append(variant)

    # Digraph substitutions (rn->m, cl->d, etc.)
    for digraph, replacements in OCR_CONFUSIONS.items():
        if len(digraph) < 2:
            continue
        dg = digraph.lower()
        if dg in token_lower:
            for replacement in replacements:
                variant = token_lower.replace(dg, replacement.lower(), 1)
                if variant != token_lower:
                    variants.append(variant)

    # Deduplicate
    seen: set[str] = set()
    unique: List[str] = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            unique.append(v)
    return unique


# ---------------------------------------------------------------------------
# Stage 1: Candidate Generation
# ---------------------------------------------------------------------------

def generate_candidates(
    raw_ocr: str,
    lexicon: List[LexiconEntry],
    top_n: int = 10,
    scorer_name: str = "WRatio",
) -> List[Tuple[LexiconEntry, float, Optional[str]]]:
    """
    Stage 1 — Generate candidate lexicon entries for a raw OCR token.

    Returns a list of (LexiconEntry, base_similarity_0_to_1, ocr_variant_or_None).
    base_similarity is the raw RapidFuzz score normalised to [0, 1].

    Two query strategies:
      A) Direct match: query the cleaned token against all lexicon brand names.
      B) OCR-variant match: for each OCR-substitution variant of the token,
         also query the lexicon and record which variant triggered the match.
         These are tagged with the variant string so Stage 2 can apply an OCR bonus.

    The token is NEVER rewritten — only used as a query.
    """
    if not lexicon:
        return []

    # Select scorer
    scorer_map = {
        "ratio": fuzz.ratio,
        "partial_ratio": fuzz.partial_ratio,
        "token_sort_ratio": fuzz.token_sort_ratio,
        "token_set_ratio": fuzz.token_set_ratio,
        "WRatio": fuzz.WRatio,
    }
    scorer_fn = scorer_map.get(scorer_name, fuzz.WRatio)

    lexicon_labels = [e.brand_lower for e in lexicon]
    label_to_entry = {e.brand_lower: e for e in lexicon}

    results: Dict[str, Tuple[LexiconEntry, float, Optional[str]]] = {}

    def _query(query_str: str, variant_tag: Optional[str]) -> None:
        if not query_str:
            return
        hits = rf_process.extract(
            query_str,
            lexicon_labels,
            scorer=scorer_fn,
            limit=top_n,
            score_cutoff=30,  # 30/100 — very loose; Stage 2 will filter properly
        )
        for label, score, _ in hits:
            sim = score / 100.0
            entry = label_to_entry[label]
            existing = results.get(label)
            if existing is None or sim > existing[1]:
                results[label] = (entry, sim, variant_tag)

    # Strategy A: direct query
    cleaned = _normalise_token(raw_ocr)
    _query(cleaned, None)

    # Strategy B: OCR-variant queries
    for variant in _apply_ocr_substitutions(cleaned):
        _query(variant, variant)

    # Sort by similarity descending, return top_n
    ranked = sorted(results.values(), key=lambda x: x[1], reverse=True)
    return ranked[:top_n]


# ---------------------------------------------------------------------------
# Stage 2: Composite Scoring
# ---------------------------------------------------------------------------

def _ocr_explained_fraction(token_lower: str, candidate_lower: str) -> float:
    """
    Estimate what fraction of the character-level edits between token and
    candidate are explainable by known OCR substitution rules.

    Returns a value in [0, 1]:  0 = nothing explained, 1 = all edits explained.
    This is used as a signal to boost confidence when OCR confusions likely
    caused the error — NOT to rewrite the token.
    """
    if token_lower == candidate_lower:
        return 1.0

    # Count character pairs that appear in our OCR confusion table
    len_max = max(len(token_lower), len(candidate_lower))
    if len_max == 0:
        return 0.0

    # Align character by character (positional), count OCR-explained pairs
    explained = 0
    total_diffs = 0
    for i, (tc, cc) in enumerate(zip(token_lower, candidate_lower)):
        if tc != cc:
            total_diffs += 1
            if (tc, cc) in _OCR_PAIRS or (cc, tc) in _OCR_PAIRS:
                explained += 1

    # Count length difference as unexplained insertions/deletions.
    # (Was accidentally removed during a scoring fix — restored here.)
    # Without this, the fraction ignores the unmatched suffix when lengths differ,
    # making it optimistically high for tokens shorter than the candidate.
    len_diff = abs(len(token_lower) - len(candidate_lower))
    total_diffs += len_diff

    if total_diffs == 0:
        return 1.0
    return min(1.0, explained / total_diffs)


def score_candidates(
    raw_ocr: str,
    candidates: List[Tuple[LexiconEntry, float, Optional[str]]],
    config: NormConfig,
) -> List[CandidateScore]:
    """
    Stage 2 — Compute a composite score for each candidate.

    composite_score = w_base * effective_base_sim
                    + w_prefix * prefix_bonus
                    + w_ocr * ocr_bonus
                    - w_len * len_penalty

    All components are in [0, 1] before weighting.
    composite_score is clamped to [0, 1].

    Weights come from config.weights so they can be tuned without touching code.

    Key design note on OCR-variant matches:
    When a match is found via an OCR substitution variant (i.e. the raw token
    was transformed before querying), RapidFuzz scores the VARIANT against the
    lexicon entry — not the original token.  This can produce base_sim=1.0 even
    though the raw OCR token is quite different from the matched drug.  We
    discount base_sim by the similarity between the original cleaned token and
    the variant to prevent over-confident OCR-hop matches, with a minimum floor
    of 0.60 so genuine OCR recoveries still score meaningfully.
    """
    cleaned = _normalise_token(raw_ocr)
    w = config.weights

    scored: List[CandidateScore] = []

    for entry, base_sim, variant_tag in candidates:
        cand_lower = entry.brand_lower

        # --- Prefix bonus ---
        # Shared prefix of length ≥3 is a strong signal (drugs rarely start
        # with the same 3+ chars by coincidence in a small lexicon).
        prefix_len = 0
        for a, b in zip(cleaned, cand_lower):
            if a == b:
                prefix_len += 1
            else:
                break
        prefix_bonus = min(1.0, prefix_len / 3.0) if prefix_len >= 2 else 0.0

        # --- Effective base similarity & OCR bonus ---
        if variant_tag is not None:
            # Match came via an OCR substitution variant.
            # Discount base_sim by similarity between original token and variant,
            # with a floor of 0.60 so valid recoveries don't disappear.
            var_len = max(len(variant_tag), len(cleaned), 1)
            matching_chars = sum(a == b for a, b in zip(cleaned, variant_tag))
            variant_sim_to_original = matching_chars / var_len
            effective_base = base_sim * max(variant_sim_to_original, 0.60)

            ocr_explained = _ocr_explained_fraction(cleaned, cand_lower)
            ocr_bonus = ocr_explained
        else:
            # Direct match — use base_sim without discount.
            effective_base = base_sim
            ocr_explained = _ocr_explained_fraction(cleaned, cand_lower)
            ocr_bonus = ocr_explained * 0.5   # smaller bonus for direct matches

        # --- Length penalty ---
        len_diff = abs(len(cleaned) - len(cand_lower))
        max_len = max(len(cleaned), len(cand_lower), 1)
        len_penalty = min(1.0, len_diff / max_len)

        # --- Composite ---
        composite = (
            w["base"] * effective_base
            + w["prefix"] * prefix_bonus
            + w["ocr"] * ocr_bonus
            - w["len_penalty"] * len_penalty
        )
        composite = max(0.0, min(1.0, composite))

        scored.append(CandidateScore(
            brand_name=entry.brand_name,
            brand_lower=cand_lower,
            generic_name=entry.generic_name,
            common_forms=entry.common_forms,
            base_similarity=round(effective_base, 4),
            prefix_bonus=round(prefix_bonus, 4),
            ocr_bonus=round(ocr_bonus, 4),
            len_penalty=round(len_penalty, 4),
            composite_score=round(composite, 4),
            ocr_variant_used=variant_tag,
        ))

    # Sort by composite score descending
    scored.sort(key=lambda x: x.composite_score, reverse=True)
    return scored[: config.top_n]


# ---------------------------------------------------------------------------
# Stage 3: Contextual Validation
# ---------------------------------------------------------------------------

_FORMULATION_KEYWORDS = {
    "tablet": ["tab", "tablet", "tabs"],
    "capsule": ["cap", "caps", "capsule"],
    "syrup": ["syp", "syrup", "syr"],
    "injection": ["inj", "injection"],
    "cream": ["cream", "cr"],
    "gel": ["gel"],
    "drops": ["drops", "drop", "gtt"],
    "inhaler": ["inhaler", "inh", "puff"],
}

_STRENGTH_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|iu|units?)\b", re.IGNORECASE
)


def validate_with_context(
    candidates: List[CandidateScore],
    context_line: str,
) -> List[CandidateScore]:
    """
    Stage 3 — Adjust scores using dosage/formulation context from the
    prescription line (if available).

    This is a LIGHTWEIGHT signal, not a hard filter:
    - Formulation match → small score boost (+0.03)
    - Formulation mismatch → small penalty (-0.02)
    - Strength extracted from context (future: cross-reference with lexicon)

    When context_line is empty (as it is when processing the benchmark CSV,
    which only has isolated word images), this stage is a no-op — candidates
    are returned unchanged.
    """
    if not context_line or not context_line.strip():
        return candidates

    ctx_lower = context_line.lower()

    # Detect formulation from context
    detected_formulations: set[str] = set()
    for form, keywords in _FORMULATION_KEYWORDS.items():
        if any(kw in ctx_lower for kw in keywords):
            detected_formulations.add(form)

    # Detect strength from context (logged but not yet used for filtering)
    strength_matches = _STRENGTH_PATTERN.findall(ctx_lower)
    # strengths = [f"{v}{u}" for v, u in strength_matches]  # reserved for future

    if not detected_formulations:
        return candidates

    adjusted: List[CandidateScore] = []
    for c in candidates:
        delta = 0.0
        candidate_forms = {f.lower() for f in c.common_forms}
        if detected_formulations & candidate_forms:
            delta += 0.03   # formulation match
        elif candidate_forms and detected_formulations:
            delta -= 0.02   # formulation mismatch

        new_score = max(0.0, min(1.0, c.composite_score + delta))
        adjusted.append(CandidateScore(
            brand_name=c.brand_name,
            brand_lower=c.brand_lower,
            generic_name=c.generic_name,
            common_forms=c.common_forms,
            base_similarity=c.base_similarity,
            prefix_bonus=c.prefix_bonus,
            ocr_bonus=c.ocr_bonus,
            len_penalty=c.len_penalty,
            composite_score=round(new_score, 4),
            ocr_variant_used=c.ocr_variant_used,
        ))

    adjusted.sort(key=lambda x: x.composite_score, reverse=True)
    return adjusted


# ---------------------------------------------------------------------------
# Stage 4: Decision
# ---------------------------------------------------------------------------

def decide(
    candidates: List[CandidateScore],
    config: NormConfig,
) -> Literal["ACCEPTED", "AMBIGUOUS", "NO_MATCH"]:
    """
    Stage 4 — Apply threshold and ambiguity-gap logic.

    Rules (applied in order):
      1. If no candidates → NO_MATCH
      2. If top score < confidence_threshold → NO_MATCH
      3. If top score ≥ threshold AND gap to 2nd candidate < ambiguity_gap
         → AMBIGUOUS  (two plausible drugs with different names)
      4. If top two candidates share the same generic name AND second score
         is above 50% of confidence_threshold → AMBIGUOUS
         (cannot distinguish between brand variants without context)
      5. Otherwise → ACCEPTED

    Note: AMBIGUOUS is intentionally returned when we're not sure — a wrong
    drug is far more dangerous than an "unclear" flag.
    """
    if not candidates:
        return "NO_MATCH"

    top_score = candidates[0].composite_score

    if top_score < config.confidence_threshold:
        return "NO_MATCH"

    if len(candidates) >= 2:
        second_score = candidates[1].composite_score
        gap = top_score - second_score

        # Rule 3: gap-based ambiguity (different drug names)
        if gap < config.ambiguity_gap:
            return "AMBIGUOUS"

        # Rule 4: same-generic-family ambiguity
        # If both top candidates map to the same generic, we can't distinguish
        # between brand variants (e.g. Montelon vs Montelar both = montelukast)
        # without additional context. Flag AMBIGUOUS when the second candidate
        # is plausibly close (above 50% of threshold).
        top_generic = (candidates[0].generic_name or "").strip().lower()
        second_generic = (candidates[1].generic_name or "").strip().lower()
        if (
            top_generic
            and top_generic == second_generic
            and second_score > config.confidence_threshold * 0.5
        ):
            return "AMBIGUOUS"

        # Rule 5: different-generic near-miss ambiguity
        # When top candidate and second candidate resolve to DIFFERENT generics,
        # and their brand names are within close edit distance (<= diff_generic_max_edit_distance),
        # flag AMBIGUOUS regardless of confidence score. A different-generic
        # substitution is a severe safety failure (wrong active ingredient administered).
        if (
            top_generic
            and second_generic
            and top_generic != second_generic
        ):
            edit_dist = Levenshtein.distance(
                candidates[0].brand_lower, candidates[1].brand_lower
            )
            if (
                edit_dist <= config.diff_generic_max_edit_distance
                and second_score > config.confidence_threshold * 0.5
            ):
                return "AMBIGUOUS"

    return "ACCEPTED"


# ---------------------------------------------------------------------------
# Stage 5: Brand → Generic Lookup
# ---------------------------------------------------------------------------

def lookup_generic(
    matched_brand_lower: str,
    lexicon: List[LexiconEntry],
) -> Optional[str]:
    """
    Stage 5 — Map a resolved brand name to its generic name.

    This is a simple dictionary lookup, completely separate from the fuzzy
    matching in Stages 1-2.  The three-stage audit trail is:
        raw OCR token → matched brand name → generic name

    Returns None if the brand is not found in the lexicon (e.g. it was
    already a generic, or the lexicon entry has no generic listed).
    """
    for entry in lexicon:
        if entry.brand_lower == matched_brand_lower:
            generic = entry.generic_name.strip()
            return generic if generic else None
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def normalize_ocr_token(
    raw_ocr: str,
    context_line: str = "",
    config: Optional[NormConfig] = None,
    lexicon: Optional[List[LexiconEntry]] = None,
) -> NormResult:
    """
    Resolve a raw PaddleOCR token to a known drug name.

    Parameters
    ----------
    raw_ocr : str
        The raw OCR output token (e.g. "Nixcil", "Indoron.", "Metro...").
        This is NEVER modified internally — all operations work on cleaned copies.

    context_line : str
        Optional: the full prescription line containing this token.
        Used in Stage 3 for formulation/dosage context signals.
        Pass "" to skip context validation (default).

    config : NormConfig
        Scoring and decision thresholds.  Defaults to NormConfig() if not
        provided.  CONFIDENCE THRESHOLDS ARE UNCALIBRATED — use
        normalization_benchmark.py --threshold-sweep to calibrate.

    lexicon : List[LexiconEntry]
        Pre-loaded lexicon.  If None, the module-level default is used
        (loaded lazily from data/indian_drug_lexicon.csv).

    Returns
    -------
    NormResult with full audit_log for debugging.
    """
    if config is None:
        config = NormConfig()
    if lexicon is None:
        lexicon = _get_default_lexicon()

    # ── Stage 1: Candidate generation ──
    raw_candidates = generate_candidates(
        raw_ocr=raw_ocr,
        lexicon=lexicon,
        top_n=max(config.top_n * 3, 10),  # over-generate; Stage 2 will trim
        scorer_name=config.scorer,
    )

    stage1_summary = [
        f"{e.brand_name}({round(sim * 100)})"
        + (f"[via:{var}]" if var else "")
        for e, sim, var in raw_candidates
    ]

    # ── Stage 2: Composite scoring ──
    scored = score_candidates(raw_ocr=raw_ocr, candidates=raw_candidates, config=config)

    stage2_scores = {c.brand_name: c.composite_score for c in scored}

    # ── Stage 3: Context validation ──
    scored = validate_with_context(candidates=scored, context_line=context_line)

    stage3_adjustments: Dict[str, float] = {}
    if context_line:
        for i, c in enumerate(scored):
            original_score = stage2_scores.get(c.brand_name, c.composite_score)
            delta = c.composite_score - original_score
            if abs(delta) > 1e-6:
                stage3_adjustments[c.brand_name] = round(delta, 4)

    # ── Stage 4: Decision ──
    status = decide(candidates=scored, config=config)

    matched_name: Optional[str] = None
    generic_name: Optional[str] = None
    confidence = scored[0].composite_score if scored else 0.0

    if status == "ACCEPTED":
        matched_name = scored[0].brand_name

    # ── Stage 5: Brand → Generic lookup ──
    stage5_generic: Optional[str] = None
    if matched_name is not None:
        stage5_generic = lookup_generic(
            matched_brand_lower=scored[0].brand_lower,
            lexicon=lexicon,
        )
        generic_name = stage5_generic

    # ── Build audit log ──
    audit_log: Dict = {
        "raw_ocr": raw_ocr,
        "cleaned_token": _normalise_token(raw_ocr),
        "ocr_variants_generated": _apply_ocr_substitutions(_normalise_token(raw_ocr)),
        "stage1_candidates": stage1_summary,
        "stage2_scores": stage2_scores,
        "stage2_detail": [
            {
                "brand": c.brand_name,
                "composite": c.composite_score,
                "base_sim": c.base_similarity,
                "prefix_bonus": c.prefix_bonus,
                "ocr_bonus": c.ocr_bonus,
                "len_penalty": c.len_penalty,
                "ocr_variant_used": c.ocr_variant_used,
            }
            for c in scored
        ],
        "stage3_context_line": context_line or None,
        "stage3_adjustments": stage3_adjustments,
        "stage4_decision": status,
        "stage4_threshold": config.confidence_threshold,
        "stage4_ambiguity_gap": config.ambiguity_gap,
        "stage5_generic": stage5_generic,
        "matched_name": matched_name,
        "confidence": round(confidence, 4),
    }

    # Log at DEBUG level for auditability
    logger.debug(
        "normalize_ocr_token | raw=%r status=%s matched=%r generic=%r conf=%.3f",
        raw_ocr, status, matched_name, generic_name, confidence,
    )
    logger.debug("audit_log: %s", audit_log)

    return NormResult(
        status=status,
        raw_ocr=raw_ocr,
        matched_name=matched_name,
        generic_name=generic_name,
        confidence=round(confidence, 4),
        candidates=scored,
        audit_log=audit_log,
    )


# ---------------------------------------------------------------------------
# Batch convenience function (for use in the benchmark script)
# ---------------------------------------------------------------------------

def normalize_batch(
    tokens: List[str],
    context_lines: Optional[List[str]] = None,
    config: Optional[NormConfig] = None,
    lexicon: Optional[List[LexiconEntry]] = None,
) -> List[NormResult]:
    """
    Normalize a list of raw OCR tokens.

    context_lines must be the same length as tokens if provided.
    """
    if lexicon is None:
        lexicon = _get_default_lexicon()
    if config is None:
        config = NormConfig()
    if context_lines is None:
        context_lines = [""] * len(tokens)

    return [
        normalize_ocr_token(
            raw_ocr=tok,
            context_line=ctx,
            config=config,
            lexicon=lexicon,
        )
        for tok, ctx in zip(tokens, context_lines)
    ]


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

def _cli_demo() -> None:
    """Quick smoke test from the command line."""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="M3 OCR Normalization — smoke test a single token"
    )
    parser.add_argument("token", help="Raw OCR token to normalize, e.g. 'Nixcil'")
    parser.add_argument("--context", default="", help="Optional context line")
    parser.add_argument(
        "--threshold", type=float, default=0.72,
        help="Confidence threshold (default: 0.72 — UNCALIBRATED)"
    )
    parser.add_argument(
        "--gap", type=float, default=0.10,
        help="Ambiguity gap (default: 0.10 — UNCALIBRATED)"
    )
    parser.add_argument(
        "--lexicon", default=None, help="Path to drug lexicon CSV"
    )
    parser.add_argument(
        "--log-level", default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Python logging level"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(name)s — %(message)s",
    )

    lexicon = load_lexicon(args.lexicon)
    cfg = NormConfig(confidence_threshold=args.threshold, ambiguity_gap=args.gap)
    result = normalize_ocr_token(args.token, context_line=args.context, config=cfg, lexicon=lexicon)

    out = {
        "status": result.status,
        "raw_ocr": result.raw_ocr,
        "matched_name": result.matched_name,
        "generic_name": result.generic_name,
        "confidence": result.confidence,
        "top_candidates": [
            {
                "brand": c.brand_name,
                "generic": c.generic_name,
                "score": c.composite_score,
                "ocr_variant_used": c.ocr_variant_used,
            }
            for c in result.candidates
        ],
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))

    if args.log_level == "DEBUG":
        print("\n── Audit Log ──")
        print(json.dumps(result.audit_log, indent=2, default=str, ensure_ascii=False))


if __name__ == "__main__":
    _cli_demo()
