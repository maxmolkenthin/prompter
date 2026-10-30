"""Lädt die KI-Modelle (Google MediaPipe, frei nutzbar, ca. 16 MB) einmalig herunter.

Aufruf: python -m colada_cull.setup_models [zielordner]
"""

import sys
import urllib.request
from pathlib import Path

from .analysis import MODEL_DIR, MODEL_URLS


def main(target=None):
    target = Path(target or MODEL_DIR)
    target.mkdir(parents=True, exist_ok=True)
    for name, url in MODEL_URLS.items():
        dest = target / name
        if dest.exists() and dest.stat().st_size > 10_000:
            print(f"vorhanden: {name}")
            continue
        print(f"lade {name} …")
        tmp = dest.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(dest)
    print(f"Modelle in {target}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
