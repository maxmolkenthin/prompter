#!/usr/bin/env python3
"""Baut aus index.html (Quelle, auch für claude.ai) die eigenständige Web-App in standalone/.

Aufruf: python3 build.py   (braucht Node.js; esbuild wird bei Bedarf per npx geholt)
Erzeugt index.html, sw.js, manifest.webmanifest, die App-Symbole und die Bibliotheken.

Der App-Code und PeerJS werden mit esbuild auf Safari 12 heruntergebrochen, damit
auch alte iPads (iOS 12) die App ausführen. Quellen der Bibliotheken in vendor/:
PeerJS 1.5.4 (MIT) und pako_inflate 2.1.0 (MIT/Zlib).
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
# Im GitHub-Repo liegt die Quelle in src/ und die gebaute App in der Wurzel,
# im Arbeitsordner liegt die Quelle in der Wurzel und die App in standalone/.
if (ROOT / "src" / "index.html").exists():
    SRC_PATH, OUT = ROOT / "src" / "index.html", ROOT
else:
    SRC_PATH, OUT = ROOT / "index.html", ROOT / "standalone"
SRC = SRC_PATH.read_text(encoding="utf-8")
VENDOR = ROOT / "vendor"
TARGET = "safari12"


def esbuild(code: str) -> str:
    """Übersetzt JavaScript für ältere Browser (Syntax, keine fehlenden Funktionen)."""
    cmd = os.environ.get("ESBUILD")
    cmd = [cmd] if cmd else ["npx", "--yes", "esbuild@0.21.5"]
    out = subprocess.run(cmd + ["--loader=js", f"--target={TARGET}", "--log-level=warning"],
                         input=code, capture_output=True, text=True, check=True)
    return out.stdout


def legacy_html(src: str) -> str:
    """Ersetzt das große Inline-Skript der App durch seine Safari-12-Fassung."""
    start = src.index("<script>\n(() => {")
    end = src.index("</script>", start)
    body = src[start + len("<script>"):end]
    return src[:start] + "<script>\n" + esbuild(body) + src[end:]

HEAD = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0e1013">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Prompter">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" type="image/png" href="icon-192.png">
<style>
/* Ersatz für das Grundgerüst, das claude.ai sonst mitliefert */
:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
body{margin:0}
img{max-width:100%}
</style>
<script src="peerjs.min.js"></script>
<script src="pako_inflate.min.js"></script>
</head>
<body>
"""

FOOT = """
<script>
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}
</script>
</body>
</html>
"""


def icon(size: int) -> Image.Image:
    """Dunkle Fläche, rote Leselinie mit Pfeilen, weiße Textzeilen."""
    s = size
    im = Image.new("RGB", (s, s), "#0e1013")
    d = ImageDraw.Draw(im)
    white = (238, 241, 244)
    dim = (110, 118, 130)
    red = (255, 75, 43)
    x0, x1 = int(s * 0.22), int(s * 0.78)
    h = max(2, int(s * 0.055))
    rows = [(0.28, 0.85, dim), (0.40, 1.0, dim), (0.54, 1.0, white), (0.66, 0.9, white), (0.78, 0.6, white)]
    for y, w, col in rows:
        yy = int(s * y)
        d.rounded_rectangle([x0, yy, x0 + int((x1 - x0) * w), yy + h], radius=h // 2, fill=col)
    ly = int(s * 0.485)
    a = int(s * 0.07)
    d.polygon([(int(s * 0.06), ly - a), (int(s * 0.06) + int(a * 1.3), ly), (int(s * 0.06), ly + a)], fill=red)
    d.polygon([(int(s * 0.94), ly - a), (int(s * 0.94) - int(a * 1.3), ly), (int(s * 0.94), ly + a)], fill=red)
    return im


def main() -> None:
    OUT.mkdir(exist_ok=True)
    html = HEAD + legacy_html(SRC) + FOOT
    (OUT / "peerjs.min.js").write_text(esbuild((VENDOR / "peerjs-1.5.4.min.js").read_text(encoding="utf-8")), encoding="utf-8")
    shutil.copyfile(VENDOR / "pako_inflate-2.1.0.min.js", OUT / "pako_inflate.min.js")
    (OUT / "index.html").write_text(html, encoding="utf-8")

    icon(512).save(OUT / "icon-512.png")
    icon(192).save(OUT / "icon-192.png")
    icon(180).save(OUT / "apple-touch-icon.png")

    manifest = {
        "name": "Colada Prompter",
        "short_name": "Prompter",
        "lang": "de",
        "start_url": "./",
        "scope": "./",
        "display": "fullscreen",
        "background_color": "#0e1013",
        "theme_color": "#0e1013",
        "icons": [
            {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }
    (OUT / "manifest.webmanifest").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # Cache-Version aus dem Inhalt, damit jede neue Fassung den Offline-Speicher erneuert.
    libs = "".join((OUT / f).read_text(encoding="utf-8") for f in ("peerjs.min.js", "pako_inflate.min.js"))
    digest = hashlib.sha256((html + libs).encode()).hexdigest()[:10]
    sw = (ROOT / "sw.template.js").read_text(encoding="utf-8").replace("__VERSION__", digest)
    (OUT / "sw.js").write_text(sw, encoding="utf-8")
    print("gebaut:", digest)


if __name__ == "__main__":
    main()
