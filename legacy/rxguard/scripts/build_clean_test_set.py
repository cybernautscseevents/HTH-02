#!/usr/bin/env python3
"""
build_clean_test_set.py
=======================
Builds the canonical clean test label dataset for Kshema OCR benchmarking.

Provenance:
- Base dataset: RxHandBD-ML / Test_Label.csv (1,115 images, P0001.jpg - P1115.jpg)
- Exclusions: results/rxhandbd_known_bad_rows.csv (97 rows, after blind-audit
  reinstatement of 13 rows from an earlier 110-row exclusion list)
  * 74 rows from 4 multi-image shift clusters (drift caused by untracked crops)
  * 23 rows from isolated mislabeled images / ground-truth typos
- Output: results/RxHandBD_Test_Label_clean.csv (1,018 images)
"""

from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_TEST_LABEL_CSV = (
    PROJECT_ROOT
    / "RxHandBD A Handwritten Prescription Word Image Dat"
    / "RxHandBD-ML"
    / "Test_Label.csv"
)
BAD_ROWS_CSV = PROJECT_ROOT / "results" / "rxhandbd_known_bad_rows.csv"
CLEAN_TEST_LABEL_CSV = PROJECT_ROOT / "results" / "RxHandBD_Test_Label_clean.csv"


def build_clean_dataset():
    if not RAW_TEST_LABEL_CSV.exists():
        raise FileNotFoundError(f"Missing raw test labels at {RAW_TEST_LABEL_CSV}")
    if not BAD_ROWS_CSV.exists():
        raise FileNotFoundError(f"Missing bad rows manifest at {BAD_ROWS_CSV}")

    raw_df = pd.read_csv(RAW_TEST_LABEL_CSV)
    raw_df.columns = raw_df.columns.str.strip()
    raw_df["Images"] = raw_df["Images"].str.strip()
    raw_df["Text"] = raw_df["Text"].str.strip()

    bad_df = pd.read_csv(BAD_ROWS_CSV)
    excluded_files = set(bad_df["filename"].str.strip())

    clean_df = raw_df[~raw_df["Images"].isin(excluded_files)].copy()
    clean_df = clean_df.reset_index(drop=True)

    CLEAN_TEST_LABEL_CSV.parent.mkdir(parents=True, exist_ok=True)
    clean_df.to_csv(CLEAN_TEST_LABEL_CSV, index=False)

    print("=================================================================")
    print("  CANONICAL CLEAN DATASET GENERATION SUMMARY")
    print("=================================================================")
    print(f"  Raw test set size       : {len(raw_df)} images")
    print(f"  Excluded bad rows       : {len(excluded_files)} images")
    print(f"  Canonical clean set size: {len(clean_df)} images")
    print(f"  Clean dataset written to: {CLEAN_TEST_LABEL_CSV}")
    print("=================================================================")
    return clean_df


if __name__ == "__main__":
    build_clean_dataset()
