"""SYNTHETIC DEMO DATA: verify the demo prescription texts, then render them as typed images.

Run from the repository root, after build_cases.py has written the JSON files:
    python data/demo_synthetic/make_images.py              # verify text, then render images/
    python data/demo_synthetic/make_images.py --ocr glm    # also OCR the rendered images (glm|qwen)

1. The exact page text in prescriptions.json goes through read_orders (transcript -> parser ->
   Catalog) and must give the expected DrugOrder fields, with the two columns of a row read either
   on one line or on two. Its diagnosis line must be the diagnosis of cases.json.
2. The orders' raw text, with the patient, diagnosis and culture of cases.json, goes through
   POST /api/evaluate and must give exactly the non-PASS findings listed in cases.json.
3. Only then are the images drawn. Nothing here changes or loads anything into the application.
"""

import argparse
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from backend.stewardship.drugs import Catalog  # noqa: E402
from backend.stewardship.intake import diagnosis_line  # noqa: E402
from prescription_ocr.orders import read_orders  # noqa: E402
from prescription_ocr.types import OcrResult  # noqa: E402

FIELDS = ("generic", "dose_mg", "freq_per_day", "route", "duration_days")
FONT_DIR = Path("/usr/share/fonts/truetype/noto")
T0 = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


def page_text(page: dict, case: dict, split_columns: bool) -> str:
    rows = [*page["header"]]
    for style, *cols in case["rows"]:
        if style == "gap":
            continue
        rows += cols if split_columns else ["    ".join(cols)]
    return "\n".join([*rows, *page["footer"]])


def order_fields(reading) -> list[dict]:
    plain = lambda v: v.value if hasattr(v, "value") else v  # noqa: E731 - Route enum -> "PO"
    return [{f: plain(getattr(r.order, f)) for f in FIELDS} for r in reading.readings]


def check_parse(catalog: Catalog, page: dict, case: dict, request: dict) -> list[str]:
    errors = []
    if diagnosis_line(page_text(page, case, False)) != request["diagnosis_text"]:
        errors.append("diagnosis line does not match cases.json")
    for split in (False, True):
        text = page_text(page, case, split)
        reading = read_orders(
            OcrResult(text, text, "typed-text", "-", "cpu", "-", 0.0), catalog, started_at=T0
        )
        got = order_fields(reading)
        if got != case["expected_orders"]:
            errors.append(f"parse ({'split' if split else 'joined'} columns): got {got}")
        if any(r.order.norm_status.value != "ACCEPTED" for r in reading.readings):
            errors.append("parse: an order was not identified")
    return errors


def check_rules(
    client, catalog: Catalog, page: dict, case: dict, request: dict, expected: dict
) -> list[str]:
    text = page_text(page, case, False)
    reading = read_orders(
        OcrResult(text, text, "typed-text", "-", "cpu", "-", 0.0), catalog, started_at=T0
    )
    body = {**request, "prescription": "\n".join(r.order.raw_text for r in reading.readings)}
    resp = client.post("/api/evaluate", json=body)
    if resp.status_code != 200:
        return [f"evaluate: HTTP {resp.status_code} {resp.text}"]
    report = resp.json()
    errors = [] if report["status"] == expected["status"] else [f"status {report['status']}"]
    drugs = {o["id"]: o["generic"] for o in report["orders"]}
    got = sorted(
        (i["rule_id"], drugs.get(i["order_id"]) or "", i["outcome"])
        for i in report["items"]
        if i["outcome"] != "PASS"
    )
    want = sorted((f["rule"], f["drug"] or "", f["outcome"]) for f in expected["findings"])
    if got != want:
        errors.append(f"findings: expected {want}, got {got}")
    return errors


