#!/usr/bin/env python3
"""Run real prescription images through the full pipeline and record every step.

image -> OCR engine (GLM-OCR transcript, or Qwen-VL structured lines)
      -> line parser / field parsers -> Catalog.normalize -> DrugOrder -> evaluate_episode()

Nothing here changes how the pipeline decides. Two inputs the images do not provide are fixed
and reported as such:
- Rule pack: no guideline syndromes (Person 3's rule pack is not merged yet), so indication,
  dose and duration rules return CANNOT_ASSESS "No infection syndrome recorded".
- Patient: an adult placeholder with unknown allergy status and no weight or creatinine, because
  patient details are not extracted from the image.

Writes <out>/results.jsonl (one record per image) and <out>/orders.csv (one row per order).
If <images>/../ground_truth.csv exists, scripts/ocr_score.py compares the results with it.

Usage (needs requirements-ocr.txt installed):
    python scripts/ocr_real_eval.py data/ocr_test/mirage/images --out data/ocr_test/mirage/results
    python scripts/ocr_real_eval.py IMAGES --out OUT --engine qwen   # HC03_QWEN_MODEL, HC03_QWEN_QUANT
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.stewardship.drugs import Catalog  # noqa: E402
from backend.stewardship.episode import evaluate_episode  # noqa: E402
from backend.stewardship.renal import RenalDosing  # noqa: E402
from backend.stewardship.schemas import (  # noqa: E402
    AllergyStatus,
    Episode,
    Patient,
    Setting,
    Sex,
    SyndromeRule,
    Trigger,
)
from prescription_ocr.glm import GlmOcrError  # noqa: E402
from prescription_ocr.orders import read_orders  # noqa: E402
from prescription_ocr.pipeline import ENGINES, OcrEngine, build_engine  # noqa: E402
from prescription_ocr.qwen import QwenOcrError, parse_qwen_output  # noqa: E402
from prescription_ocr.types import OcrResult  # noqa: E402

STARTED_AT = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}


class NoGuidelineRulePack:
    """No syndromes: guideline-dependent rules return CANNOT_ASSESS instead of using test data."""

    version = "none"

    def syndrome(self, code: str) -> SyndromeRule | None:
        return None


PLACEHOLDER_PATIENT = Patient(
    id="unknown", age_years=40, sex=Sex.F, allergy_status=AllergyStatus.UNKNOWN
)


class ReplayEngine:
    """Re-reads saved Qwen answers (results.jsonl `raw_output`) so a policy can be re-scored
    without running the model again."""

    model_id, model_revision, device, dtype = "replay", "", "cpu", "replay"

    def __init__(self, results: Path) -> None:
        rows = map(json.loads, (results / "results.jsonl").read_text().splitlines())
        self.saved = {r["image"]: r for r in rows if "raw_output" in r}
        self.dtype = "replay"

    def transcribe(self, image: Path) -> OcrResult:
        saved = self.saved[image.name]
        lines, warnings = parse_qwen_output(saved["raw_output"])
        text = "\n".join(line.text for line in lines)
        return OcrResult(
            saved["raw_output"], text, saved["model"].split("@")[0], saved["model"].split("@")[-1],
            saved["device"], "replay", saved["ocr_seconds"], warnings, lines,
        )


def evaluate_image(
    path: Path,
    engine: OcrEngine,
    catalog: Catalog,
    renal: RenalDosing,
    uncertain_as_orders: bool = False,
) -> dict:
    record: dict = {"image": path.name}
    try:
        ocr = engine.transcribe(path)
    except (GlmOcrError, QwenOcrError) as exc:
        return record | {"error": str(exc)}
    reading = read_orders(
        ocr, catalog, started_at=STARTED_AT, uncertain_as_orders=uncertain_as_orders
    )
    episode = Episode(
        id=path.stem,
        patient=PLACEHOLDER_PATIENT,
        setting=Setting.OPD,
        syndrome_code=None,
        started_at=STARTED_AT,
        orders=reading.orders,
    )
    evaluation = evaluate_episode(
        episode,
        now=STARTED_AT,
        trigger=Trigger.NEW_PRESCRIPTION,
        rulepack=NoGuidelineRulePack(),
        catalog=catalog,
        renal=renal,
    )
    findings = {}
    for f in evaluation.findings:
        findings.setdefault(f.order_id or "episode", {})[f.rule_id] = f.outcome.value
    orders = []
    for r in reading.readings:
        o = r.order
        orders.append(
            {
                "order_id": o.id,
                "line_number": r.line_number,
                "raw_line": r.raw_line,
                "norm_status": o.norm_status.value,
                "generic": o.generic,
                "brand": o.brand,
                "candidates": list(o.norm_candidates),
                "reason": r.reason,
                "dose_mg": o.dose_mg,
                "freq_per_day": o.freq_per_day,
                "route": o.route.value if o.route else None,
                "duration_days": o.duration_days,
                "is_antibiotic": bool(o.generic and catalog.is_antibiotic(o.generic)),
                "findings": findings.get(o.id, {}),
            }
        )
    return record | {
        "ocr_seconds": ocr.elapsed_seconds,
        "model": f"{ocr.model_id}@{ocr.model_revision}",
        "device": ocr.device,
        "transcript": ocr.text,
        "raw_output": ocr.raw_text,
        "orders": orders,
        "unparsed_lines": list(reading.unparsed_lines),
        "uncertain_lines": list(reading.uncertain_lines),
        "warnings": list(reading.warnings),
        "evaluation_status": evaluation.status.value,
        "episode_findings": findings.get("episode", {}),
    }


def _peak_gpu_mb() -> float | None:
    try:
        import torch
    except ImportError:
        return None
    if not torch.cuda.is_available():
        return None
    return round(torch.cuda.max_memory_allocated() / 2**20)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("images", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--engine", choices=ENGINES, default="glm")
    parser.add_argument(
        "--uncertain-as-orders",
        action="store_true",
        help="Qwen lines marked not legible become orders that always need drug confirmation",
    )
    parser.add_argument(
        "--replay", type=Path, help="re-read the saved Qwen answers in this results folder"
    )
    parser.add_argument("--device", default="auto")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    paths = sorted(p for p in args.images.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    paths = paths[: args.limit] if args.limit else paths
    args.out.mkdir(parents=True, exist_ok=True)
    engine = ReplayEngine(args.replay) if args.replay else build_engine(args.engine, device=args.device)
    catalog, renal = Catalog.load(), RenalDosing.load()

    started = time.perf_counter()
    records = []
    for i, path in enumerate(paths, start=1):
        record = evaluate_image(path, engine, catalog, renal, args.uncertain_as_orders)
        records.append(record)
        n = len(record.get("orders", []))
        print(f"[{i}/{len(paths)}] {path.name}: {n} order(s) {record.get('error', '')}", flush=True)

    with (args.out / "results.jsonl").open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    with (args.out / "orders.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["image", "order_id", "raw_line", "norm_status", "generic", "candidates", "dose_mg",
             "freq_per_day", "route", "duration_days", "is_antibiotic", "R0", "R2", "R4"]
        )
        for record in records:
            for o in record.get("orders", []):
                writer.writerow(
                    [record["image"], o["order_id"], o["raw_line"], o["norm_status"], o["generic"],
                     "|".join(o["candidates"]), o["dose_mg"], o["freq_per_day"], o["route"],
                     o["duration_days"], o["is_antibiotic"], o["findings"].get("R0_IDENTIFIED"),
                     o["findings"].get("R2_AWARE"), o["findings"].get("R4_RENAL")]
                )
    elapsed = time.perf_counter() - started
    seconds = [r["ocr_seconds"] for r in records if "ocr_seconds" in r]
    summary = {
        "engine": args.engine,
        "uncertain_as_orders": args.uncertain_as_orders,
        "model": next((r["model"] for r in records if "model" in r), None),
        "dtype": getattr(engine, "dtype", None),
        "images": len(records),
        "errors": sum("error" in r for r in records),
        "mean_ocr_seconds": round(sum(seconds) / len(seconds), 2) if seconds else None,
        "max_ocr_seconds": max(seconds, default=None),
        "total_seconds_with_load": round(elapsed, 1),
        "peak_gpu_allocated_mb": _peak_gpu_mb(),
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
