#!/usr/bin/env python3
"""
ocr_benchmark.py — Raw OCR Engine Comparison on RxHandBD v3 Test Set
====================================================================

Compares PaddleOCR and docTR (PARSeq) recognition accuracy on pre-cropped
handwritten medical prescription word images.  No normalization, spell-check,
or fuzzy matching — raw OCR output only.

Usage
-----
    # Run both engines (default paths)
    python benchmarks/ocr_benchmark.py

    # Run a single engine
    python benchmarks/ocr_benchmark.py --engines paddleocr
    python benchmarks/ocr_benchmark.py --engines doctr

    # Custom paths
    python benchmarks/ocr_benchmark.py \
        --dataset-dir "RxHandBD A Handwritten Prescription Word Image Dat/RxHandBD-ML" \
        --output-dir  results/benchmark

Output
------
1. Console summary table: Engine × CER / WER / Exact-Match Accuracy
2. ``ocr_benchmark_results.csv`` with per-image results
3. Worst-20 failures per engine printed to console

CSV Columns
-----------
filename           : Image filename (e.g. P0001.jpg)
ground_truth       : Ground-truth label from Test_Label.csv
paddleocr_pred     : Raw PaddleOCR prediction (empty if engine skipped)
doctr_pred         : Raw docTR / PARSeq prediction (empty if engine skipped)
paddleocr_cer      : Character Error Rate for PaddleOCR (0.0–1.0+)
doctr_cer          : Character Error Rate for docTR (0.0–1.0+)
paddleocr_wer      : Word Error Rate for PaddleOCR
doctr_wer          : Word Error Rate for docTR
paddleocr_exact    : 1 if case-insensitive exact match, else 0 (PaddleOCR)
doctr_exact        : 1 if case-insensitive exact match, else 0 (docTR)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Silence noisy library warnings before imports pull them in
# ---------------------------------------------------------------------------
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
# Disable docTR / HuggingFace progress bars that compete with tqdm
os.environ.setdefault("DOCTR_MULTIPROCESSING_DISABLE", "TRUE")
warnings.filterwarnings("ignore", category=UserWarning)

import cv2
import numpy as np
import pandas as pd
from tqdm import tqdm

# jiwer imported lazily in metric helpers (allows --help without install)
_jiwer_cer = None
_jiwer_wer = None


def _ensure_jiwer():
    global _jiwer_cer, _jiwer_wer
    if _jiwer_cer is None:
        try:
            from jiwer import cer as _cer, wer as _wer
            _jiwer_cer = _cer
            _jiwer_wer = _wer
        except ImportError:
            sys.exit(
                "ERROR: jiwer is required.  Install with:  pip install jiwer"
            )

# ═══════════════════════════════════════════════════════════════════════════
# Configuration (overridable via CLI)
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_DATASET_DIR = os.path.join(
    "RxHandBD A Handwritten Prescription Word Image Dat", "RxHandBD-ML"
)
DEFAULT_OUTPUT_DIR = os.path.join("results", "benchmark")
AVAILABLE_ENGINES = ("paddleocr", "doctr")

# ═══════════════════════════════════════════════════════════════════════════
# Metric helpers
# ═══════════════════════════════════════════════════════════════════════════


def _normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace to a single space and strip."""
    return " ".join(text.split())


def compute_cer(reference: str, hypothesis: str) -> float:
    """Character Error Rate via jiwer. Returns 0.0 for empty reference match."""
    _ensure_jiwer()
    ref = _normalize_whitespace(reference)
    hyp = _normalize_whitespace(hypothesis)
    if not ref and not hyp:
        return 0.0
    if not ref:
        return 1.0  # insertion-only → CER capped at 1.0
    return _jiwer_cer(ref, hyp)


def compute_wer(reference: str, hypothesis: str) -> float:
    """Word Error Rate via jiwer."""
    _ensure_jiwer()
    ref = _normalize_whitespace(reference)
    hyp = _normalize_whitespace(hypothesis)
    if not ref and not hyp:
        return 0.0
    if not ref:
        return 1.0
    return _jiwer_wer(ref, hyp)


def exact_match(reference: str, hypothesis: str) -> int:
    """Case-insensitive, whitespace-normalised exact match → 1/0."""
    return int(
        _normalize_whitespace(reference).lower()
        == _normalize_whitespace(hypothesis).lower()
    )


# ═══════════════════════════════════════════════════════════════════════════
# Engine 1: PaddleOCR
# ═══════════════════════════════════════════════════════════════════════════

_paddle_engine: Optional[object] = None


def _get_paddle_engine():
    """Lazy-initialise PaddleOCR TextRecognition (recognition only, no detection)."""
    global _paddle_engine
    if _paddle_engine is None:
        from paddleocr import TextRecognition

        _paddle_engine = TextRecognition()
    return _paddle_engine


