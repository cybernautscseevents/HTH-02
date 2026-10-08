"""Prescription image -> GLM-OCR transcript -> DrugOrders for evaluate_episode()."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol

from backend.stewardship.drugs import Catalog
from prescription_ocr.orders import PrescriptionReading, read_orders
from prescription_ocr.types import OcrResult

ENGINES = ("glm", "qwen")


class OcrEngine(Protocol):
    def transcribe(self, image: str | Path) -> OcrResult: ...


def read_prescription(
    image: str | Path,
    engine: OcrEngine,
    catalog: Catalog,
    *,
    started_at: datetime,
    uncertain_as_orders: bool = False,
) -> PrescriptionReading:
    """Transcribe a prescription image and turn its medicine lines into DrugOrders."""
    return read_orders(
        engine.transcribe(image),
        catalog,
        started_at=started_at,
        uncertain_as_orders=uncertain_as_orders,
    )


def build_engine(name: str, *, device: str = "auto") -> OcrEngine:
    """The OCR engine called `name`. Qwen-VL reads its model and quantization from HC03_QWEN_*."""
    if name == "glm":
        from prescription_ocr.glm import GlmOcrEngine
        from prescription_ocr.types import GlmOcrConfig

        return GlmOcrEngine(GlmOcrConfig(device=device))
    if name == "qwen":
        from prescription_ocr.qwen import QwenVlConfig, QwenVlEngine

        return QwenVlEngine(QwenVlConfig(device=device))
    raise ValueError(f"unknown OCR engine {name!r}; choose from {', '.join(ENGINES)}")
