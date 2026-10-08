"""Deterministic image preparation for GLM-OCR inputs."""

from __future__ import annotations

from typing import Any

MIN_IMAGE_SIDE = 32


def prepare_image(image: Any, *, enhance_contrast: bool = True) -> tuple[Any, tuple[str, ...]]:
    """Normalize orientation, color, contrast, and undersized inputs."""
    from PIL import Image, ImageOps

    prepared = ImageOps.exif_transpose(image)
    if prepared.width <= 0 or prepared.height <= 0:
        raise ValueError("image dimensions must be positive")
    if prepared.mode in {"RGBA", "LA"} or "transparency" in prepared.info:
        rgba = prepared.convert("RGBA")
        background = Image.new("RGB", prepared.size, "white")
        background.paste(rgba.convert("RGB"), mask=rgba.getchannel("A"))
        prepared = background
    else:
        prepared = prepared.convert("RGB")

    warnings: list[str] = []
    if prepared.width < MIN_IMAGE_SIDE or prepared.height < MIN_IMAGE_SIDE:
        scale = max(MIN_IMAGE_SIDE / prepared.width, MIN_IMAGE_SIDE / prepared.height)
        size = (
            max(MIN_IMAGE_SIDE, round(prepared.width * scale)),
            max(MIN_IMAGE_SIDE, round(prepared.height * scale)),
        )
        prepared = prepared.resize(size, Image.Resampling.LANCZOS)
        warnings.append(f"Image upscaled to {size[0]}x{size[1]} pixels")

    if enhance_contrast:
        prepared = ImageOps.autocontrast(prepared, cutoff=1, preserve_tone=True)
    return prepared, tuple(warnings)
