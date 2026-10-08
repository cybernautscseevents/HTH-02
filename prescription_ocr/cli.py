"""Command line: read a prescription image and print the drug orders as JSON.

Usage: python -m prescription_ocr IMAGE [--started-at 2026-10-08T09:00:00+05:30] [--device cpu]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from backend.stewardship.drugs import Catalog
from prescription_ocr.glm import GlmOcrEngine, GlmOcrError
from prescription_ocr.pipeline import read_prescription
from prescription_ocr.types import GlmOcrConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prescription-ocr",
        description="Read a prescription with GLM-OCR and build stewardship drug orders.",
    )
    parser.add_argument("image", type=Path)
    parser.add_argument(
        "--started-at",
        type=datetime.fromisoformat,
        default=None,
        help="ISO time the prescription started, with timezone (default: now, local time)",
    )
    parser.add_argument("--device", default="auto")
    parser.add_argument("--max-new-tokens", type=int, default=768)
    parser.add_argument("--enhance-contrast", action=argparse.BooleanOptionalAction, default=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    started_at = args.started_at or datetime.now().astimezone()
    if started_at.tzinfo is None:
        print("ERROR: --started-at needs a timezone, e.g. +05:30", file=sys.stderr)
        return 1
    engine = GlmOcrEngine(
        GlmOcrConfig(
            device=args.device,
            max_new_tokens=args.max_new_tokens,
            enhance_contrast=args.enhance_contrast,
        )
    )
    try:
        reading = read_prescription(args.image, engine, Catalog.load(), started_at=started_at)
    except (GlmOcrError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    payload = {
        "transcript": reading.ocr.text,
        "model": f"{reading.ocr.model_id}@{reading.ocr.model_revision}",
        "orders": [
            {"line": r.line_number, "reason": r.reason, **r.order.model_dump(mode="json")}
            for r in reading.readings
        ],
        "unparsed_lines": list(reading.unparsed_lines),
        "warnings": list(reading.warnings),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0
