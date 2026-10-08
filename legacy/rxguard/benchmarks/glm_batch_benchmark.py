#!/usr/bin/env python3
"""Measure native CPU batching throughput for zai-org/GLM-OCR.

This is deliberately a diagnostic only. It does not change the OCR pipeline,
normalization, or any confidence threshold.

Run from the repository root:
    ./venv/bin/python benchmarks/glm_batch_benchmark.py

The benchmark uses the same first ten rows selected by ``--smoke`` in
``new_models_benchmark.py`` and the same GLM-OCR loader (CPU, float32,
``device_map="cpu"``). It first proves that the public batched chat-template
path can generate two images with padding and an attention mask. If that
preflight fails, it exits instead of attempting any workaround.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import psutil
import torch
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import benchmarks.new_models_benchmark as benchmark


BATCH_SIZES = (1, 2, 4, 8)
SMOKE_IMAGE_COUNT = 10
PROMPT = (
    "Please transcribe the text in this image exactly as written. "
    "Output ONLY the transcribed text with no additional explanation or formatting."
)


class BatchUnsupportedError(RuntimeError):
    """The supported processor/model API did not produce a valid batch."""


class RssSampler:
    """Sample process RSS while image preparation and generation are running."""

    def __init__(self, interval_seconds: float = 0.02) -> None:
        self.process = psutil.Process(os.getpid())
        self.interval_seconds = interval_seconds
        self.before_bytes = 0
        self.after_bytes = 0
        self.peak_bytes = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def _rss(self) -> int:
        return self.process.memory_info().rss

    def _sample(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.peak_bytes = max(self.peak_bytes, self._rss())

    def start(self) -> None:
        self.before_bytes = self._rss()
        self.peak_bytes = self.before_bytes
        self._thread.start()

    def stop(self) -> None:
        self.after_bytes = self._rss()
        self.peak_bytes = max(self.peak_bytes, self.after_bytes)
        self._stop.set()
        self._thread.join()


@dataclass(frozen=True)
class Prediction:
    cleaned_text: str
    raw_text: str
    token_ids: tuple[int, ...]


@dataclass(frozen=True)
class BatchResult:
    batch_size: int
    total_seconds: float
    rss_before_mb: float
    rss_after_mb: float
    peak_rss_mb: float
    peak_vram_mb: float
    predictions: list[Prediction]


def mb(byte_count: int) -> float:
    return byte_count / (1024 * 1024)


def make_conversation(image_path: Path) -> list[dict[str, Any]]:
    """Build exactly the GLM-OCR message used by run_glm_ocr()."""
    with Image.open(image_path) as image:
        rgb_image = image.convert("RGB")
    return [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": rgb_image},
                {"type": "text", "text": PROMPT},
            ],
        }
    ]


def prepare_batched_inputs(image_paths: Sequence[Path]):
    """Use the public batched apply_chat_template API; do not reshape internals."""
    conversations = [make_conversation(path) for path in image_paths]
    inputs = benchmark._glm_processor.apply_chat_template(
        conversations,
        add_generation_prompt=True,
        tokenize=True,
        padding=True,
        return_tensors="pt",
        return_dict=True,
    )

    input_ids = inputs.get("input_ids")
    attention_mask = inputs.get("attention_mask")
    if input_ids is None or input_ids.ndim != 2:
        raise BatchUnsupportedError("apply_chat_template did not return 2-D input_ids for a chat batch")
    if input_ids.shape[0] != len(image_paths):
        raise BatchUnsupportedError(
            f"chat batch dimension is {input_ids.shape[0]}, expected {len(image_paths)}"
        )
    if attention_mask is None or attention_mask.shape != input_ids.shape:
        raise BatchUnsupportedError(
            "padding=True did not return an attention_mask aligned with input_ids: "
            f"input_ids={tuple(input_ids.shape)}, "
            f"attention_mask={None if attention_mask is None else tuple(attention_mask.shape)}"
        )
    if "pixel_values" not in inputs or "image_grid_thw" not in inputs:
        raise BatchUnsupportedError(
            "the processor did not return pixel_values and image_grid_thw for the image chat batch"
        )
    return inputs


def trim_continuation_tokens(token_ids: torch.Tensor) -> tuple[int, ...]:
    """Drop generation padding only; preserve the real generated token sequence."""
    values = token_ids.tolist()
    pad_token_id = benchmark._glm_processor.tokenizer.pad_token_id
    while values and values[-1] == pad_token_id:
        values.pop()
    return tuple(values)


def generate_batch(image_paths: Sequence[Path]) -> list[Prediction]:
    """Generate one OCR continuation per image through the standard HF API."""
    inputs = prepare_batched_inputs(image_paths)
    device = benchmark._glm_model.device
    inputs = {k: (v.to(device) if hasattr(v, "to") else v) for k, v in inputs.items()}
    prompt_width = inputs["input_ids"].shape[1]

    with torch.inference_mode():
        output_ids = benchmark._glm_model.generate(
            **inputs,
            max_new_tokens=64,
            do_sample=False,
            temperature=None,
            top_p=None,
        )

    if output_ids.ndim != 2 or output_ids.shape[0] != len(image_paths):
        raise BatchUnsupportedError(
            f"generate returned {tuple(output_ids.shape)} for a batch of {len(image_paths)} images"
        )
    if output_ids.shape[1] < prompt_width:
        raise BatchUnsupportedError(
            f"generate output width {output_ids.shape[1]} is shorter than prompt width {prompt_width}"
        )

    predictions: list[Prediction] = []
    for output_ids_for_image in output_ids:
        continuation = trim_continuation_tokens(output_ids_for_image[prompt_width:])
        raw_text = benchmark._glm_processor.decode(continuation, skip_special_tokens=True).strip()
        cleaned_text, _ = benchmark.strip_vlm_prose(raw_text)
        predictions.append(Prediction(cleaned_text, raw_text, continuation))
    return predictions


def run_timed_batch_size(image_paths: Sequence[Path], batch_size: int) -> BatchResult:
    sampler = RssSampler()
    predictions: list[Prediction] = []
    is_cuda = torch.cuda.is_available() and str(benchmark._glm_model.device).startswith("cuda")
    if is_cuda:
        torch.cuda.reset_peak_memory_stats()
    sampler.start()
    started = time.perf_counter()
    try:
        for offset in range(0, len(image_paths), batch_size):
            predictions.extend(generate_batch(image_paths[offset : offset + batch_size]))
    finally:
        elapsed = time.perf_counter() - started
        sampler.stop()
    peak_vram_mb = mb(torch.cuda.max_memory_allocated()) if is_cuda else 0.0
    return BatchResult(
        batch_size=batch_size,
        total_seconds=elapsed,
        rss_before_mb=mb(sampler.before_bytes),
        rss_after_mb=mb(sampler.after_bytes),
        peak_rss_mb=mb(sampler.peak_bytes),
        peak_vram_mb=peak_vram_mb,
        predictions=predictions,
    )


def exact_match_counts(
    baseline: Sequence[Prediction], candidate: Sequence[Prediction]
) -> tuple[int, int]:
    token_matches = sum(a.token_ids == b.token_ids for a, b in zip(baseline, candidate))
    text_matches = sum(a.cleaned_text == b.cleaned_text for a, b in zip(baseline, candidate))
    return token_matches, text_matches


def run_batch_preflight(image_paths: Sequence[Path], baseline: Sequence[Prediction]) -> None:
    """Prove public batched generation works before measuring larger batches."""
    print("\nNative batch-support preflight (two image chats, padding=True):")
    try:
        batched = generate_batch(image_paths[:2])
    except Exception as error:
        print("  FAILED: batched apply_chat_template()/generate() is not viable in this environment.")
        print(f"  Root failure: {type(error).__name__}: {error}")
        print("  No monkey-patch will be applied; benchmark stops before larger batches.")
        raise BatchUnsupportedError("native GLM-OCR batch preflight failed") from error

    token_matches, text_matches = exact_match_counts(baseline[:2], batched)
    if token_matches != 2 or text_matches != 2:
        raise BatchUnsupportedError(
            "native batch generation completed but changed output for the first two smoke images: "
            f"token matches={token_matches}/2, text matches={text_matches}/2"
        )
    print("  PASS: 2/2 token sequences and cleaned texts match Batch Size 1.")


def print_summary(results: Sequence[BatchResult], baseline: Sequence[Prediction]) -> list[BatchResult]:
    viable: list[BatchResult] = []
    print("\n| Batch Size | Total Time (s) | Sec / Image | Peak RSS (MB) | Peak VRAM (MB) | Exact Match vs BS=1 (%) |")
    print("|---:|---:|---:|---:|---:|---:|")
    for result in results:
        token_matches, text_matches = exact_match_counts(baseline, result.predictions)
        exact_percent = 100 * text_matches / len(baseline)
        if token_matches == len(baseline) and text_matches == len(baseline):
            viable.append(result)
        print(
            f"| {result.batch_size} | {result.total_seconds:.2f} | "
            f"{result.total_seconds / len(result.predictions):.2f} | "
            f"{result.peak_rss_mb:.1f} | {result.peak_vram_mb:.1f} | {exact_percent:.1f} |"
        )
        print(
            f"  BS={result.batch_size}: RSS before/after {result.rss_before_mb:.1f}/"
            f"{result.rss_after_mb:.1f} MB; peak VRAM {result.peak_vram_mb:.1f} MB; "
            f"token matches {token_matches}/{len(baseline)}; "
            f"cleaned-text matches {text_matches}/{len(baseline)}."
        )
        if token_matches != len(baseline) or text_matches != len(baseline):
            for i, (b, r) in enumerate(zip(baseline, result.predictions)):
                if b.cleaned_text != r.cleaned_text or b.token_ids != r.token_ids:
                    print(
                        f"    MISMATCH image[{i}]: baseline={b.cleaned_text!r} "
                        f"vs BS={result.batch_size}={r.cleaned_text!r} "
                        f"(token match={b.token_ids == r.token_ids})"
                    )
    return viable


def print_clinical_projection(best: BatchResult) -> None:
    seconds_per_image = best.total_seconds / len(best.predictions)
    print(f"\nClinical UX projection (best viable batch size: {best.batch_size}):")
    print("| Prescription crops | Estimated OCR wait (s) | Clinical UX assessment |")
    print("|---:|---:|---|")
    for crops in (3, 5, 8):
        estimated_seconds = seconds_per_image * crops
        if estimated_seconds <= 2:
            assessment = "within the 2 s target"
        elif estimated_seconds <= 4:
            assessment = "within the 4 s upper target"
        else:
            assessment = "exceeds synchronous 2–4 s target"
        print(f"| {crops} | {estimated_seconds:.2f} | {assessment} |")
    print(
        "Projection uses measured effective throughput and assumes all word crops are available "
        "to submit together. PaddleOCR remains the near-instant baseline; any GLM-OCR result "
        "above 2–4 s is unsuitable as a blocking synchronous step on this CPU."
    )


def main() -> int:
    print("GLM-OCR native CPU batch benchmark")
    print("Diagnostic only — no pipeline, normalization, or threshold changes.\n")
    if not benchmark._load_glm():
        print("ERROR: GLM-OCR could not be loaded; no batch conclusion can be drawn.", file=sys.stderr)
        return 1

    # This is the exact smoke-test sampling path: canonical labels when present,
    # otherwise the raw labels, then the first ten rows.
    dataset_dir = os.path.join(
        "RxHandBD A Handwritten Prescription Word Image Dat", "RxHandBD-ML"
    )
    dataframe = benchmark.load_test_labels(dataset_dir, use_raw=False).iloc[:SMOKE_IMAGE_COUNT].copy()
    image_dir = Path(dataset_dir) / "Test_Set"
    image_paths = [image_dir / filename for filename in dataframe["Images"].tolist()]
    missing = [str(path) for path in image_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Smoke-test images are missing: {missing}")
    print(f"Using the same first {len(image_paths)} smoke-test images as new_models_benchmark.py.")

    print("\nWarm-up: one Batch Size 1 generation (excluded from measurements).")
    generate_batch(image_paths[:1])

    print("\nMeasuring warm Batch Size 1 baseline...")
    baseline_result = run_timed_batch_size(image_paths, batch_size=1)
    baseline = baseline_result.predictions
    run_batch_preflight(image_paths, baseline)

    results = [baseline_result]
    for batch_size in BATCH_SIZES[1:]:
        print(f"Measuring warm Batch Size {batch_size}...")
        results.append(run_timed_batch_size(image_paths, batch_size=batch_size))

    viable = print_summary(results, baseline)
    if not viable:
        raise BatchUnsupportedError("no batch size preserved both generated tokens and cleaned OCR text")
    best = min(viable, key=lambda result: result.total_seconds / len(result.predictions))
    print_clinical_projection(best)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BatchUnsupportedError as error:
        print(f"\nBATCHING NOT VIABLE: {error}", file=sys.stderr)
        raise SystemExit(2)
    except Exception as error:
        print(f"\nBENCHMARK FAILED: {type(error).__name__}: {error}", file=sys.stderr)
        traceback.print_exc()
        raise SystemExit(1)
