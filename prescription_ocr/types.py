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
class ReadLine:
    """One medicine line as a vision model read it. Values are text exactly as written, or None.

    Nothing here is normalized or interpreted: the drug name goes to the stewardship catalog and
    the directions go through the same deterministic parsers as a plain transcript.
    """

    as_written: str
    dose: str | None = None
    frequency: str | None = None
    route: str | None = None
    duration: str | None = None
    legible: bool = True

    @property
    def text(self) -> str:
        """The line as read: the written name plus any direction text not already in it."""
        written = self.as_written.casefold()
        extras = (
            v
            for v in (self.dose, self.frequency, self.route, self.duration)
            if v and v.casefold() not in written
        )
        return " ".join((self.as_written, *extras))


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
    # Set by engines that return structured medicine lines (Qwen-VL); None for plain transcripts.
    lines: tuple[ReadLine, ...] | None = None

    def to_dict(self) -> Mapping[str, Any]:
        return asdict(self)
