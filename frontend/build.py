"""Assemble frontend/src/* into one self-contained frontend/index.html (same shape as the design export).

    python frontend/build.py

To bring in a new design export from the UI team:
    python frontend/build.py --split path/to/export.html     (overwrites src/template.html and src/style.css only;
                                                              src/logic.js keeps the backend wiring)
"""
import argparse
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"


def build():
    r = lambda name: (SRC / name).read_text(encoding="utf-8")  # noqa: E731
    tpl = r("template.html")
    if "</script" in tpl.lower():
        raise SystemExit("template.html must not contain a </script> tag")
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SafeSphere</title>
<style>{r("style.css")}</style>
</head>
<body>
<div id="app"></div>
<script>{r("vendor/react.production.min.js")}</script>
<script>{r("vendor/react-dom.production.min.js")}</script>
<script type="text/plain" id="tpl">{tpl}</script>
<script>{r("renderer.js")}</script>
<script>{r("api.js")}</script>
<script>{r("logic.js")}</script>
</body>
</html>
"""
    out = HERE / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html) // 1024} KB)")


def split(export):
    t = Path(export).read_text(encoding="utf-8")
    scripts = re.findall(r"<script([^>]*)>(.*?)</script>", t, re.S)
    tpl = next(body for attrs, body in scripts if 'id="tpl"' in attrs)
    (SRC / "template.html").write_text(tpl, encoding="utf-8")
    (SRC / "style.css").write_text(re.search(r"<style[^>]*>(.*?)</style>", t, re.S).group(1), encoding="utf-8")
    print("updated src/template.html and src/style.css; re-apply the two small template edits "
          "(conn chip in the header, met.sampleText) if the new export dropped them")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", help="design export .html to take template/style from")
    a = ap.parse_args()
    if a.split:
        split(a.split)
    build()
