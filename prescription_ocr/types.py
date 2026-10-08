"""Public result and configuration types for prescription OCR."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class GlmOcrConfig:
    device: str = "auto"
    max_new_tokens: int = 768
    enhance_contrast: bool = True

    def __post_init__(self) -> None:
        if self.device != "auto" and self.device != "cpu" and not self.device.startswith("cuda"):
            raise ValueError("device must be auto, cpu, or cuda[:index]")
        if not 64 <= self.max_new_tokens <= 4096:
            raise ValueError("max_new_tokens must be between 64 and 4096")


@dataclass(frozen=True)
class OcrResult:
    raw_text: str
    text: str
    model_id: str
    model_revision: str
    device: str
    dtype: str
    elapsed_seconds: float
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> Mapping[str, Any]:
        return asdict(self)