def run_paddleocr(image_path: str) -> str:
    """
    Run PaddleOCR recognition on a single pre-cropped word image.
    Returns the raw recognised text (empty string on failure).
    """
    engine = _get_paddle_engine()
    try:
        results = engine.predict(image_path)
        if results:
            first = results[0]
            if isinstance(first, dict):
                return str(first.get("rec_text", "")).strip()
            elif hasattr(first, "rec_text"):
                return str(first.rec_text).strip()
            elif hasattr(first, "__getitem__") and "rec_text" in first:
                return str(first["rec_text"]).strip()
        return ""
    except Exception as e:
        print(f"  [PaddleOCR ERROR] {image_path}: {e}", file=sys.stderr)
        return ""


# ═══════════════════════════════════════════════════════════════════════════
# Engine 2: docTR + PARSeq
# ═══════════════════════════════════════════════════════════════════════════

_doctr_predictor: Optional[object] = None


def _get_doctr_predictor():
    """Lazy-initialise docTR recognition-only predictor with PARSeq."""
    global _doctr_predictor
    if _doctr_predictor is None:
        from doctr.models import recognition_predictor

        _doctr_predictor = recognition_predictor(
            arch="parseq", pretrained=True
        )
    return _doctr_predictor


def run_doctr(image_path: str) -> str:
    """
    Run docTR PARSeq recognition on a single pre-cropped word image.
    Returns the raw recognised text (empty string on failure).
    """
    predictor = _get_doctr_predictor()
    try:
        img = cv2.imread(image_path)
        if img is None:
            print(f"  [docTR ERROR] Cannot read: {image_path}", file=sys.stderr)
            return ""
        # docTR recognition_predictor expects a list of numpy arrays (BGR ok)
        result = predictor([img])
        # result is a list of (word_value, confidence) tuples
        if result and len(result) > 0:
            word, _conf = result[0]
            return str(word).strip()
        return ""
    except Exception as e:
        print(f"  [docTR ERROR] {image_path}: {e}", file=sys.stderr)
        return ""


# ═══════════════════════════════════════════════════════════════════════════
# Engine dispatcher
# ═══════════════════════════════════════════════════════════════════════════

ENGINE_RUNNERS = {
    "paddleocr": run_paddleocr,
    "doctr": run_doctr,
}

# ═══════════════════════════════════════════════════════════════════════════
# Main benchmark
# ═══════════════════════════════════════════════════════════════════════════


def load_test_labels(dataset_dir: str, use_raw: bool = False) -> pd.DataFrame:
    """Load and validate the test label CSV. Defaults to canonical clean set unless use_raw=True."""
    clean_csv_path = os.path.join("results", "RxHandBD_Test_Label_clean.csv")
    raw_csv_path = os.path.join(dataset_dir, "Test_Label.csv")

    if not use_raw and os.path.isfile(clean_csv_path):
        csv_path = clean_csv_path
        dataset_mode = "CANONICAL CLEAN (1,018 images, known bad rows excluded)"
    else:
        csv_path = raw_csv_path
        dataset_mode = "RAW (unfiltered 1,115 images with known alignment issues)"

    if not os.path.isfile(csv_path):
        sys.exit(f"ERROR: Label file not found at {csv_path}")

    df = pd.read_csv(csv_path, dtype=str).dropna(subset=["Images", "Text"])
    df.columns = df.columns.str.strip()
    df["Images"] = df["Images"].str.strip()
    df["Text"] = df["Text"].str.strip()

    image_dir = os.path.join(dataset_dir, "Test_Set")
    if not os.path.isdir(image_dir):
        sys.exit(f"ERROR: Test_Set directory not found at {image_dir}")

    # Verify a sample of images exist
    sample = df["Images"].iloc[:5].tolist()
    for fname in sample:
        fpath = os.path.join(image_dir, fname)
        if not os.path.isfile(fpath):
            sys.exit(f"ERROR: Sample image missing: {fpath}")

    print(f"✓ Loaded {len(df)} test samples [{dataset_mode}] from {csv_path}")
    return df


