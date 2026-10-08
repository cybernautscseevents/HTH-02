"""Qwen vision-language engine: prescription image -> structured medicine lines.

The model only reads. It returns each medicine line as JSON text (name as written, dose,
frequency, route, duration, legible); it never normalizes a drug name or judges a prescription.
Names go to the stewardship catalog and directions go through the deterministic parsers in
prescription_ocr.orders, exactly as for a GLM-OCR transcript.

The model, quantization and image size come from the environment so a different Qwen-VL can be
tried without code changes (see QwenVlConfig). Text that cannot be parsed raises QwenOutputError:
it is never turned into an empty prescription.
"""

from __future__ import annotations

import json
import os
import re
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from prescription_ocr.image import prepare_image
from prescription_ocr.types import OcrResult, ReadLine

DEFAULT_MODEL_ID = "Qwen/Qwen2.5-VL-3B-Instruct"
QUANTIZATIONS = ("4bit", "8bit", "none")
MAX_LINES = 40
MAX_FIELD_CHARS = 160

PRESCRIPTION_PROMPT = """\
You are reading a photographed prescription. Your only job is to copy the prescribed MEDICINES \
exactly as written. Do not judge whether any medicine is appropriate and do not explain.

Return ONLY one JSON object, nothing before or after it:
{"medicines": [{"as_written": "...", "dose": "...", "frequency": "...", "route": "...", \
"duration": "...", "legible": true}]}

Rules:
- One entry per medicine, in the order written. Never merge two medicines into one entry.
- "as_written": the medicine line exactly as written: dosage form (Tab, Cap, Syp, Inj ...), \
the drug or brand name with its spelling as you see it, and any strength. Do not correct, \
complete, translate or normalize the name. Do not replace a brand with its generic name.
- "dose": the strength or amount written for one dose (for example "500 mg"), else null.
- "frequency": how often, as written (for example "BD", "TDS", "1-0-1", "q8h", "SOS"), else null.
- "route": only if written (for example "IV", "IM", "PO", "oral"), else null.
- "duration": only if written (for example "x 5 days", "for 1 week"), else null.
- Never invent a value. If a field is not written or you are not sure, use null.
- "legible": false if you cannot confidently read the line as a medicine; still copy what you \
can see into "as_written".
- Ignore patient details, diagnosis, clinical notes, investigations and advice. \
List only medicines.
- If there are no medicines, return {"medicines": []}.
"""

_NULL_WORDS = frozenset(
    {"", "null", "none", "n/a", "na", "nil", "-", "--", "?", "unknown", "unclear", "illegible"}
)
_FENCE = re.compile(r"```(?:json)?", re.IGNORECASE)
_FLAT_OBJECT = re.compile(r"\{[^{}]*\}")


class QwenOcrError(RuntimeError):
    """Raised when the Qwen engine cannot initialize or run."""


class QwenOutputError(QwenOcrError):
    """The model answered, but not with medicine lines we can read."""


@dataclass(frozen=True)
class QwenVlConfig:
    """Qwen-VL settings. Unset values come from the environment, then from the defaults.

    HC03_QWEN_MODEL        Hugging Face model id (default Qwen/Qwen2.5-VL-3B-Instruct)
    HC03_QWEN_REVISION     optional model revision to pin
    HC03_QWEN_QUANT        4bit (default), 8bit or none; 4bit/8bit need bitsandbytes and CUDA
    HC03_QWEN_MAX_PIXELS   image area cap; more pixels read finer writing but use more VRAM
    """

    model_id: str = field(default_factory=lambda: os.getenv("HC03_QWEN_MODEL", DEFAULT_MODEL_ID))
    revision: str | None = field(default_factory=lambda: os.getenv("HC03_QWEN_REVISION") or None)
    quantization: str = field(default_factory=lambda: os.getenv("HC03_QWEN_QUANT", "4bit"))
    max_pixels: int = field(
        default_factory=lambda: int(os.getenv("HC03_QWEN_MAX_PIXELS", str(1280 * 28 * 28)))
    )
    min_pixels: int = 256 * 28 * 28
    device: str = "auto"
    max_new_tokens: int = 1024
    enhance_contrast: bool = True

    def __post_init__(self) -> None:
        if self.quantization not in QUANTIZATIONS:
            raise ValueError(f"quantization must be one of {', '.join(QUANTIZATIONS)}")
        if self.device != "auto" and self.device != "cpu" and not self.device.startswith("cuda"):
            raise ValueError("device must be auto, cpu, or cuda[:index]")
        if not 64 <= self.max_new_tokens <= 4096:
            raise ValueError("max_new_tokens must be between 64 and 4096")
        if not 0 < self.min_pixels <= self.max_pixels:
            raise ValueError("pixel limits must satisfy 0 < min_pixels <= max_pixels")


