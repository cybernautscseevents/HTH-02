"""Pinned GLM-OCR engine for full prescription images."""

from __future__ import annotations

import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from prescription_ocr.image import prepare_image
from prescription_ocr.transcript import clean_glm_transcript
from prescription_ocr.types import GlmOcrConfig, OcrResult

GLM_MODEL_ID = "zai-org/GLM-OCR"
GLM_REVISION = "2e85a62840ccac27daa451df36c736c4636b8628"
PRESCRIPTION_PROMPT = (
    "Transcribe every visible line in this prescription exactly as written. "
    "Preserve line breaks and medicine strengths. Output only the transcription, "
    "with no explanation, markdown, diagnosis, or inferred text."
)


class GlmOcrError(RuntimeError):
    """Raised when GLM-OCR cannot initialize or transcribe an image."""


class GlmOcrEngine:
    def __init__(
        self,
        config: GlmOcrConfig | None = None,
        *,
        processor: Any = None,
        model: Any = None,
    ) -> None:
        self.config = config or GlmOcrConfig()
        self.processor = processor
        self.model = model
        self.device = "unloaded"
        self.dtype = "unloaded"

    def load(self) -> None:
        if self.processor is not None and self.model is not None:
            if self.device == "unloaded":
                self.device, self.dtype = "injected", "injected"
            return
        try:
            import torch
            from transformers import AutoProcessor, GlmOcrForConditionalGeneration
        except ImportError as exc:
            raise GlmOcrError(
                "GLM-OCR dependencies are missing; install the application requirements"
            ) from exc

        requested = self.config.device
        if requested == "auto":
            requested = "cuda:0" if torch.cuda.is_available() else "cpu"
        if requested.startswith("cuda") and not torch.cuda.is_available():
            raise GlmOcrError(f"requested device {requested} but CUDA is unavailable")
        torch_dtype = torch.bfloat16 if requested.startswith("cuda") else torch.float32
        try:
            self.processor = AutoProcessor.from_pretrained(GLM_MODEL_ID, revision=GLM_REVISION)
            self.model = GlmOcrForConditionalGeneration.from_pretrained(
                GLM_MODEL_ID,
                revision=GLM_REVISION,
                torch_dtype=torch_dtype,
                device_map=requested,
            )
            self.model.eval()
        except Exception as exc:
            raise GlmOcrError(f"failed to load pinned GLM-OCR: {exc}") from exc
        self.device = requested
        self.dtype = str(torch_dtype).removeprefix("torch.")

    def transcribe(self, image: str | Path | Any) -> OcrResult:
        try:
            from PIL import Image
        except ImportError as exc:
            raise GlmOcrError("Pillow is required for image input") from exc
        if isinstance(image, (str, Path)):
            path = Path(image)
            if not path.is_file():
                raise GlmOcrError(f"image not found: {path}")
            try:
                with Image.open(path) as source:
                    opened = source.copy()
            except Exception as exc:
                raise GlmOcrError(f"cannot read image {path}: {exc}") from exc
        elif isinstance(image, Image.Image):
            opened = image
        else:
            raise GlmOcrError("image must be a filesystem path or PIL image")
        opened, preprocessing_warnings = prepare_image(
            opened, enhance_contrast=self.config.enhance_contrast
        )

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
                    **inputs,
                    max_new_tokens=self.config.max_new_tokens,
                    do_sample=False,
                    temperature=None,
                    top_p=None,
                )
            prompt_length = inputs["input_ids"].shape[1]
            generated = output_ids[:, prompt_length:]
            raw = self.processor.decode(generated[0], skip_special_tokens=True).strip()
        except Exception as exc:
            raise GlmOcrError(f"GLM-OCR inference failed: {exc}") from exc
        cleaned = clean_glm_transcript(raw)
        warnings = list(preprocessing_warnings)
        if not cleaned:
            warnings.append("GLM-OCR returned no text")
        return OcrResult(
            raw_text=raw,
            text=cleaned,
            model_id=GLM_MODEL_ID,
            model_revision=GLM_REVISION,
            device=self.device,
            dtype=self.dtype,
            elapsed_seconds=round(time.perf_counter() - started, 6),
            warnings=tuple(warnings),
        )
