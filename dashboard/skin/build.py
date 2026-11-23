#!/usr/bin/env python3
"""Assemble dashboard/index.html from the Plain page and the Thalamus (hologram) skin.

parts: dashboard/skin/plain.html (the Plain page, with a <!--THALAMUS_BUNDLE--> marker) and
       dashboard/holo/{brain.js, holo.js, sector.js, texts.js, chat.js, holo.css, holo.html} (the skin, Phases 18/19).
The old Thalamus skin (engine.js, skin.js and its CSS) was retired on 2026-11-10.
Run: python3 dashboard/skin/build.py   (add --check to fail if index.html is out of date)
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "index.html"


def js_str(text):
    # safe inside an inline <script>: no literal "</" sequences
    return json.dumps(text).replace("</", "<\\/")


def build():
    hread = lambda n: (HERE.parent / "holo" / n).read_text(encoding="utf-8")
    holo = hread("brain.js") + "\n" + hread("holo.js") + "\n" + hread("sector.js") + "\n" + hread("texts.js") + "\n" + hread("chat.js")
    for tag, val in (("HCSS", hread("holo.css")), ("HHTML", hread("holo.html"))):
        # tolerant of a formatter adding spaces around the marker
        holo, n = re.subn(r'/\*__' + tag + r'__\*/\s*""', lambda _m, v=val: js_str(v), holo)
        if n != 1:
            raise SystemExit("holo.js needs exactly one /*__" + tag + "__*/ marker")
    bundle = "<script>\n(function () {\n" + holo + "\n})();\n</script>"
    page = (HERE / "plain.html").read_text(encoding="utf-8")
    marker = "<!--THALAMUS_BUNDLE-->"
    if page.count(marker) != 1:
        raise SystemExit("plain.html needs exactly one " + marker)
    return page.replace(marker, bundle)


if __name__ == "__main__":
    html = build()
    if "--check" in sys.argv:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == html
        print("index.html is up to date" if ok else "index.html is OUT OF DATE: run python3 dashboard/skin/build.py")
        sys.exit(0 if ok else 1)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({len(html):,} bytes)")