def _text_or_none(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        value = f"{value:g}"
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return None if text.casefold() in _NULL_WORDS else text


def _legible(value: Any) -> bool:
    """A missing or unrecognised flag counts as not legible: never assume confidence."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"true", "yes"}
    return False


def _entries(payload: Any) -> list[Any] | None:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("medicines", "medications", "lines", "drugs"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return None


def _load_entries(raw: str) -> tuple[list[Any], list[str]]:
    """Medicine entries from the model's answer, tolerating fences and truncated output."""
    text = _FENCE.sub("", raw).strip()
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start >= 0:
        try:
            payload, _ = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError:
            payload = None
        entries = _entries(payload)
        if entries is not None:
            return entries, []
    # Truncated or malformed: keep only complete flat objects that look like medicine lines.
    salvaged = []
    for match in _FLAT_OBJECT.finditer(text):
        try:
            obj = json.loads(match.group())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "as_written" in obj:
            salvaged.append(obj)
    if not salvaged:
        raise QwenOutputError("Model output is not valid medicine JSON.")
    return salvaged, [
        f"Model output was malformed or cut off; recovered {len(salvaged)} complete line(s) only."
    ]


def parse_qwen_output(raw: str) -> tuple[tuple[ReadLine, ...], tuple[str, ...]]:
    """Parse the model's JSON answer into medicine lines, plus warnings about anything dropped.

    Raises QwenOutputError when no medicine list can be recovered at all. Entries without a
    usable "as_written" are dropped with a warning; unknown or empty fields become None.
    """
    entries, warnings = _load_entries(raw)
    lines: list[ReadLine] = []
    dropped = 0
    for entry in entries:
        written = _text_or_none(entry.get("as_written")) if isinstance(entry, dict) else None
        if written is None or len(written) > MAX_FIELD_CHARS:
            dropped += 1
            continue
        line = ReadLine(
            as_written=written,
            dose=_text_or_none(entry.get("dose")),
            frequency=_text_or_none(entry.get("frequency")),
            route=_text_or_none(entry.get("route")),
            duration=_text_or_none(entry.get("duration")),
            legible=_legible(entry.get("legible")),
        )
        if line not in lines:  # a model stuck in a loop repeats the same entry
            lines.append(line)
    if dropped:
        warnings.append(f"{dropped} entr{'y' if dropped == 1 else 'ies'} without a readable name.")
    if len(lines) > MAX_LINES:
        warnings.append(f"Model returned {len(lines)} lines; kept the first {MAX_LINES}.")
        lines = lines[:MAX_LINES]
    return tuple(lines), tuple(warnings)


class QwenVlEngine:
    """Reads a prescription image with a Qwen vision-language model (OcrEngine interface)."""

    def __init__(
        self,
        config: QwenVlConfig | None = None,
        *,
        processor: Any = None,
        model: Any = None,
    ) -> None:
        self.config = config or QwenVlConfig()
        self.processor = processor
        self.model = model
        self.device = "unloaded"
        self.dtype = "unloaded"
        self.revision = self.config.revision or "unpinned"

    def load(self) -> None:
        if self.processor is not None and self.model is not None:
            if self.device == "unloaded":
                self.device, self.dtype = "injected", "injected"
            return
        try:
            import torch
            from transformers import AutoModelForImageTextToText, AutoProcessor
        except ImportError as exc:
            raise QwenOcrError(
                "Qwen-VL dependencies are missing; install requirements-ocr.txt"
            ) from exc

        cfg = self.config
        requested = cfg.device
        if requested == "auto":
            requested = "cuda:0" if torch.cuda.is_available() else "cpu"
        if requested.startswith("cuda") and not torch.cuda.is_available():
            raise QwenOcrError(f"requested device {requested} but CUDA is unavailable")
        quantization = cfg.quantization
        if quantization != "none" and not requested.startswith("cuda"):
            raise QwenOcrError(
                f"{quantization} quantization needs a CUDA device; set HC03_QWEN_QUANT=none "
                "to run unquantized on CPU (slow)"
            )
        dtype = torch.bfloat16 if requested.startswith("cuda") else torch.float32
        kwargs: dict[str, Any] = {"dtype": dtype, "device_map": requested}
        if cfg.revision:
            kwargs["revision"] = cfg.revision
        if quantization != "none":
            try:
                from transformers import BitsAndBytesConfig
            except ImportError as exc:
                raise QwenOcrError("bitsandbytes is required for quantized Qwen-VL") from exc
            kwargs["quantization_config"] = (
                BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=dtype,
                    bnb_4bit_use_double_quant=True,
                    llm_int8_skip_modules=["lm_head"],
                )
                if quantization == "4bit"
                else BitsAndBytesConfig(load_in_8bit=True, llm_int8_skip_modules=["lm_head"])
            )
        try:
            self.processor = AutoProcessor.from_pretrained(
                cfg.model_id,
                revision=cfg.revision,
                min_pixels=cfg.min_pixels,
                max_pixels=cfg.max_pixels,
            )
            self.model = AutoModelForImageTextToText.from_pretrained(cfg.model_id, **kwargs)
            self.model.eval()
        except Exception as exc:
            raise QwenOcrError(f"failed to load {cfg.model_id}: {exc}") from exc
        commit = getattr(self.model.config, "_commit_hash", None)
        self.revision = cfg.revision or commit or "unpinned"
        self.device = requested
        self.dtype = f"{str(dtype).removeprefix('torch.')}+{quantization}"

    def transcribe(self, image: str | Path | Any) -> OcrResult:
        try:
            from PIL import Image
        except ImportError as exc:
            raise QwenOcrError("Pillow is required for image input") from exc
        if isinstance(image, (str, Path)):
            path = Path(image)
            if not path.is_file():
                raise QwenOcrError(f"image not found: {path}")
            try:
                with Image.open(path) as source:
                    opened = source.copy()
            except Exception as exc:
                raise QwenOcrError(f"cannot read image {path}: {exc}") from exc
        elif isinstance(image, Image.Image):
            opened = image
        else:
            raise QwenOcrError("image must be a filesystem path or PIL image")
        opened, warnings = prepare_image(opened, enhance_contrast=self.config.enhance_contrast)

        self.load()
        started = time.perf_counter()
        try:
            try:
                import torch

                inference_context = torch.no_grad()
            except ImportError:
                if self.device != "injected":
                    raise
                inference_context = nullcontext()

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": opened},
                        {"type": "text", "text": PRESCRIPTION_PROMPT},
                    ],
                }
            ]
            inputs = self.processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_tensors="pt",
                return_dict=True,
            )
            model_device = getattr(self.model, "device", None)
            if model_device is not None:
                inputs = {
                    key: value.to(model_device) if hasattr(value, "to") else value
                    for key, value in inputs.items()
                }
            with inference_context:
                output_ids = self.model.generate(
                    **inputs, max_new_tokens=self.config.max_new_tokens, do_sample=False
                )
            prompt_length = inputs["input_ids"].shape[1]
            raw = self.processor.decode(
                output_ids[0][prompt_length:], skip_special_tokens=True
            ).strip()
        except Exception as exc:
            raise QwenOcrError(f"Qwen-VL inference failed: {exc}") from exc
        elapsed = round(time.perf_counter() - started, 6)

        lines, parse_warnings = parse_qwen_output(raw)
        warnings = [*warnings, *parse_warnings]
        if not lines:
            warnings.append("Qwen-VL reported no medicines")
        return OcrResult(
            raw_text=raw,
            text="\n".join(line.text for line in lines),
            model_id=self.config.model_id,
            model_revision=self.revision,
            device=self.device,
            dtype=self.dtype,
            elapsed_seconds=elapsed,
            warnings=tuple(warnings),
            lines=lines,
        )
