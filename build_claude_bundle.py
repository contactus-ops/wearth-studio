"""Build review bundles for Claude: plain UTF-8 upload + optional small LZMA.

Run: python build_claude_bundle.py
"""
import lzma
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
UPLOAD_TXT = ROOT / "wearth_studio_FOR_CLAUDE_UPLOAD.txt"
OUT_LZMA = ROOT / "wearth_studio_for_claude.lzma"
README = ROOT / "wearth_studio_for_claude_HOWTO.txt"


def stripped_app() -> str:
    p = ROOT / "app.py"
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines(True)
    idx = next(i for i, l in enumerate(lines) if l.startswith("GARMENTS ="))
    app_strip = (
        "".join(lines[:idx])
        + "GARMENTS = []  # omitted: embedded base64 garment images (see git for full list)\n"
        + "".join(lines[idx + 1 :])
    )
    return "\n".join(l.rstrip() for l in app_strip.splitlines()) + "\n"


def sec(name: str, content: str) -> str:
    return f"\n\n{'=' * 72}\n### FILE: {name}\n{'=' * 72}\n\n{content}"


def build_plain_upload() -> str:
    """One UTF-8 text file you can attach to claude.ai / API as-is."""
    parts = [
        "WEARTH STUDIO — single-file code dump for review\n",
        "GARMENTS in app.py is replaced with []; base64 garment blobs omitted.\n",
        "All other listed files are full copies from the repo.\n",
    ]
    blob = "".join(parts) + sec("app.py", stripped_app())
    for fn in (
        "requirements.txt",
        "Procfile",
        "manifest.json",
        "sw.js",
        "seo_engine.py",
        "ARCHITECTURE.md",
        "index.html",
        "meta_publish_test.ps1",
        "wearth_diagnose.ps1",
    ):
        fp = ROOT / fn
        if fp.exists():
            blob += sec(fn, fp.read_text(encoding="utf-8", errors="replace"))
    return blob


def main():
    plain = build_plain_upload()
    UPLOAD_TXT.write_text(plain, encoding="utf-8", newline="\n")

    # Small LZMA bundle (same ~20KB target as before) for email-sized shares
    manifest = (
        "\n\n# ===BUNDLE MANIFEST===\n"
        "Full multi-file text: wearth_studio_FOR_CLAUDE_UPLOAD.txt (upload that to Claude).\n"
        "This .lzma file is a smaller subset for tight size limits.\n"
        "GARMENTS in app.py replaced with []; restore from git for embedded garment images."
    )
    blob = stripped_app() + manifest
    for fn in ("requirements.txt", "Procfile", "manifest.json", "sw.js"):
        blob += sec(fn, (ROOT / fn).read_text(encoding="utf-8"))
    blob += sec("ARCHITECTURE.md (first 1500 chars)", (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")[:1500])
    blob += sec("seo_engine.py (first 900 chars)", (ROOT / "seo_engine.py").read_text(encoding="utf-8")[:900])

    raw = blob.encode("utf-8")
    packed = lzma.compress(raw, preset=9)
    OUT_LZMA.write_bytes(packed)

    README.write_text(
        "wearth_studio_FOR_CLAUDE_UPLOAD.txt\n"
        "====================================\n"
        "Plain UTF-8: attach this file directly to Claude (no Python, no decompression).\n\n"
        "wearth_studio_for_claude.lzma\n"
        "=============================\n"
        "Smaller LZMA bundle for tight size limits; decompress per earlier instructions.\n\n"
        f"UPLOAD.txt size: {UPLOAD_TXT.stat().st_size} bytes\n"
        f".lzma size: {len(packed)} bytes\n",
        encoding="utf-8",
    )
    print(f"Wrote {UPLOAD_TXT.name} ({UPLOAD_TXT.stat().st_size} bytes)")
    print(f"Wrote {OUT_LZMA.name} ({len(packed)} bytes), {README.name}")


if __name__ == "__main__":
    main()