def render(page: dict, case: dict, out: Path) -> None:
    font = lambda name, size: ImageFont.truetype(str(FONT_DIR / name), size)  # noqa: E731
    regular, bold = font("NotoSans-Regular.ttf", 28), font("NotoSans-Bold.ttf", 28)
    width, height, margin = 1240, 1754, 100
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    ink, muted, accent = (20, 24, 32), (110, 116, 128), (24, 70, 130)

    d.text(
        (width / 2, 110),
        page["header"][0],
        font=font("NotoSans-Bold.ttf", 38),
        fill=accent,
        anchor="mm",
    )
    d.text(
        (width / 2, 165),
        page["header"][1],
        font=font("NotoSans-Regular.ttf", 26),
        fill=muted,
        anchor="mm",
    )
    d.line((margin, 210, width - margin, 210), fill=accent, width=3)

    def labelled(x: int, y: int, text: str, size_font=(regular, bold)) -> None:
        label, sep, value = text.partition(":")
        if not sep:
            d.text((x, y), text, font=size_font[0], fill=ink)
            return
        d.text((x, y), label + ":", font=size_font[1], fill=ink)
        d.text(
            (x + d.textlength(label + ": ", font=size_font[1]), y),
            value.strip(),
            font=size_font[0],
            fill=ink,
        )

    y = 250
    for style, *cols in case["rows"]:
        if style == "gap":
            y += 28
        elif style == "field":
            labelled(margin, y, cols[0])
            if len(cols) > 1:
                labelled(width // 2 + 40, y, cols[1])
            y += 48
        elif style == "rx":
            d.line((margin, y, width - margin, y), fill=(210, 214, 222), width=2)
            d.text((margin, y + 18), cols[0], font=font("NotoSans-Bold.ttf", 52), fill=accent)
            y += 100
        elif style == "med":
            d.text((margin + 30, y), cols[0], font=font("NotoSans-Regular.ttf", 34), fill=ink)
            y += 60

    d.text((width - margin, height - 260), page["footer"][0], font=regular, fill=ink, anchor="ra")
    d.line((margin, height - 110, width - margin, height - 110), fill=(210, 214, 222), width=2)
    d.text(
        (width / 2, height - 75),
        page["footer"][1],
        font=font("NotoSans-Regular.ttf", 20),
        fill=muted,
        anchor="mm",
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)


def check_ocr(engine_name: str, catalog: Catalog, cases: list[dict]) -> int:
    from prescription_ocr.pipeline import build_engine

    engine, failures = build_engine(engine_name), 0
    for case in cases:
        result = engine.transcribe(HERE / case["image"])
        got = order_fields(read_orders(result, catalog, started_at=T0))
        ok = got == case["expected_orders"]
        failures += not ok
        print(f"{case['case_id']} OCR[{engine_name}] {'OK' if ok else 'MISMATCH'} {got}")
        if not ok:
            print("  transcript:", result.text.replace("\n", " | "))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ocr", choices=("glm", "qwen"))
    args = parser.parse_args()

    from fastapi.testclient import TestClient

    from backend.stewardship.api import create_app
    from backend.stewardship.audit import JsonlAuditLog
    from backend.stewardship.renal import RenalDosing
    from backend.stewardship.rulepack import YamlRulePack
    from backend.stewardship.service import StewardshipService

    data = json.loads((HERE / "prescriptions.json").read_text())
    known = {c["case_id"]: c for c in json.loads((HERE / "cases.json").read_text())["cases"]}
    catalog = Catalog.load()
    with tempfile.TemporaryDirectory() as tmp:
        service = StewardshipService(
            catalog=catalog,
            rulepack=YamlRulePack(),
            renal=RenalDosing.load(),
            audit=JsonlAuditLog(Path(tmp) / "audit.jsonl"),
        )
        client = TestClient(create_app(service))
        failed = False
        for case in data["cases"]:
            ref = known[case["case_id"]]
            errors = check_parse(catalog, data["page"], case, ref["request"]) + check_rules(
                client, catalog, data["page"], case, ref["request"], ref["expected"]
            )
            print(f"{case['case_id']} text: {'OK' if not errors else '; '.join(errors)}")
            failed |= bool(errors)
    if failed:
        print("Verification failed; no images were drawn.")
        return 1
    for case in data["cases"]:
        render(data["page"], case, HERE / case["image"])
        print("drew", case["image"])
    return 1 if args.ocr and check_ocr(args.ocr, catalog, data["cases"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
