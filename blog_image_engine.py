"""
Blog hero image optimization — quality-first JPEG, ≤500KB, max 1200px wide.
Used by SEO publish and batch blog maintenance (no theme API).
"""
from __future__ import annotations

import base64
import io
import logging
import os
from typing import Any

import requests
from PIL import Image

logger = logging.getLogger(__name__)

BLOG_MAX_KB = int(os.environ.get("BLOG_IMAGE_MAX_KB", "500"))
BLOG_MAX_WIDTH = int(os.environ.get("BLOG_IMAGE_MAX_WIDTH", "1200"))
JPEG_MIN_QUALITY = 84
JPEG_MAX_QUALITY = 95


def _has_transparency(im: Image.Image) -> bool:
    if im.mode in ("RGBA", "LA"):
        alpha = im.getextrema()[3]
        return alpha[0] < 255
    if im.mode == "P":
        return "transparency" in im.info
    return False


def _fit_max(im: Image.Image, max_w: int) -> Image.Image:
    w, h = im.size
    if w <= max_w:
        return im
    nh = max(1, int(h * (max_w / w)))
    return im.resize((max_w, nh), Image.Resampling.LANCZOS)


def _flatten_for_jpeg(im: Image.Image) -> Image.Image:
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and _has_transparency(im)):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        rgba = im.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return im.convert("RGB")


def _jpeg_bytes(im: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def encode_blog_jpeg(im: Image.Image, *, max_kb: int | None = None) -> tuple[bytes, dict[str, Any]]:
    """Quality-first: start at high Q, step down; resize only if needed."""
    budget = max_kb if max_kb is not None else BLOG_MAX_KB
    work = _fit_max(im, BLOG_MAX_WIDTH)
    work = _flatten_for_jpeg(work)
    w0, h0 = im.size
    meta: dict[str, Any] = {
        "width_before": w0,
        "height_before": h0,
        "target_kb": budget,
    }

    for _ in range(10):
        for q in range(JPEG_MAX_QUALITY, JPEG_MIN_QUALITY - 1, -1):
            data = _jpeg_bytes(work, q)
            if len(data) <= budget * 1024:
                with Image.open(io.BytesIO(data)) as check:
                    meta.update(
                        {
                            "width_after": check.size[0],
                            "height_after": check.size[1],
                            "quality": q,
                            "bytes": len(data),
                            "kb": round(len(data) / 1024, 1),
                            "target_met": True,
                        }
                    )
                return data, meta
        w, h = work.size
        work = work.resize((max(1, int(w * 0.92)), max(1, int(h * 0.92))), Image.Resampling.LANCZOS)

    data = _jpeg_bytes(work, JPEG_MIN_QUALITY)
    meta.update(
        {
            "width_after": work.size[0],
            "height_after": work.size[1],
            "quality": JPEG_MIN_QUALITY,
            "bytes": len(data),
            "kb": round(len(data) / 1024, 1),
            "target_met": len(data) <= budget * 1024,
        }
    )
    return data, meta


def optimize_image_bytes(raw: bytes, *, max_kb: int | None = None) -> tuple[bytes, dict[str, Any]]:
    with Image.open(io.BytesIO(raw)) as im:
        im.load()
        return encode_blog_jpeg(im, max_kb=max_kb)


def optimize_image_from_url(url: str, *, timeout: int = 90) -> tuple[bytes, dict[str, Any]]:
    if not (url or "").strip():
        raise ValueError("empty image url")
    r = requests.get(url.strip(), timeout=timeout)
    r.raise_for_status()
    meta_in = {"source_url": url.split("?")[0][:120], "source_bytes": len(r.content)}
    data, meta = optimize_image_bytes(r.content)
    meta.update(meta_in)
    return data, meta


def shopify_image_attachment_payload(jpeg_bytes: bytes, alt: str) -> dict[str, str]:
    return {
        "attachment": base64.b64encode(jpeg_bytes).decode("ascii"),
        "alt": alt,
    }


def needs_optimization(url: str, size_bytes: int | None) -> bool:
    if size_bytes is not None and size_bytes <= BLOG_MAX_KB * 1024:
        path = (url or "").split("?")[0].lower()
        if path.endswith((".jpg", ".jpeg")) and size_bytes <= (BLOG_MAX_KB - 20) * 1024:
            return False
    return True
