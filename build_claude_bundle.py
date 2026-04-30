"""Build wearth_studio_for_claude.lzma — single LZMA bundle for Claude (~19 KB compressed).

Target: under 20,000 bytes (decimal). GARMENTS line stripped from app.py.
Run: python build_claude_bundle.py
"""
import lzma
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "wearth_studio_for_claude.lzma"
README = ROOT / "wearth_studio_for_claude_HOWTO.txt"


def main():
    p = ROOT / "app.py"
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines(True)
    idx = next(i for i, l in enumerate(lines) if l.startswith("GARMENTS ="))
    app_strip = "".join(lines[:idx]) + "GARMENTS = []  # omitted: embedded base64 garment images\n" + "".join(lines[idx + 1 :])
    app_strip = "\n".join(l.rstrip() for l in app_strip.splitlines()) + "\n"

    def sec(name: str, content: str) -> str:
        return f"\n\n# ===FILE: {name}===\n\n{content}"

    manifest = (
        "\n\n# ===BUNDLE MANIFEST===\n"
        "Inlined below: requirements.txt, Procfile, manifest.json, sw.js, start of ARCHITECTURE.md, start of seo_engine.py.\n"
        "Not inlined (get from repo): index.html, meta_publish_test.ps1, wearth_diagnose.ps1, full ARCHITECTURE/seo_engine.\n"
        "GARMENTS in app.py replaced with []; restore from git for embedded garment images."
    )
    blob = app_strip + manifest
    for fn in ("requirements.txt", "Procfile", "manifest.json", "sw.js"):
        blob += sec(fn, (ROOT / fn).read_text(encoding="utf-8"))
    blob += sec("ARCHITECTURE.md (first 1500 chars)", (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")[:1500])
    blob += sec("seo_engine.py (first 900 chars)", (ROOT / "seo_engine.py").read_text(encoding="utf-8")[:900])

    raw = blob.encode("utf-8")
    packed = lzma.compress(raw, preset=9)
    OUT.write_bytes(packed)

    README.write_text(
        "wearth_studio_for_claude.lzma\n"
        "===============================\n"
        "Single-file LZMA-compressed UTF-8 text bundle for code review.\n"
        "GARMENTS = [...] in app.py was replaced by an empty list + comment (base64 assets omitted).\n"
        "Some large files are truncated; see full repo for complete index.html, full seo_engine, etc.\n\n"
        "Decompress (Python):\n"
        "  import lzma, pathlib\n"
        "  p = pathlib.Path('wearth_studio_for_claude.lzma')\n"
        "  pathlib.Path('wearth_studio_for_claude_DECOMPRESSED.txt').write_bytes(lzma.open(p, 'rb').read())\n\n"
        "Decompress (Windows with WSL / xz):\n"
        "  xz -d -k wearth_studio_for_claude.lzma   # may need renaming to .xz depending on tool\n\n"
        f"Compressed size: {len(packed)} bytes (kept under 20,000 for tight limits)\n"
        f"Uncompressed text size: {len(raw)} bytes\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUT.name} ({len(packed)} bytes), {README.name}")


if __name__ == "__main__":
    main()
