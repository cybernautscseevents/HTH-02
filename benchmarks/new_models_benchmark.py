#!/usr/bin/env python3
"""
benchmarks/new_models_benchmark.py
====================================
OCR Benchmark — GLM-OCR, TrOCR-large-handwritten, Chandra-OCR-2
on RxHandBD v3 Test Set

Usage
-----
    # Smoke test (first 10 images only) — ALWAYS run this before full benchmark
    python benchmarks/new_models_benchmark.py --smoke

    # Full run (all 1115 images)
    python benchmarks/new_models_benchmark.py

    # Specific models only
    python benchmarks/new_models_benchmark.py --models glm trocr
    python benchmarks/new_models_benchmark.py --models trocr --smoke

Notes
-----
* Raw OCR ONLY — no normalization, no RapidFuzz, no spell-check, no dict lookup.
* For VLM models (GLM-OCR, Chandra-OCR-2): any extra prose/markdown in output
  is stripped BEFORE CER calculation. Both raw and cleaned outputs are saved.
  Stripping is clearly flagged in the results (vlm_raw != vlm_pred rows).
* Chandra-OCR-2 license: modified OpenRAIL-M for model weights.
  Free for research/personal use. Prohibits competition with Datalab API.
  See https://huggingface.co/datalab-to/chandra-ocr-2 before using commercially.
* GPU: CUDA is unavailable on this system. All models run on CPU.
  Chandra-OCR-2 at 4B params will be ~30-60s/image on CPU (hours for full run).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import pandas as pd
from tqdm import tqdm

# ---------------------------------------------------------------------------
# jiwer lazy import
# ---------------------------------------------------------------------------
_jiwer_cer = _jiwer_wer = None


def _ensure_jiwer():
    global _jiwer_cer, _jiwer_wer
    if _jiwer_cer is None:
        from jiwer import cer as _c, wer as _w
        _jiwer_cer, _jiwer_wer = _c, _w


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DEFAULT_DATASET_DIR = os.path.join(
    "RxHandBD A Handwritten Prescription Word Image Dat", "RxHandBD-ML"
)
DEFAULT_OUTPUT_DIR = os.path.join("results", "benchmark")
TROCR_LOCAL_PATH = "models/trocr-large-handwritten"

# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def _norm(t: str) -> str:
    return " ".join(t.split()).lower()


def compute_cer(ref: str, hyp: str) -> float:
    _ensure_jiwer()
    r, h = _norm(ref), _norm(hyp)
    if not r and not h:
        return 0.0
    if not r:
        return 1.0
    return _jiwer_cer(r, h)


def compute_wer(ref: str, hyp: str) -> float:
    _ensure_jiwer()
    r, h = _norm(ref), _norm(hyp)
    if not r and not h:
        return 0.0
    if not r:
        return 1.0
    return _jiwer_wer(r, h)


def exact_match(ref: str, hyp: str) -> int:
    return int(_norm(ref) == _norm(hyp))


# ---------------------------------------------------------------------------
# VLM output cleanup
# ---------------------------------------------------------------------------

_MARKDOWN_RE = re.compile(
    r"```[a-z]*\n?|```|^\s*#+\s*|^\s*[-*]\s*|\*\*|__|`",
    re.MULTILINE,
)
_PREAMBLE_RE = re.compile(
    r"(?i)(the\s+(text|word|content|image)\s+(is|reads|says|:)\s*[\"']?|"
    r"transcribed\s+text\s*:\s*|ocr\s+(result|output)\s*:\s*|"
    r"text\s+in\s+the\s+image\s*:\s*)",
)


def strip_vlm_prose(raw: str) -> Tuple[str, bool]:
    """
    Strip markdown fences and preamble prose from VLM output.
    Returns (cleaned_text, was_modified).

    Strategy:
    1. Remove markdown fences and decorators
    2. Remove common preamble phrases ("The text is ...", "OCR result: ...")
    3. Take the first non-empty line of whatever remains
    4. Strip surrounding quotes

    This is conservative — designed to not silently swallow real OCR errors.
    If the model outputs prose it shouldn't, the stripping is flagged.
    """
    original = raw.strip()
    if not original:
        return "", False

    text = _MARKDOWN_RE.sub(" ", original)
    text = _PREAMBLE_RE.sub("", text)
    text = text.strip().strip('"\'')

    # Take first non-empty line
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    first = lines[0] if lines else text

    was_modified = (first != original)
    return first, was_modified


# ===========================================================================
# Engine 1: GLM-OCR (zai-org/GLM-OCR, 0.9B, MIT license)
# ===========================================================================

_glm_model = _glm_processor = None
_glm_device = "cpu"
_GLM_MODEL_ID = "zai-org/GLM-OCR"


def _load_glm():
    global _glm_model, _glm_processor, _glm_device
    if _glm_model is not None:
        return True

    try:
        import torch
        from transformers import AutoProcessor, AutoModelForCausalLM
    except ImportError:
        print("ERROR: transformers required for GLM-OCR", file=sys.stderr)
        return False

    print(f"  Loading {_GLM_MODEL_ID}")
    print(f"  License  : MIT (model) | Apache-2.0 (PP-DocLayout pipeline component)")
    print(f"  Params   : ~0.9B")
    print(f"  NOTE: GLM-OCR is document/layout-focused (OmniDocBench). It does support")
    print(f"        handwriting in complex documents, but performance on isolated")
    print(f"        single-word crops like RxHandBD is EXPECTED to be weaker than on")
    print(f"        structured documents. A weak result here is expected, not a bug.")

    use_cuda = torch.cuda.is_available()
    if use_cuda:
        gpu_name = torch.cuda.get_device_name(0)
        print(f"  CUDA available — attempting GPU load on: {gpu_name}")
    else:
        print("  CUDA not available — loading on CPU (float32)")

    try:
        _glm_processor = AutoProcessor.from_pretrained(
            _GLM_MODEL_ID, trust_remote_code=True
        )
        # GLM-OCR uses a custom architecture (GlmOcrForConditionalGeneration).
        # We can import it directly since it is natively supported in this
        # transformers fork, bypassing the AutoModel registry.
        from transformers import GlmOcrForConditionalGeneration

        if use_cuda:
            try:
                _glm_model = GlmOcrForConditionalGeneration.from_pretrained(
                    _GLM_MODEL_ID,
                    trust_remote_code=True,
                    torch_dtype=torch.bfloat16,
                    device_map="cuda:0",
                )
                _glm_device = "cuda:0"
                _glm_model.eval()
                print(f"  Loaded OK (GPU cuda:0, bfloat16) — class: {type(_glm_model).__name__}")
                return True
            except Exception as gpu_error:
                print(f"  GPU LOAD FAILED, falling back to CPU: {gpu_error}", file=sys.stderr)
                _glm_model = None

        _glm_model = GlmOcrForConditionalGeneration.from_pretrained(
            _GLM_MODEL_ID,
            trust_remote_code=True,
            torch_dtype=torch.float32,
            device_map="cpu",
        )
        _glm_device = "cpu"
        _glm_model.eval()
        print(f"  Loaded OK (CPU, float32) — class: {type(_glm_model).__name__}")
        return True
    except Exception as e:
        print(f"  LOAD FAILED: {e}", file=sys.stderr)
        return False


def run_glm_ocr(image_path: str) -> Tuple[str, str]:
    """Returns (cleaned_pred, raw_pred)."""
    import torch
    from PIL import Image

    try:
        img = Image.open(image_path).convert("RGB")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": img},
                    {"type": "text", "text": (
                        "Please transcribe the text in this image exactly as written. "
                        "Output ONLY the transcribed text with no additional explanation or formatting."
                    )},
                ],
            }
        ]
        inputs = _glm_processor.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=True,
            return_tensors="pt", return_dict=True
        )
        inputs = {k: (v.to(_glm_model.device) if hasattr(v, "to") else v) for k, v in inputs.items()}
        with torch.no_grad():
            output_ids = _glm_model.generate(
                **inputs,
                max_new_tokens=64,
                do_sample=False,
                temperature=None,
                top_p=None,
            )
        new_ids = output_ids[:, inputs["input_ids"].shape[1]:]
        raw = _glm_processor.decode(new_ids[0], skip_special_tokens=True).strip()
        cleaned, _ = strip_vlm_prose(raw)
        return cleaned, raw
    except Exception as e:
        print(f"  [GLM-OCR ERROR] {image_path}: {e}", file=sys.stderr)
        return "", ""


# ===========================================================================
# Engine 2: TrOCR-large-handwritten (microsoft/trocr-large-handwritten)
# ===========================================================================

_trocr_model = _trocr_processor = None
_TROCR_MODEL_ID = "microsoft/trocr-large-handwritten"


def _load_trocr():
    global _trocr_model, _trocr_processor
    if _trocr_model is not None:
        return True

    import torch
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel

    local_path = TROCR_LOCAL_PATH
    if os.path.isdir(local_path) and os.path.isfile(os.path.join(local_path, "config.json")):
        source = local_path
        print(f"  Loading TrOCR from local path: {local_path}")
    else:
        source = _TROCR_MODEL_ID
        print(f"  Downloading TrOCR: {_TROCR_MODEL_ID}")

    print(f"  License  : MIT (Microsoft)")
    print(f"  Params   : ~0.33B (ViT encoder + mBART decoder)")
    print(f"  NOTE: Prior runs showed this model struggles on Indian prescription")
    print(f"        handwriting. This run is a controlled RxHandBD-specific sanity check.")

    try:
        _trocr_processor = TrOCRProcessor.from_pretrained(source, use_fast=True)
        _trocr_model = VisionEncoderDecoderModel.from_pretrained(
            source, torch_dtype=torch.float32
        )
        _trocr_model.eval()
        print(f"  Loaded OK (CPU, float32)")
        return True
    except Exception as e:
        print(f"  LOAD FAILED: {e}", file=sys.stderr)
        return False


def run_trocr(image_path: str) -> Tuple[str, str]:
    import torch
    from PIL import Image

    try:
        img = Image.open(image_path).convert("RGB")
        pv = _trocr_processor(images=img, return_tensors="pt").pixel_values
        with torch.no_grad():
            ids = _trocr_model.generate(pv, max_new_tokens=30)
        raw = _trocr_processor.batch_decode(ids, skip_special_tokens=True)[0].strip()

        # TrOCR-large-handwritten systematically appends " ." to every output —
        # a known artifact of the mBART decoder when given single-word inputs.
        # This is stripped before CER calculation; raw text is preserved for audit.
        # This is NOT a VLM hallucination strip — it's a decoder EOS artifact.
        cleaned = raw
        if cleaned.endswith(" ."):
            cleaned = cleaned[:-2].strip()
        elif cleaned.endswith(".") and len(cleaned) > 1:
            cleaned = cleaned[:-1].strip()

        return cleaned, raw
    except Exception as e:
        print(f"  [TrOCR ERROR] {image_path}: {e}", file=sys.stderr)
        return "", ""



# ===========================================================================
# Engine 3: Chandra-OCR-2 (datalab-to/chandra-ocr-2, 4B)
# ===========================================================================

_chandra_model = _chandra_processor = None
_CHANDRA_MODEL_ID = "datalab-to/chandra-ocr-2"


def _load_chandra():
    global _chandra_model, _chandra_processor
    if _chandra_model is not None:
        return True

    import torch
    from transformers import AutoProcessor, AutoModelForCausalLM

    print(f"  Loading {_CHANDRA_MODEL_ID}")
    print(f"  !! LICENSE WARNING: Modified OpenRAIL-M for model weights.")
    print(f"     Free for research/personal use and startups with <$2M revenue.")
    print(f"     PROHIBITS use competitive with Datalab's commercial API.")
    print(f"     For commercial use beyond the above: contact Datalab.")
    print(f"     See: https://huggingface.co/datalab-to/chandra-ocr-2")
    print(f"  Params   : ~4B (bfloat16 load to fit ~8GB RAM)")
    print(f"  !! CPU WARNING: ~30-60s per image. Full run = 9-18 hours on this CPU.")
    print(f"     Strongly recommend running --models chandra separately, overnight.")

    try:
        _chandra_processor = AutoProcessor.from_pretrained(
            _CHANDRA_MODEL_ID, trust_remote_code=True
        )
        from transformers import Qwen3_5ForConditionalGeneration
        _chandra_model = Qwen3_5ForConditionalGeneration.from_pretrained(
            _CHANDRA_MODEL_ID,
            trust_remote_code=True,
            torch_dtype=torch.bfloat16,
            device_map="cpu",
            low_cpu_mem_usage=True,
        )
        _chandra_model.eval()
        print(f"  Loaded OK (CPU, bfloat16)")
        return True
    except Exception as e:
        print(f"  LOAD FAILED: {e}", file=sys.stderr)
        return False


def run_chandra(image_path: str) -> Tuple[str, str]:
    import torch
    from PIL import Image

    try:
        img = Image.open(image_path).convert("RGB")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image"},
                    {"type": "text", "text": (
                        "Transcribe the text in this image exactly as written. "
                        "Output ONLY the text, nothing else."
                    )},
                ],
            }
        ]
        text_prompt = _chandra_processor.apply_chat_template(
            messages, add_generation_prompt=True
        )
        inputs = _chandra_processor(
            text=text_prompt, images=[img], return_tensors="pt"
        )
        with torch.no_grad():
            output_ids = _chandra_model.generate(
                **inputs,
                max_new_tokens=64,
                do_sample=False,
                temperature=None,
                top_p=None,
            )
        new_ids = output_ids[:, inputs["input_ids"].shape[1]:]
        raw = _chandra_processor.decode(new_ids[0], skip_special_tokens=True).strip()
        cleaned, _ = strip_vlm_prose(raw)
        return cleaned, raw
    except Exception as e:
        print(f"  [Chandra ERROR] {image_path}: {e}", file=sys.stderr)
        return "", ""


# ===========================================================================
# Engine 4: Qwen2.5-VL-3B-Instruct (Qwen/Qwen2.5-VL-3B-Instruct, 3B)
# ===========================================================================

_qwen_model = _qwen_processor = None
_QWEN_MODEL_ID = "Qwen/Qwen2.5-VL-3B-Instruct"

def _load_qwen():
    global _qwen_model, _qwen_processor
    if _qwen_model is not None:
        return True

    import torch
    from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor

    print(f"  Loading {_QWEN_MODEL_ID}")
    print(f"  License  : Qwen Research License Agreement (Non-Commercial)")
    print(f"  Params   : ~3B")
    print(f"  NOTE: General-purpose VLM. Prompt constrained to literal transcription.")

    try:
        _qwen_processor = AutoProcessor.from_pretrained(
            _QWEN_MODEL_ID, trust_remote_code=True
        )
        _qwen_model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            _QWEN_MODEL_ID,
            torch_dtype=torch.bfloat16,
            device_map="cpu",
        )
        _qwen_model.eval()
        print(f"  Loaded OK (CPU, bfloat16) — class: {type(_qwen_model).__name__}")
        return True
    except Exception as e:
        print(f"  LOAD FAILED: {e}", file=sys.stderr)
        return False

def run_qwen(image_path: str) -> Tuple[str, str]:
    import torch
    from PIL import Image

    try:
        img = Image.open(image_path).convert("RGB")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image"},
                    {"type": "text", "text": (
                        "Transcribe exactly the handwritten text in this image. "
                        "Output ONLY the text you see, nothing else. "
                        "Do not correct spelling, do not guess what word it should be, "
                        "do not add punctuation that isn't visible, do not explain."
                    )},
                ],
            }
        ]
        text_prompt = _qwen_processor.apply_chat_template(
            messages, add_generation_prompt=True
        )
        inputs = _qwen_processor(
            text=[text_prompt], images=[img], padding=True, return_tensors="pt"
        )
        with torch.no_grad():
            output_ids = _qwen_model.generate(
                **inputs, max_new_tokens=64
            )
        new_ids = output_ids[:, inputs["input_ids"].shape[1]:]
        raw = _qwen_processor.batch_decode(new_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0].strip()
        cleaned, _ = strip_vlm_prose(raw)
        return cleaned, raw
    except Exception as e:
        print(f"  [QWEN ERROR] {image_path}: {e}", file=sys.stderr)
        return "", ""

# ===========================================================================
# Model registry
# ===========================================================================

LOADERS = {
    "glm": _load_glm,
    "trocr": _load_trocr,
    "chandra": _load_chandra,
    "qwen": _load_qwen,
}
RUNNERS = {
    "glm": run_glm_ocr,
    "trocr": run_trocr,
    "chandra": run_chandra,
    "qwen": run_qwen,
}
MODEL_META = {
    "glm": {
        "name": "GLM-OCR",
        "model_id": _GLM_MODEL_ID,
        "params": "0.9B",
        "license": "MIT (model) / Apache-2.0 (pipeline)",
        "framework": "transformers (AutoModelForCausalLM)",
        "is_vlm": True,
        "precision": "float32",
        "notes": "Document/layout-focused. Weak results on handwritten word crops EXPECTED.",
    },
    "trocr": {
        "name": "TrOCR-large-handwritten",
        "model_id": _TROCR_MODEL_ID,
        "params": "0.33B",
        "license": "MIT (Microsoft)",
        "framework": "transformers (VisionEncoderDecoderModel)",
        "is_vlm": False,
        "precision": "float32",
        "output_postprocessed": True,  # trailing ' .' artifact stripped
        "notes": "Specialized HTR. Trailing ' .' artifact stripped (mBART EOS). Prior runs showed weakness on Indian handwriting.",

    },
    "chandra": {
        "name": "Chandra-OCR-2",
        "model_id": _CHANDRA_MODEL_ID,
        "params": "4B",
        "license": "modified OpenRAIL-M (weights) / Apache-2.0 (code)",
        "framework": "transformers (AutoModelForCausalLM)",
        "is_vlm": True,
        "precision": "bfloat16",
        "notes": "SLOW on CPU (~30-60s/img). License: prohibits Datalab API competition.",
    },
    "qwen": {
        "name": "Qwen2.5-VL-3B-Instruct",
        "model_id": _QWEN_MODEL_ID,
        "params": "3B",
        "license": "Qwen Research License Agreement (Non-Commercial)",
        "framework": "transformers (Qwen2_5_VLForConditionalGeneration)",
        "is_vlm": True,
        "precision": "bfloat16",
        "notes": "General-purpose VLM constrained via prompt. Prone to semantic hallucination. Strict non-commercial license.",
    },
}
AVAILABLE_MODELS = list(MODEL_META.keys())


# ===========================================================================
# Dataset loader
# ===========================================================================

def load_test_labels(dataset_dir: str, use_raw: bool = False) -> pd.DataFrame:
    clean_csv_path = os.path.join("results", "RxHandBD_Test_Label_clean.csv")
    raw_csv_path = os.path.join(dataset_dir, "Test_Label.csv")

    if not use_raw and os.path.isfile(clean_csv_path):
        csv_path = clean_csv_path
        dataset_mode = "CANONICAL CLEAN (1,018 images, known bad rows excluded)"
    else:
        csv_path = raw_csv_path
        dataset_mode = "RAW (unfiltered 1,115 images with known alignment issues)"

    if not os.path.isfile(csv_path):
        sys.exit(f"ERROR: Label file not found at {csv_path}")

    df = pd.read_csv(csv_path, dtype=str).dropna(subset=["Images", "Text"])
    df.columns = df.columns.str.strip()
    df["Images"] = df["Images"].str.strip()
    df["Text"] = df["Text"].str.strip()
    image_dir = os.path.join(dataset_dir, "Test_Set")
    if not os.path.isdir(image_dir):
        sys.exit(f"ERROR: Test_Set directory not found: {image_dir}")
    print(f"✓ Loaded {len(df)} test samples [{dataset_mode}] from {csv_path}")
    return df


# ===========================================================================
# Smoke test
# ===========================================================================

def run_smoke_test(
    models: List[str],
    dataset_dir: str,
    n: int = 10,
    use_raw: bool = False,
) -> Dict[str, bool]:
    """
    Run all requested models on first N images.
    Returns dict of {model_key: passed_bool}.
    Prints full comparison table and per-model metadata.
    """
    df = load_test_labels(dataset_dir, use_raw=use_raw)
    df = df.iloc[:n].copy()
    image_dir = os.path.join(dataset_dir, "Test_Set")

    print(f"\n{'='*72}")
    print(f"  SMOKE TEST — first {n} images on {len(models)} model(s)")
    print(f"{'='*72}\n")

    # Print model metadata
    for mk in models:
        m = MODEL_META[mk]
        print(f"  [{m['name']}]")
        print(f"    HF ID     : {m['model_id']}")
        print(f"    Params    : {m['params']}  |  Precision: {m['precision']}  |  Device: CPU")
        print(f"    License   : {m['license']}")
        print(f"    Is VLM    : {m['is_vlm']} (output prose-stripping: {'YES' if m['is_vlm'] else 'NO'})")
        print(f"    Notes     : {m['notes']}")
        print()

    # Load models (fail fast — one bad load stops that model)
    load_status: Dict[str, bool] = {}
    for mk in models:
        print(f"\n── Loading {MODEL_META[mk]['name']} ──")
        t0 = time.time()
        ok = LOADERS[mk]()
        load_status[mk] = ok
        if ok:
            print(f"  → Load OK ({time.time()-t0:.1f}s)")
        else:
            print(f"  → LOAD FAILED — this model will be SKIPPED in smoke table and full run.")

    # Run inference on each image for each loaded model
    fnames = df["Images"].tolist()
    gts = df["Text"].tolist()

    all_cleaned: Dict[str, List[str]] = {mk: [] for mk in models}
    all_raw: Dict[str, List[str]] = {mk: [] for mk in models}
    all_errors: Dict[str, int] = {mk: 0 for mk in models}
    all_empty: Dict[str, int] = {mk: 0 for mk in models}
    all_vlm_cleaned: Dict[str, int] = {mk: 0 for mk in models}

    print(f"\n── Running inference on {n} images ──")
    for fname, gt in zip(fnames, gts):
        img_path = os.path.join(image_dir, fname)
        for mk in models:
            if not load_status[mk]:
                all_cleaned[mk].append("[LOAD FAILED]")
                all_raw[mk].append("")
                continue
            t0 = time.time()
            try:
                cleaned, raw = RUNNERS[mk](img_path)
                all_cleaned[mk].append(cleaned)
                all_raw[mk].append(raw)
                if not cleaned:
                    all_empty[mk] += 1
                if MODEL_META[mk]["is_vlm"] and cleaned != raw:
                    all_vlm_cleaned[mk] += 1
            except Exception as e:
                print(f"  [{mk} ERROR] {fname}: {e}", file=sys.stderr)
                all_cleaned[mk].append("")
                all_raw[mk].append("")
                all_errors[mk] += 1

    # Comparison table
    print(f"\n{'─'*80}")
    header = f"  {'File':<12} {'GT':<14}"
    for mk in models:
        col = MODEL_META[mk]["name"][:16]
        header += f" {col:<17}"
    print(header)
    print(f"  {'─'*78}")

    for i, (fname, gt) in enumerate(zip(fnames, gts)):
        row = f"  {fname:<12} {gt:<14}"
        for mk in models:
            pred = all_cleaned[mk][i] if i < len(all_cleaned[mk]) else ""
            if pred == "[LOAD FAILED]":
                cell = f"{'[LOAD FAILED]':<16} "
            else:
                ok = "✓" if _norm(pred) == _norm(gt) else " "
                cell = f"{pred[:15]:<15}{ok} "
            row += cell
        print(row)

    # Per-model metrics
    print(f"\n── Smoke Test Summary ──")
    print(f"  {'Model':<26} {'CER':>7} {'WER':>7} {'Exact%':>7}  {'Empty':>5}  {'Err':>4}  {'VLMClean':>9}  Status")
    print(f"  {'─'*75}")
    for mk in models:
        preds = all_cleaned[mk]
        if not load_status[mk]:
            print(f"  {MODEL_META[mk]['name']:<26} {'—':>7} {'—':>7} {'—':>7}  {'—':>5}  {'—':>4}  {'—':>9}  LOAD FAILED")
            continue
        cers = [compute_cer(gt, p) for gt, p in zip(gts, preds)]
        wers = [compute_wer(gt, p) for gt, p in zip(gts, preds)]
        exacts = [exact_match(gt, p) for gt, p in zip(gts, preds)]
        is_vlm = MODEL_META[mk]["is_vlm"]
        vlm_str = f"{all_vlm_cleaned[mk]}/{n}" if is_vlm else "N/A"
        print(
            f"  {MODEL_META[mk]['name']:<26} {sum(cers)/n:>7.4f} {sum(wers)/n:>7.4f} "
            f"{sum(exacts)/n*100:>6.1f}%  {all_empty[mk]:>5}  {all_errors[mk]:>4}  {vlm_str:>9}  OK"
        )

    # VLM raw vs cleaned inspection
    for mk in models:
        if MODEL_META[mk]["is_vlm"] and load_status[mk]:
            print(f"\n── {MODEL_META[mk]['name']} — raw vs cleaned (first 5) ──")
            for i in range(min(5, n)):
                raw = all_raw[mk][i] if i < len(all_raw[mk]) else ""
                cln = all_cleaned[mk][i] if i < len(all_cleaned[mk]) else ""
                diff = " [STRIPPED]" if cln != raw else ""
                print(f"  {fnames[i]}: raw={raw!r:50s}  cleaned={cln!r}{diff}")

    # Determine which models passed
    passed: Dict[str, bool] = {}
    for mk in models:
        if not load_status[mk]:
            passed[mk] = False
            print(f"\n  !! {MODEL_META[mk]['name']}: FAILED smoke test (load error). Will be EXCLUDED from full run.")
        elif all_errors[mk] == n:
            passed[mk] = False
            print(f"\n  !! {MODEL_META[mk]['name']}: ALL {n} images errored. Will be EXCLUDED from full run.")
        else:
            passed[mk] = True
            if all_errors[mk] > 0:
                print(f"\n  !! {MODEL_META[mk]['name']}: {all_errors[mk]} errors in smoke test. Proceeding with caution.")

    return passed


# ===========================================================================
# Full benchmark
# ===========================================================================

def run_full_benchmark(
    models: List[str],
    dataset_dir: str,
    output_dir: str,
    passed_smoke: Optional[Dict[str, bool]] = None,
    use_raw: bool = False,
) -> None:
    """Run all (passed) models on the test images."""
    if passed_smoke is not None:
        excluded = [m for m in models if not passed_smoke.get(m, True)]
        active = [m for m in models if passed_smoke.get(m, True)]
    else:
        excluded = []
        active = models

    if not active:
        print("ERROR: No models passed smoke test. Aborting full run.")
        return

    if excluded:
        print(f"\n  Excluding (failed smoke): {[MODEL_META[m]['name'] for m in excluded]}")

    df = load_test_labels(dataset_dir, use_raw=use_raw)
    image_dir = os.path.join(dataset_dir, "Test_Set")
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'='*72}")
    print(f"  FULL BENCHMARK — {len(active)} model(s) on {len(df)} images")
    print(f"{'='*72}\n")

    # Load models
    load_ok: Dict[str, bool] = {}
    for mk in active:
        print(f"\n── Loading {MODEL_META[mk]['name']} ──")
        t0 = time.time()
        ok = LOADERS[mk]()
        load_ok[mk] = ok
        if ok:
            print(f"  → Ready ({time.time()-t0:.1f}s)")
        else:
            print(f"  → LOAD FAILED — excluding from run")

    active_run = [m for m in active if load_ok.get(m)]
    if not active_run:
        print("ERROR: All models failed to load. Aborting.")
        return

    # Per-image inference
    records: List[dict] = []
    times: Dict[str, List[float]] = {mk: [] for mk in active_run}
    errors: Dict[str, int] = {mk: 0 for mk in active_run}
    empty: Dict[str, int] = {mk: 0 for mk in active_run}
    vlm_cleaned: Dict[str, int] = {mk: 0 for mk in active_run}

    print(f"\n── Running {len(df)} images ──")
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Benchmarking"):
        fname = row["Images"]
        gt = row["Text"]
        img_path = os.path.join(image_dir, fname)
        rec = {"filename": fname, "ground_truth": gt}

        for mk in active_run:
            t0 = time.time()
            try:
                cleaned, raw = RUNNERS[mk](img_path)
                elapsed = time.time() - t0
                if not cleaned:
                    empty[mk] += 1
                if MODEL_META[mk]["is_vlm"] and cleaned != raw:
                    vlm_cleaned[mk] += 1
            except Exception as e:
                print(f"  [{mk} ERROR] {fname}: {e}", file=sys.stderr)
                cleaned, raw = "", ""
                elapsed = time.time() - t0
                errors[mk] += 1

            times[mk].append(elapsed)
            rec[f"{mk}_pred"] = cleaned
            # Save raw output for VLMs (prose stripping) and TrOCR (trailing dot artifact)
            if MODEL_META[mk]["is_vlm"] or MODEL_META[mk].get("output_postprocessed"):
                rec[f"{mk}_raw"] = raw
            rec[f"{mk}_cer"] = compute_cer(gt, cleaned)
            rec[f"{mk}_wer"] = compute_wer(gt, cleaned)
            rec[f"{mk}_exact"] = exact_match(gt, cleaned)
            rec[f"{mk}_latency_s"] = round(elapsed, 3)


        records.append(rec)

    results_df = pd.DataFrame(records)

    # Save CSV
    csv_out = os.path.join(output_dir, "new_models_benchmark_results.csv")
    results_df.to_csv(csv_out, index=False)
    print(f"\n✓ Per-image results saved to {csv_out}")

    # Aggregate summary
    print("\n" + "=" * 78)
    print("  NEW MODELS BENCHMARK SUMMARY — RxHandBD v3 Test Set")
    print("=" * 78)
    print(f"  {'Model':<26} {'CER':>8} {'WER':>8} {'Exact%':>8}  {'Lat/img':>8}  {'Total':>7}  {'Empty':>5}  {'Err':>4}")
    print("-" * 78)

    metadata = []
    for mk in active_run:
        mean_cer = results_df[f"{mk}_cer"].mean()
        mean_wer = results_df[f"{mk}_wer"].mean()
        acc = results_df[f"{mk}_exact"].mean() * 100
        mean_lat = results_df[f"{mk}_latency_s"].mean()
        total_time = results_df[f"{mk}_latency_s"].sum()
        print(
            f"  {MODEL_META[mk]['name']:<26} {mean_cer:>8.4f} {mean_wer:>8.4f} {acc:>7.2f}%  "
            f"{mean_lat:>7.2f}s  {total_time/60:>5.1f}m  {empty[mk]:>5}  {errors[mk]:>4}"
        )
        metadata.append({
            "model": MODEL_META[mk]["name"],
            "model_id": MODEL_META[mk]["model_id"],
            "params": MODEL_META[mk]["params"],
            "license": MODEL_META[mk]["license"],
            "framework": MODEL_META[mk]["framework"],
            "is_vlm": MODEL_META[mk]["is_vlm"],
            "vlm_output_cleaned_count": vlm_cleaned[mk] if MODEL_META[mk]["is_vlm"] else 0,
            "device": "CPU",
            "precision": MODEL_META[mk]["precision"],
            "n_images": len(df),
            "mean_cer": round(mean_cer, 4),
            "mean_wer": round(mean_wer, 4),
            "exact_match_pct": round(acc, 2),
            "mean_latency_s": round(mean_lat, 3),
            "total_runtime_s": round(total_time, 1),
            "empty_outputs": empty[mk],
            "errors": errors[mk],
        })
    print("=" * 78)

    # Save metadata JSON
    meta_out = os.path.join(output_dir, "new_models_benchmark_metadata.json")
    with open(meta_out, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"✓ Metadata saved to {meta_out}")

    # Worst-20 per model
    for mk in active_run:
        worst = results_df.nlargest(20, f"{mk}_cer")[
            ["filename", "ground_truth", f"{mk}_pred", f"{mk}_cer"]
        ].reset_index(drop=True)
        print(f"\n── Worst 20 failures: {MODEL_META[mk]['name']} ──")
        print(f"  {'#':>3}  {'File':<12} {'GT':<20} {'Pred':<20} {'CER':>6}")
        print(f"  {'─'*65}")
        for i, r in worst.iterrows():
            print(
                f"  {i+1:>3}  {r['filename']:<12} {str(r['ground_truth'])[:18]:<20} "
                f"{str(r[f'{mk}_pred'])[:18]:<20} {r[f'{mk}_cer']:>6.3f}"
            )

    # Full comparison table (baselines + new)
    print("\n" + "=" * 80)
    print("  FULL COMPARISON — All Engines (RxHandBD v3 Test Set, 1115 images)")
    print("=" * 80)
    baselines = [
        ("PP-OCRv5-server_rec",   0.5667, 0.8716,  9.24, "~60ms",  "multilingual 18k-char dict (CURRENT BASELINE)"),
        ("en-PP-OCRv5-mobile_rec",0.5195, 0.9135, 10.85, "~35ms",  "English-only 440-char dict (Step 0 finding)"),
        ("docTR+PARSeq",          0.6887, None,    3.59, "N/A",    "prior benchmark"),
    ]
    print(f"  {'Engine':<28} {'CER':>8} {'WER':>8} {'Exact%':>8}  {'Lat/img':>9}")
    print(f"  {'─'*70}")
    for name, cer_v, wer_v, acc_v, lat, note in baselines:
        wer_s = f"{wer_v:.4f}" if wer_v else "  N/A  "
        print(f"  {name:<28} {cer_v:>8.4f} {wer_s:>8} {acc_v:>7.2f}%  {lat:>9}  ← {note}")
    for mk in active_run:
        mean_cer = results_df[f"{mk}_cer"].mean()
        mean_wer = results_df[f"{mk}_wer"].mean()
        acc = results_df[f"{mk}_exact"].mean() * 100
        mean_lat = results_df[f"{mk}_latency_s"].mean()
        print(
            f"  {MODEL_META[mk]['name']:<28} {mean_cer:>8.4f} {mean_wer:>8.4f} {acc:>7.2f}%  {mean_lat:>7.2f}s"
        )
    print("=" * 80)
    print()


# ===========================================================================
# CLI
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Benchmark GLM-OCR / TrOCR-large / Chandra-OCR-2 on RxHandBD v3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dataset-dir", default=DEFAULT_DATASET_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--models", nargs="+", default=AVAILABLE_MODELS, choices=AVAILABLE_MODELS,
        help=f"Models to run: {AVAILABLE_MODELS} (default: all)"
    )
    parser.add_argument(
        "--smoke", action="store_true",
        help="Smoke test only (first 10 images). Run this before --full."
    )
    parser.add_argument(
        "--smoke-n", type=int, default=10,
        help="Number of images for smoke test (default: 10)"
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Full 1115-image run. Should be preceded by --smoke."
    )
    parser.add_argument(
        "--smoke-then-full", action="store_true",
        help="Smoke test first, then auto-continue to full run for passing models."
    )
    parser.add_argument(
        "--use-raw", action="store_true",
        help="Use raw uncleaned Test_Label.csv (1,115 images) instead of canonical clean set"
    )
    args = parser.parse_args()

    if not (args.smoke or args.full or args.smoke_then_full):
        # Default: smoke test only, to be safe
        args.smoke = True
        print("No mode specified — defaulting to --smoke. Use --full or --smoke-then-full for full run.\n")

    print(f"OCR Benchmark — New Models on RxHandBD v3")
    print(f"  Dataset  : {args.dataset_dir}")
    print(f"  Output   : {args.output_dir}")
    print(f"  Models   : {', '.join(args.models)}")
    print(f"  Use Raw  : {args.use_raw}")

    if args.smoke:
        run_smoke_test(args.models, args.dataset_dir, n=args.smoke_n, use_raw=args.use_raw)

    elif args.full:
        run_full_benchmark(args.models, args.dataset_dir, args.output_dir, use_raw=args.use_raw)

    elif args.smoke_then_full:
        passed = run_smoke_test(args.models, args.dataset_dir, n=args.smoke_n, use_raw=args.use_raw)
        passed_keys = [m for m, ok in passed.items() if ok]
        failed_keys = [m for m, ok in passed.items() if not ok]
        if failed_keys:
            print(f"\n  !! STOPPING for failed models: {[MODEL_META[m]['name'] for m in failed_keys]}")
            print(f"     Proceeding with: {[MODEL_META[m]['name'] for m in passed_keys]}")
        if not passed_keys:
            print("  No models passed smoke test. Full run aborted.")
            return
        run_full_benchmark(passed_keys, args.dataset_dir, args.output_dir, passed_smoke=passed, use_raw=args.use_raw)


if __name__ == "__main__":
    main()

