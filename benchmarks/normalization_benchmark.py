#!/usr/bin/env python3
"""
benchmarks/normalization_benchmark.py
======================================
M3 Normalization Benchmark — Post-OCR Error Recovery
=====================================================

Reads the existing OCR benchmark results CSV and runs the M3 normalization
module against PaddleOCR's raw failures to measure:

  ✅ RECOVERED   — normalization correctly resolved the OCR error
  ⚠️  AMBIGUOUS   — normalization was uncertain (correct answer may be in candidates)
  ❌ WRONG       — normalization picked the WRONG drug (most critical metric)
  🔵 NO_MATCH    — normalization found no match above threshold

Usage
-----
    # Run with default settings
    python benchmarks/normalization_benchmark.py

    # Specify a different lexicon or threshold
    python benchmarks/normalization_benchmark.py \\
        --lexicon data/indian_drug_lexicon.csv \\
        --threshold 0.75

    # Sweep thresholds from 0.5 to 0.95 in steps of 0.05
    python benchmarks/normalization_benchmark.py --threshold-sweep

    # Also show full audit log for each wrong prediction
    python benchmarks/normalization_benchmark.py --show-wrong-audit

    # Custom input/output paths
    python benchmarks/normalization_benchmark.py \\
        --input  results/benchmark/ocr_benchmark_results.csv \\
        --output results/benchmark/normalization_benchmark_results.csv

Notes
-----
* The benchmark runs only on rows where paddleocr_exact == 0 (OCR failures).
  Exact-match successes are skipped because normalization is irrelevant there.
* ground_truth comparison is case-insensitive and whitespace-normalised.
* The "WRONG" count is the most important output — a confident wrong drug is
  worse than an ambiguous flag.
* Threshold defaults are UNCALIBRATED.  Use --threshold-sweep to see the
  full precision/recall trade-off and choose a medically appropriate point.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Path setup — allow running from repo root OR benchmarks/ directory
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parent.parent   # benchmarks/ -> repo root
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.modules.module3.ocr_normalization import (
    NormConfig,
    NormResult,
    load_lexicon,
    normalize_ocr_token,
)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_INPUT = str(_REPO_ROOT / "results" / "benchmark" / "ocr_benchmark_results.csv")
DEFAULT_OUTPUT = str(_REPO_ROOT / "results" / "benchmark" / "normalization_benchmark_results.csv")
DEFAULT_LEXICON = str(_REPO_ROOT / "data" / "indian_drug_lexicon.csv")
DEFAULT_THRESHOLD = 0.72   # UNCALIBRATED PLACEHOLDER
DEFAULT_GAP = 0.10         # UNCALIBRATED PLACEHOLDER


# ---------------------------------------------------------------------------
# Outcome categories
# ---------------------------------------------------------------------------
OUTCOME_RECOVERED = "RECOVERED"    # ✅
OUTCOME_AMBIGUOUS = "AMBIGUOUS"    # ⚠️
OUTCOME_WRONG = "WRONG"            # ❌
OUTCOME_NO_MATCH = "NO_MATCH"      # 🔵


def _normalise_text(s: str) -> str:
    """Case-insensitive, whitespace-normalised comparison."""
    return " ".join(str(s).strip().split()).lower()


def classify_result(result: NormResult, ground_truth: str) -> str:
    """
    Classify a NormResult against the ground truth label.

    Returns one of: RECOVERED, AMBIGUOUS, WRONG, NO_MATCH
    """
    gt_norm = _normalise_text(ground_truth)

    if result.status == "ACCEPTED":
        if _normalise_text(result.matched_name or "") == gt_norm:
            return OUTCOME_RECOVERED
        else:
            return OUTCOME_WRONG

    if result.status == "AMBIGUOUS":
        return OUTCOME_AMBIGUOUS

    # NO_MATCH
    return OUTCOME_NO_MATCH


def ambiguous_contains_gt(result: NormResult, ground_truth: str) -> bool:
    """Check whether the ground truth appears in the AMBIGUOUS candidate list."""
    gt_norm = _normalise_text(ground_truth)
    return any(
        _normalise_text(c.brand_name) == gt_norm
        for c in result.candidates
    )


# ---------------------------------------------------------------------------
# Core benchmark runner
# ---------------------------------------------------------------------------

def _detect_columns(first_row: dict, model_prefix: Optional[str] = None):
    prefixes = [model_prefix] if model_prefix else []
    prefixes += ["paddleocr", "glm", "trocr", "doctr"]
    
    pred_col = None
    exact_col = None
    cer_col = None
    model_name = model_prefix or "OCR"

    for p in prefixes:
        if p and f"{p}_pred" in first_row:
            pred_col = f"{p}_pred"
            exact_col = f"{p}_exact" if f"{p}_exact" in first_row else None
            cer_col = f"{p}_cer" if f"{p}_cer" in first_row else None
            model_name = p
            break

    if not pred_col:
        for c in ["pred", "prediction", "text"]:
            if c in first_row:
                pred_col = c
                break
        for c in ["exact", "exact_match"]:
            if c in first_row:
                exact_col = c
                break
        for c in ["cer"]:
            if c in first_row:
                cer_col = c
                break

    return pred_col, exact_col, cer_col, model_name


def run_benchmark(
    input_csv: str,
    output_csv: str,
    lexicon_path: str,
    config: NormConfig,
    show_wrong_audit: bool = False,
    verbose: bool = True,
    use_raw: bool = False,
    model: Optional[str] = None,
) -> Dict:
    """
    Run the normalization benchmark.

    Returns a summary dict with counts and percentages.
    """
    # Load lexicon once
    lexicon = load_lexicon(lexicon_path)
    if verbose:
        print(f"Lexicon: {len(lexicon)} entries from {lexicon_path}")
        print(f"Threshold: {config.confidence_threshold} (UNCALIBRATED PLACEHOLDER)")
        print(f"Ambiguity gap: {config.ambiguity_gap} (UNCALIBRATED PLACEHOLDER)")

    # Read benchmark CSV
    rows = []
    with open(input_csv, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)

    if not rows:
        sys.exit(f"ERROR: No rows found in {input_csv}")

    clean_set_path = _REPO_ROOT / "results" / "RxHandBD_Test_Label_clean.csv"
    if not use_raw and clean_set_path.exists():
        with open(clean_set_path, newline="", encoding="utf-8") as fh:
            clean_reader = csv.DictReader(fh)
            clean_filenames = {r["Images"].strip() for r in clean_reader if "Images" in r}
        total_before = len(rows)
        rows = [r for r in rows if r.get("filename", "").strip() in clean_filenames]
        if verbose:
            print(f"Dataset mode: CANONICAL CLEAN (filtered {total_before} -> {len(rows)} images using {clean_set_path.name})")
    else:
        if verbose:
            print(f"Dataset mode: RAW ({len(rows)} images, unfiltered)")

    pred_col, exact_col, cer_col, detected_model = _detect_columns(rows[0], model)
    if not pred_col:
        sys.exit(f"ERROR: Could not find prediction column in {input_csv}. Available: {list(rows[0].keys())}")

    if verbose:
        print(f"Model engine: {detected_model} (pred column: '{pred_col}')")

    # Filter to OCR failures only
    failures = []
    for r in rows:
        gt = r.get("ground_truth", "").strip()
        pred = r.get(pred_col, "").strip()
        if not gt or gt == "???":
            continue
        if not pred:
            continue
        if exact_col and r.get(exact_col) is not None:
            is_exact = str(r.get(exact_col, "0")).strip() == "1"
        else:
            is_exact = (_normalise_text(gt) == _normalise_text(pred))
        if not is_exact:
            failures.append(r)

    if verbose:
        print(f"{detected_model} failures (exact_match=0, non-empty pred, known GT): {len(failures)}")
        print()

    # Run normalization on each failure
    output_rows = []
    counts = {
        OUTCOME_RECOVERED: 0,
        OUTCOME_AMBIGUOUS: 0,
        OUTCOME_WRONG: 0,
        OUTCOME_NO_MATCH: 0,
    }
    ambiguous_gt_in_candidates = 0
    wrong_rows = []

    for row in failures:
        filename = row.get("filename", "")
        ground_truth = row.get("ground_truth", "").strip()
        raw_pred = row.get(pred_col, "").strip()
        raw_cer = row.get(cer_col, "") if cer_col else ""

        result = normalize_ocr_token(
            raw_ocr=raw_pred,
            context_line="",      # no context available in isolated word images
            config=config,
            lexicon=lexicon,
        )

        outcome = classify_result(result, ground_truth)
        counts[outcome] += 1

        if outcome == OUTCOME_AMBIGUOUS and ambiguous_contains_gt(result, ground_truth):
            ambiguous_gt_in_candidates += 1

        if outcome == OUTCOME_WRONG:
            wrong_rows.append((row, result, raw_pred))

        # Build output row
        out_row = {
            "filename": filename,
            "ground_truth": ground_truth,
            "ocr_pred": raw_pred,
            "ocr_cer": raw_cer,
            "norm_status": result.status,
            "norm_outcome": outcome,
            "norm_matched_name": result.matched_name or "",
            "norm_generic_name": result.generic_name or "",
            "norm_confidence": result.confidence,
            "norm_top_candidates": "|".join(
                f"{c.brand_name}({c.composite_score:.3f})"
                for c in result.candidates
            ),
            "ambiguous_gt_in_candidates": (
                "yes" if outcome == OUTCOME_AMBIGUOUS and ambiguous_contains_gt(result, ground_truth)
                else ("n/a" if outcome != OUTCOME_AMBIGUOUS else "no")
            ),
        }
        output_rows.append(out_row)

    # Write output CSV
    if output_csv and output_csv != os.devnull:
        os.makedirs(os.path.dirname(output_csv), exist_ok=True)
        fieldnames = list(output_rows[0].keys()) if output_rows else []
        with open(output_csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(output_rows)

    total = len(failures)
    summary = {
        "model_evaluated": detected_model,
        "total_failures": total,
        "recovered": counts[OUTCOME_RECOVERED],
        "ambiguous": counts[OUTCOME_AMBIGUOUS],
        "ambiguous_gt_in_candidates": ambiguous_gt_in_candidates,
        "wrong": counts[OUTCOME_WRONG],
        "no_match": counts[OUTCOME_NO_MATCH],
        "recovered_pct": round(100 * counts[OUTCOME_RECOVERED] / total, 2) if total else 0,
        "ambiguous_pct": round(100 * counts[OUTCOME_AMBIGUOUS] / total, 2) if total else 0,
        "wrong_pct": round(100 * counts[OUTCOME_WRONG] / total, 2) if total else 0,
        "no_match_pct": round(100 * counts[OUTCOME_NO_MATCH] / total, 2) if total else 0,
        "threshold_used": config.confidence_threshold,
        "ambiguity_gap_used": config.ambiguity_gap,
    }

    if verbose:
        _print_summary(summary, counts, total, ambiguous_gt_in_candidates, model_name=detected_model)

    if show_wrong_audit and wrong_rows:
        _print_wrong_audit(wrong_rows)

    return summary


def _print_summary(summary: Dict, counts: Dict, total: int, amb_gt_in_cands: int, model_name: str = "OCR") -> None:
    W = 65
    print("=" * W)
    print(f"  M3 NORMALIZATION BENCHMARK — {model_name} Failure Recovery")
    print("=" * W)
    print(f"  Total {model_name} failures evaluated  : {total}")
    print(f"  Confidence threshold (UNCALIBRATED): {summary['threshold_used']}")
    print(f"  Ambiguity gap (UNCALIBRATED)       : {summary['ambiguity_gap_used']}")
    print("-" * W)
    print(f"  ✅ RECOVERED   (correct resolution) : "
          f"{counts[OUTCOME_RECOVERED]:>5}  ({summary['recovered_pct']:>5.1f}%)")
    print(f"  ⚠️  AMBIGUOUS   (flagged for review)  : "
          f"{counts[OUTCOME_AMBIGUOUS]:>5}  ({summary['ambiguous_pct']:>5.1f}%)")
    print(f"     └─ GT in candidate list           : "
          f"{amb_gt_in_cands:>5}  (of {counts[OUTCOME_AMBIGUOUS]} ambiguous)")
    print(f"  🔵 NO_MATCH    (below threshold)     : "
          f"{counts[OUTCOME_NO_MATCH]:>5}  ({summary['no_match_pct']:>5.1f}%)")
    print(f"  ❌ WRONG       (confident wrong drug) : "
          f"{counts[OUTCOME_WRONG]:>5}  ({summary['wrong_pct']:>5.1f}%)")
    print("=" * W)
    if counts[OUTCOME_WRONG] == 0:
        print("  🎉 Zero wrong drug picks at this threshold.")
    else:
        print(f"  ⚠️  {counts[OUTCOME_WRONG]} wrong drug pick(s) — inspect --show-wrong-audit")
    print()


def _print_wrong_audit(wrong_rows: List) -> None:
    print("=" * 65)
    print("  WRONG PREDICTIONS — Full Audit")
    print("=" * 65)
    for row, result, raw_pred in wrong_rows:
        print(f"\n  File    : {row.get('filename', '')}")
        print(f"  GT      : {row.get('ground_truth', '')}")
        print(f"  OCR Pred: {raw_pred}")
        print(f"  Matched : {result.matched_name}  (conf={result.confidence:.3f})")
        print(f"  Generic : {result.generic_name}")
        print("  Candidates:")
        for c in result.candidates:
            print(f"    {c.brand_name:<20} score={c.composite_score:.3f}  "
                  f"(base={c.base_similarity:.3f}, prefix={c.prefix_bonus:.3f}, "
                  f"ocr={c.ocr_bonus:.3f}, len_pen={c.len_penalty:.3f})")
        print("  Audit log snippet:")
        al = result.audit_log
        print(f"    cleaned_token     : {al.get('cleaned_token')}")
        print(f"    ocr_variants      : {al.get('ocr_variants_generated', [])[:5]}")
        print(f"    stage1_candidates : {al.get('stage1_candidates', [])[:5]}")
    print()


# ---------------------------------------------------------------------------
# Threshold sweep
# ---------------------------------------------------------------------------

def run_threshold_sweep(
    input_csv: str,
    lexicon_path: str,
    thresholds: Optional[List[float]] = None,
    gap: float = 0.10,
    verbose: bool = True,
    use_raw: bool = False,
    model: Optional[str] = None,
) -> List[Dict]:
    """
    Run the benchmark at multiple threshold values and print a summary table.

    Useful for calibrating the confidence threshold against a labelled set.
    Plot the "WRONG" count and "RECOVERED" count vs threshold to find the
    operating point with acceptable false-accept rate.
    """
    if thresholds is None:
        thresholds = [round(0.50 + i * 0.05, 2) for i in range(10)]  # 0.50 to 0.95

    sweep_results = []

    # Suppress output per-run; collect summaries
    import io
    from contextlib import redirect_stdout

    for t in thresholds:
        cfg = NormConfig(confidence_threshold=t, ambiguity_gap=gap)
        buf = io.StringIO()
        with redirect_stdout(buf):
            summary = run_benchmark(
                input_csv=input_csv,
                output_csv=os.devnull,
                lexicon_path=lexicon_path,
                config=cfg,
                verbose=False,
                use_raw=use_raw,
                model=model,
            )
        sweep_results.append(summary)

    if verbose:
        model_name = sweep_results[0]["model_evaluated"] if sweep_results else "OCR"
        W = 80
        print("=" * W)
        print(f"  THRESHOLD SWEEP — M3 Normalization [{model_name}] (gap={gap:.2f}, UNCALIBRATED)")
        print("=" * W)
        print(f"  {'Threshold':>10}  {'Recovered':>10}  {'Ambiguous':>10}  "
              f"{'NoMatch':>8}  {'WRONG':>6}  {'Rec%':>6}  {'Wrong%':>7}")
        print("-" * W)
        for s in sweep_results:
            print(
                f"  {s['threshold_used']:>10.2f}  "
                f"{s['recovered']:>10}  "
                f"{s['ambiguous']:>10}  "
                f"{s['no_match']:>8}  "
                f"{s['wrong']:>6}  "
                f"{s['recovered_pct']:>6.1f}%  "
                f"{s['wrong_pct']:>6.1f}%"
            )
        print("=" * W)
        print()
        print("  NOTE: Thresholds are UNCALIBRATED.")
        print("  Choose a threshold where Wrong% is at its minimum acceptable level.")
        print("  Consider the clinical cost of each outcome:")
        print("    WRONG     — patient receives wrong drug info — HIGHEST RISK")
        print("    AMBIGUOUS — reviewer workload increases — MODERATE")
        print("    NO_MATCH  — drug not resolved — LOW RISK (stays unresolved)")
        print()

    return sweep_results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "M3 Normalization Benchmark — measures OCR error recovery on "
            "PaddleOCR failures from the RxHandBD v3 benchmark set."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python benchmarks/normalization_benchmark.py
  python benchmarks/normalization_benchmark.py --threshold 0.80
  python benchmarks/normalization_benchmark.py --threshold-sweep
  python benchmarks/normalization_benchmark.py --show-wrong-audit
  python benchmarks/normalization_benchmark.py --log-level DEBUG
        """,
    )
    parser.add_argument(
        "--input", default=DEFAULT_INPUT,
        help=f"Path to ocr_benchmark_results.csv (default: {DEFAULT_INPUT})"
    )
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT,
        help=f"Path for normalization benchmark output CSV (default: {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--lexicon", default=DEFAULT_LEXICON,
        help=f"Path to drug lexicon CSV (default: {DEFAULT_LEXICON})"
    )
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD,
        help=f"Confidence threshold (default: {DEFAULT_THRESHOLD} — UNCALIBRATED)"
    )
    parser.add_argument(
        "--gap", type=float, default=DEFAULT_GAP,
        help=f"Ambiguity gap (default: {DEFAULT_GAP} — UNCALIBRATED)"
    )
    parser.add_argument(
        "--top-n", type=int, default=3,
        help="Number of top candidates to return per token (default: 3)"
    )
    parser.add_argument(
        "--threshold-sweep", action="store_true",
        help="Run benchmark at multiple thresholds (0.50 to 0.95) for calibration"
    )
    parser.add_argument(
        "--sweep-gap", type=float, default=DEFAULT_GAP,
        help="Ambiguity gap to use during threshold sweep (default: 0.10)"
    )
    parser.add_argument(
        "--show-wrong-audit", action="store_true",
        help="Print full audit log for every WRONG prediction"
    )
    parser.add_argument(
        "--log-level", default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Python logging level (use DEBUG to see per-token audit logs)"
    )
    parser.add_argument(
        "--json-summary", action="store_true",
        help="Print summary as JSON to stdout (for scripting)"
    )
    parser.add_argument(
        "--use-raw", action="store_true",
        help="Use raw uncleaned benchmark data (1,115 rows) instead of canonical clean set (1,018 rows)"
    )
    parser.add_argument(
        "--model", choices=["paddleocr", "glm", "trocr", "doctr"], default=None,
        help="Model engine to evaluate (default: auto-detected from CSV columns)"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(name)s — %(message)s",
    )

    # Auto-adjust input if model is glm/trocr and default paddleocr input wasn't changed
    input_path = args.input
    if input_path == DEFAULT_INPUT and args.model in ("glm", "trocr"):
        alt_input = str(_REPO_ROOT / "results" / "benchmark" / "new_models_benchmark_results.csv")
        if os.path.isfile(alt_input):
            input_path = alt_input

    if not os.path.isfile(input_path):
        print(f"ERROR: Input CSV not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    if args.threshold_sweep:
        sweep_results = run_threshold_sweep(
            input_csv=input_path,
            lexicon_path=args.lexicon,
            gap=args.sweep_gap,
            use_raw=args.use_raw,
            model=args.model,
        )
        if args.json_summary:
            print(json.dumps(sweep_results, indent=2))
        return

    config = NormConfig(
        confidence_threshold=args.threshold,
        ambiguity_gap=args.gap,
        top_n=args.top_n,
    )

    summary = run_benchmark(
        input_csv=input_path,
        output_csv=args.output,
        lexicon_path=args.lexicon,
        config=config,
        show_wrong_audit=args.show_wrong_audit,
        verbose=True,
        use_raw=args.use_raw,
        model=args.model,
    )

    print(f"Detailed results written to: {args.output}")

    if args.json_summary:
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
