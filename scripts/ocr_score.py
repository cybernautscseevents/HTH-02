#!/usr/bin/env python3
"""Compare pipeline results (scripts/ocr_real_eval.py) with hand-made ground truth.

Each ground-truth line is paired with the pipeline order from the same image whose raw text is
most similar (one-to-one, similarity >= 0.45). Pairings are printed so a person can check them;
the numbers are only as good as that check.

Ground truth columns (data/ocr_test/*/ground_truth.csv): image, gt_id, written, kind
(antibiotic | non_antibiotic | none), expected_generic, dose_mg, freq_per_day (number, or
weekly/stat/sos), route, duration (days, or text such as "1 month"), reading, notes.

Optional ground-truth column `labelled`: "all" (default) when every drug line of the image is
listed, or "antibiotics" when only its antibiotic lines are; false-line counts skip the latter.

Usage: python scripts/ocr_score.py data/ocr_test/mirage [engine]
    With an engine name the results are read from <folder>/results/<engine>/results.jsonl.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

MIN_SIMILARITY = 0.45
NAME_CLOSE = 0.8
_FORM_WORDS = frozenset(
    "tab tabs tablet cap caps capsule syp syrup susp suspension inj injection eye ear drops "
    "drop tb rx".split()
)


def name_tokens(text: str) -> list[str]:
    """Letters-only words of the drug name: the text before the first digit, forms removed."""
    head = re.split(r"\d", text.lower(), maxsplit=1)[0]
    words = re.findall(r"[a-z]+", head)
    return [w for w in words if w not in _FORM_WORDS and len(w) > 1]


def name_match(written: str, read: str) -> str:
    """exact: every word of the true name is in the read line; close: similar; wrong."""
    truth, got = name_tokens(written), name_tokens(read)
    if truth and set(truth) <= set(got):
        return "exact"
    ratio = SequenceMatcher(None, "".join(truth), "".join(got)).ratio()
    return "close" if truth and ratio >= NAME_CLOSE else "wrong"


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def _number(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def expected_duration(value: str) -> float | None:
    """Days for "5" or "8 weeks"; None (not expressible in days by the parser) for months."""
    if not value:
        return None
    if (n := _number(value)) is not None:
        return n
    match = re.fullmatch(r"(\d+)\s*weeks?", value.strip())
    return float(match.group(1)) * 7 if match else None


def field_result(expected, got) -> str:
    if expected is None:
        return "ok_empty" if got is None else "wrong_value"
    if got is None:
        return "missed"
    return "ok" if abs(float(expected) - float(got)) < 1e-6 else "wrong_value"


def pair(gt_rows: list[dict], orders: list[dict]) -> list[tuple[dict, dict | None, float]]:
    scored = sorted(
        (
            (SequenceMatcher(None, _norm(g["written"]), _norm(o["raw_line"])).ratio(), gi, oi)
            for gi, g in enumerate(gt_rows)
            for oi, o in enumerate(orders)
        ),
        reverse=True,
    )
    used_g, used_o, best = set(), set(), {}
    for score, gi, oi in scored:
        if score < MIN_SIMILARITY or gi in used_g or oi in used_o:
            continue
        used_g.add(gi)
        used_o.add(oi)
        best[gi] = (oi, score)
    return [
        (g, orders[best[gi][0]] if gi in best else None, best.get(gi, (None, 0.0))[1])
        for gi, g in enumerate(gt_rows)
    ]


def main(folder: Path, engine: str | None = None) -> int:
    results_dir = folder / "results" / engine if engine else folder / "results"
    results = {
        r["image"]: r
        for r in map(json.loads, (results_dir / "results.jsonl").read_text().splitlines())
    }
    with (folder / "ground_truth.csv").open(encoding="utf-8") as f:
        truth = list(csv.DictReader(f))

    images = sorted({t["image"] for t in truth})
    tally: Counter = Counter()
    unmatched_orders = []
    print("image | gt | kind | written -> pipeline raw_line | status generic | dose freq route dur")
    for image in images:
        gt_rows = [t for t in truth if t["image"] == image and t["kind"] != "none"]
        if "error" in results[image]:
            tally["image_errors"] += 1
        orders = results[image].get("orders", [])
        pairs = pair(gt_rows, orders)
        matched_ids = {id(o) for _, o, _ in pairs if o is not None}
        fully_labelled = all(t.get("labelled", "all") == "all" for t in truth if t["image"] == image)
        for o in orders:
            if id(o) in matched_ids:
                continue
            unmatched_orders.append((image, o["raw_line"]))
            if fully_labelled:
                tally["all|false_lines"] += 1
                tally["all|wrong_drug_accepted"] += o["norm_status"] == "ACCEPTED"
        tally["uncertain_lines_reported"] += len(results[image].get("uncertain_lines", []))
        for g, o, score in pairs:
            scopes = ["all"] + (["abx"] if g["kind"] == "antibiotic" else [])

            def bump(metric: str, scopes=scopes) -> None:
                for scope in scopes:
                    tally[f"{scope}|{metric}"] += 1

            tally["gt_lines"] += 1
            tally[f"gt_{g['kind']}"] += 1
            bump("gt_lines")
            if o is None:
                tally["not_detected"] += 1
                bump("not_detected")
                print(f"{image} | {g['gt_id']} | {g['kind']} | {g['written']} -> NOT DETECTED")
                continue
            tally["detected"] += 1
            bump("detected")
            bump(f"name_{name_match(g['written'], o['raw_line'])}")
            status, generic = o["norm_status"], o["generic"]
            if g["kind"] == "antibiotic":
                if status == "ACCEPTED" and generic == g["expected_generic"]:
                    outcome = "antibiotic_correct"
                elif status == "ACCEPTED":
                    outcome = "antibiotic_wrong_drug"
                else:
                    outcome = "antibiotic_needs_confirmation"
            else:
                accepted = status == "ACCEPTED"
                outcome = f"non_antibiotic_{'accepted' if accepted else 'unidentified'}"
            tally[outcome] += 1
            if outcome == "antibiotic_wrong_drug" or outcome == "non_antibiotic_accepted":
                bump("wrong_drug_accepted")
            if outcome == "antibiotic_correct":
                bump("identified_correct")
            tally[f"R0_{o['findings'].get('R0_IDENTIFIED')}"] += 1

            freq_text = g["freq_per_day"].strip().lower()
            checks = {
                "dose": field_result(_number(g["dose_mg"]), o["dose_mg"]),
                "freq": field_result(_number(freq_text), o["freq_per_day"]),
                "route": (
                    "ok" if g["route"] and g["route"] == o["route"]
                    else "ok_empty" if not g["route"] and o["route"] is None
                    else "missed" if o["route"] is None else "wrong_value"
                ),
                "duration": field_result(expected_duration(g["duration"]), o["duration_days"]),
            }
            for name, result in checks.items():
                tally[f"{name}_{result}"] += 1
                bump(f"{name}_{result}")
            print(
                f"{image} | {g['gt_id']} | {g['kind']} | {g['written']} -> {o['raw_line']!r} "
                f"(sim {score:.2f}) | {status} {generic} | "
                + " ".join(f"{k}:{v}" for k, v in checks.items())
            )

    print("\nPipeline orders not paired with any ground-truth line (possible false detections):")
    for image, line in unmatched_orders:
        print(f"  {image}: {line!r}")
    print("\nTotals:")
    for key in sorted(tally):
        print(f"  {key}: {tally[key]}")
    print_summary(tally)
    return 0


def print_summary(tally: Counter) -> None:
    """Headline metrics for comparing engines: all drug lines, then antibiotics only."""
    for scope, title in (("all", "ALL DRUG LINES"), ("abx", "ANTIBIOTIC LINES ONLY")):
        n = tally[f"{scope}|gt_lines"]

        def t(metric: str, scope=scope) -> int:
            return tally[f"{scope}|{metric}"]

        print(f"\nSUMMARY - {title} ({n} hand-labelled lines)")
        print(f"  detected as an order:        {t('detected')}/{n}   missed: {t('not_detected')}")
        print(f"  drug name exact / close:     {t('name_exact')} / {t('name_close')} of {n}")
        if scope == "abx":
            print(f"  identified correctly:        {t('identified_correct')}/{n}")
        for field in ("dose", "freq", "route", "duration"):
            ok = t(f"{field}_ok") + t(f"{field}_ok_empty")
            print(
                f"  {field:<9} correct {t(f'{field}_ok')}  missed {t(f'{field}_missed')}  "
                f"wrong {t(f'{field}_wrong_value')}  (correct empty {t(f'{field}_ok_empty')}; "
                f"right {ok}/{t('detected')})"
            )
        print(f"  wrong drug accepted:         {t('wrong_drug_accepted')}")
    print(
        "\nFALSE MEDICINE LINES (orders matching no label, fully labelled images): "
        f"{tally['all|false_lines']}"
    )
    print(f"UNCERTAIN LINES REPORTED (not turned into orders): {tally['uncertain_lines_reported']}")


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else None))