def run_benchmark(
    dataset_dir: str,
    output_dir: str,
    engines: list[str],
    sample_n: Optional[int] = None,
    use_raw: bool = False,
) -> None:
    """Run the OCR benchmark."""

    df = load_test_labels(dataset_dir, use_raw=use_raw)
    if sample_n is not None and sample_n > 0:
        df = df.iloc[:sample_n].copy()
        print(f"  [Subsampled to first {len(df)} images]")
    image_dir = os.path.join(dataset_dir, "Test_Set")
    os.makedirs(output_dir, exist_ok=True)

    # Warm up selected engines
    print("\n── Warming up engines ──")
    for eng_name in engines:
        t0 = time.time()
        print(f"  Loading {eng_name}...", end=" ", flush=True)
        # Run a dummy prediction to trigger model download / load
        dummy_path = os.path.join(image_dir, df["Images"].iloc[0])
        ENGINE_RUNNERS[eng_name](dummy_path)
        print(f"ready ({time.time() - t0:.1f}s)")

    # ----- Per-image inference -----
    records: list[dict] = []

    print(f"\n── Running OCR on {len(df)} images ──")
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Benchmarking"):
        fname = row["Images"]
        gt = row["Text"]
        img_path = os.path.join(image_dir, fname)

        rec: dict = {"filename": fname, "ground_truth": gt}

        for eng_name in AVAILABLE_ENGINES:
            if eng_name in engines:
                pred = ENGINE_RUNNERS[eng_name](img_path)
            else:
                pred = ""

            rec[f"{eng_name}_pred"] = pred
            rec[f"{eng_name}_cer"] = compute_cer(gt, pred) if eng_name in engines else None
            rec[f"{eng_name}_wer"] = compute_wer(gt, pred) if eng_name in engines else None
            rec[f"{eng_name}_exact"] = exact_match(gt, pred) if eng_name in engines else None

        records.append(rec)

    results_df = pd.DataFrame(records)

    # ----- Save per-image CSV -----
    csv_out = os.path.join(output_dir, "ocr_benchmark_results.csv")
    results_df.to_csv(csv_out, index=False)
    print(f"\n✓ Per-image results saved to {csv_out}")

    # ----- Aggregate summary -----
    print("\n" + "=" * 65)
    print("  OCR BENCHMARK SUMMARY — RxHandBD v3 Test Set")
    print("=" * 65)
    print(f"  {'Engine':<14} {'CER':>8} {'WER':>8} {'Exact-Match':>13}  {'N':>5}")
    print("-" * 65)

    for eng_name in engines:
        cer_col = f"{eng_name}_cer"
        wer_col = f"{eng_name}_wer"
        exact_col = f"{eng_name}_exact"

        mean_cer = results_df[cer_col].mean()
        mean_wer = results_df[wer_col].mean()
        acc = results_df[exact_col].mean() * 100

        print(
            f"  {eng_name:<14} {mean_cer:>7.4f}  {mean_wer:>7.4f}  "
            f"{acc:>11.2f}%  {len(results_df):>5}"
        )

    print("=" * 65)

    # ----- Worst 20 failures per engine -----
    for eng_name in engines:
        cer_col = f"{eng_name}_cer"
        pred_col = f"{eng_name}_pred"

        worst = (
            results_df.nlargest(20, cer_col)[
                ["filename", "ground_truth", pred_col, cer_col]
            ]
            .reset_index(drop=True)
        )

        print(f"\n── Worst 20 failures: {eng_name} ──")
        print(f"  {'#':>3}  {'File':<12} {'GT':<20} {'Pred':<20} {'CER':>6}")
        print("  " + "-" * 64)
        for i, r in worst.iterrows():
            gt_display = str(r["ground_truth"])[:18]
            pred_display = str(r[pred_col])[:18]
            print(
                f"  {i + 1:>3}  {r['filename']:<12} {gt_display:<20} "
                f"{pred_display:<20} {r[cer_col]:>6.3f}"
            )
    print()


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="OCR benchmark: PaddleOCR vs docTR/PARSeq on RxHandBD v3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dataset-dir",
        default=DEFAULT_DATASET_DIR,
        help=f"Path to RxHandBD-ML directory (default: {DEFAULT_DATASET_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for output CSV (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--engines",
        nargs="+",
        default=list(AVAILABLE_ENGINES),
        choices=AVAILABLE_ENGINES,
        help="Which engines to run (default: both)",
    )
    parser.add_argument(
        "--sample-n",
        type=int,
        default=None,
        help="Run on only the first N samples (e.g. for smoke testing)",
    )
    parser.add_argument(
        "--use-raw",
        action="store_true",
        help="Use unfiltered raw Test_Label.csv (1,115 images) instead of canonical clean set",
    )
    args = parser.parse_args()

    print("OCR Benchmark — RxHandBD v3 Test Set")
    print(f"  Dataset  : {args.dataset_dir}")
    print(f"  Output   : {args.output_dir}")
    print(f"  Engines  : {', '.join(args.engines)}")
    print(f"  Use Raw  : {args.use_raw}")
    if args.sample_n:
        print(f"  Sample N : {args.sample_n}")

    run_benchmark(
        dataset_dir=args.dataset_dir,
        output_dir=args.output_dir,
        engines=args.engines,
        sample_n=args.sample_n,
        use_raw=args.use_raw,
    )


if __name__ == "__main__":
    main()
