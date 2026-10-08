"""Prescription image reading for the stewardship engine.

GLM-OCR transcription, image preparation and transcript parsing come from PranamB21's GLM-OCR
prescription reader (branch `ocr`, commit 5237e32). Drug identity is decided only by the
stewardship drug catalog, never by OCR similarity scores.
"""

from prescription_ocr.glm import GlmOcrEngine, GlmOcrError
from prescription_ocr.orders import OrderReading, PrescriptionReading, read_orders
from prescription_ocr.pipeline import read_prescription
from prescription_ocr.types import GlmOcrConfig, OcrResult

__all__ = [
    "GlmOcrConfig",
    "GlmOcrEngine",
    "GlmOcrError",
    "OcrResult",
    "OrderReading",
    "PrescriptionReading",
    "read_orders",
    "read_prescription",
]
