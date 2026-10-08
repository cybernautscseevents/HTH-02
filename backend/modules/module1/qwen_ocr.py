#!/usr/bin/env python3
"""
Reads a prescription image using local PaddleOCR + Ollama text models,
falling back to qwen3-vl:2b vision model if needed.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
import ollama

MODEL_ID = "qwen3-vl:2b"

SYSTEM_PROMPT = (
    "You are a medical prescription analyzer. Extract from this handwritten "
    "prescription image and return ONLY valid JSON with these fields: patient "
    "(name, age, gender), diagnosis, drugs (array with name, brand, dose, route, "
    "frequency, duration for each), comorbidities (array), pregnancy (true/false). "
    "Return only JSON, no explanation."
)


def _extract_json(text: str) -> dict[str, Any]:
    # Try direct parse first.
    try:
        return json.loads(text)
    except Exception:
        pass

    # Fallback: extract first JSON object from free-form output.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model output")

    clean_text = match.group(0)
    # Remove any trailing commas before closing braces/brackets
    clean_text = re.sub(r',\s*([\]}])', r'\1', clean_text)
    # Remove single line comments
    clean_text = re.sub(r'//.*', '', clean_text)
    
    return json.loads(clean_text)


def _resolve_text_model(host: str) -> str:
    try:
        from urllib.request import Request, urlopen
        import json
        url = host.rstrip("/") + "/api/tags"
        req = Request(url)
        with urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = [m["name"] for m in data.get("models", [])]
        
        # Prefer mistral models
        for target in ["mistral:7b", "mistral", "biomistral"]:
            for m in models:
                if target in m.lower():
                    return m
        # Fallback to any non-vision model
        non_vision = [m for m in models if "vl" not in m.lower()]
        if non_vision:
            return non_vision[0]
        if models:
            return models[0]
    except Exception:
        pass
    return "mistral:7b"


def _group_by_lines(texts: list[str], boxes: Any, y_threshold: float = 15.0) -> str:
    if not texts or boxes is None or len(texts) != len(boxes):
        return "  ".join(texts)
    
    items = []
    for text, box in zip(texts, boxes):
        try:
            # box is [x_min, y_min, x_max, y_max]
            x_min, y_min, x_max, y_max = box
            y_center = (y_min + y_max) / 2.0
            height = y_max - y_min
            items.append({
                "text": text,
                "x_min": x_min,
                "y_center": y_center,
                "height": height
            })
        except Exception:
            # Fallback for any invalid box formatting
            items.append({
                "text": text,
                "x_min": 0,
                "y_center": 0,
                "height": 10
            })
            
    # Group items vertically by sorting them by Y center coordinate
    sorted_by_y = sorted(items, key=lambda k: k["y_center"])
    lines = []
    current_line = []
    
    for item in sorted_by_y:
        if not current_line:
            current_line.append(item)
        else:
            last_item = current_line[-1]
            vertical_diff = abs(item["y_center"] - last_item["y_center"])
            line_height = max(item["height"], last_item["height"])
            # If vertical distance is smaller than 75% of font height or threshold, group on same line
            if vertical_diff < (line_height * 0.75) or vertical_diff < y_threshold:
                current_line.append(item)
            else:
                lines.append(current_line)
                current_line = [item]
    if current_line:
        lines.append(current_line)
        
    # Reconstruct lines from left to right (sort by x_min)
    final_lines = []
    for line in lines:
        sorted_line = sorted(line, key=lambda k: k["x_min"])
        final_lines.append("  ".join([i["text"] for i in sorted_line]))
        
    return "\n".join(final_lines)


def read_prescription(image_path: str) -> dict[str, Any]:
    """
    Reads a prescription image using local PaddleOCR + Ollama model pipeline,
    with a fallback to qwen3-vl:2b vision model if needed.
    """
    try:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")

        # 1. Try local PaddleOCR first
        grouped_ocr_text = ""
        try:
            print("[*] Running local PaddleOCR...")
            from paddleocr import PaddleOCR
            ocr = PaddleOCR(lang='en', enable_mkldnn=False)
            result = ocr.ocr(image_path)
            if result and result[0]:
                raw_texts = result[0].get('rec_texts', [])
                raw_boxes = result[0].get('rec_boxes', [])
                print(f"[+] Local PaddleOCR extracted {len(raw_texts)} text snippets.")
                grouped_ocr_text = _group_by_lines(raw_texts, raw_boxes)
        except Exception as ocr_exc:
            print(f"[!] PaddleOCR error: {ocr_exc}. Falling back to Vision model.")

        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

        # If we got raw texts, use local text model (e.g., Mistral) to structure
        if grouped_ocr_text.strip():
            text_model = _resolve_text_model(host)
            print(f"[*] Sending structured layout to Ollama model '{text_model}'...")
            
            system_prompt = (
                "You are an expert clinical prescription parser. "
                "You will receive a raw multi-line document reconstructed from a prescription via OCR. "
                "The text is formatted such that horizontally aligned values (e.g., drug name and its dosage/duration) "
                "appear on the same line. Reconstruct the patient details, diagnosis, and prescribed drugs. "
                "Correct common transcription/spelling errors based on typical drug names (e.g., 'Amoxillin' -> 'amoxicillin', "
                "'Nebilong' -> 'nebivolol', 'Voliai' -> 'volini', 'Belladanna' -> 'belladonna'). "
                "Respond ONLY with a strict JSON object containing these keys: "
                "patient (name, age, gender), diagnosis, drugs (array with name, brand, dose, route, frequency, duration), "
                "comorbidities (array of strings), pregnancy (true/false). "
                "Do NOT output any markdown blocks (like ```json) or conversational text, only return the raw JSON object."
            )
            
            user_prompt = f"Structured OCR text layout:\n{grouped_ocr_text}"
            
            response = ollama.chat(
                model=text_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                options={"temperature": 0.0}
            )
            output_text = response['message']['content']
            parsed_data = _extract_json(output_text)
            
            # Record that we used hybrid pipeline
            parsed_data["ocr_method"] = "hybrid_paddle_ollama"
            parsed_data["ocr_model"] = text_model
            parsed_data["raw_text"] = grouped_ocr_text
            return parsed_data

        # 2. Fallback: Vision model (qwen3-vl:2b)
        print(f"[*] Sending image to Ollama using vision model '{MODEL_ID}'...")
        response = ollama.chat(
            model=MODEL_ID,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": "Extract structured prescription JSON from this image.",
                    "images": [image_path],
                }
            ],
            options={"temperature": 0.0}
        )
        output_text = response['message']['content']
        parsed_data = _extract_json(output_text)
        parsed_data["ocr_method"] = "vision_model"
        parsed_data["ocr_model"] = MODEL_ID
        return parsed_data

    except Exception as exc:
        return {"status": "error", "error": str(exc)}
