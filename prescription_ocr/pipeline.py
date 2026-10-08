"""Prescription image -> GLM-OCR transcript -> DrugOrders for evaluate_episode()."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol

from backend.stewardship.drugs import Catalog
from prescription_ocr.orders import PrescriptionReading, read_orders
from prescription_ocr.types import OcrResult


class OcrEngine(Protocol):
    def transcribe(self, image: str | Path) -> OcrResult: ...


def read_prescription(
    image: str | Path, engine: OcrEngine, catalog: Catalog, *, started_at: datetime
) -> PrescriptionReading:
    """Transcribe a prescription image and turn its medicine lines into DrugOrders."""
    return read_orders(engine.transcribe(image), catalog, started_at=started_at)
