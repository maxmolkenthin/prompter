"""Sterne/Farblabel als XMP-Sidecar schreiben (Ordner-Modus, vor dem Import in Capture One).

Vorhandene XMP-Dateien (z. B. von der Kamera oder aus Capture One) werden ergänzt, nicht ersetzt.
"""

from __future__ import annotations

import re
from pathlib import Path

LABELS = {0: "", 1: "Red", 2: "Orange", 3: "Yellow", 4: "Green", 5: "Blue", 6: "Pink", 7: "Purple"}

TEMPLATE = """<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Colada Cull">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmp:Rating="{rating}"{label}/>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>
"""


def sidecar_path(image: Path) -> Path:
    return image.with_suffix(".xmp")


def _set_prop(text: str, name: str, value: str | None) -> str:
    """Setzt xmp:<name> als Attribut oder Element; value None entfernt es."""
    attr = re.compile(rf'(\s)xmp:{name}="[^"]*"')
    elem = re.compile(rf"<xmp:{name}>.*?</xmp:{name}>|<xmp:{name}\s*/>", re.S)
    if value is None:
        text = attr.sub(r"\1", text)
        return elem.sub("", text)
    if attr.search(text):
        return attr.sub(lambda m: f'{m.group(1)}xmp:{name}="{value}"', text, count=1)
    if elem.search(text):
        return elem.sub(f"<xmp:{name}>{value}</xmp:{name}>", text, count=1)
    # neues Attribut an die erste rdf:Description hängen
    m = re.search(r"<rdf:Description\b", text)
    if not m:
        raise ValueError("keine rdf:Description gefunden")
    insert = m.end()
    extra = f' xmp:{name}="{value}"'
    if "xmlns:xmp=" not in text:
        extra = ' xmlns:xmp="http://ns.adobe.com/xap/1.0/"' + extra
    return text[:insert] + extra + text[insert:]


def write_sidecar(image: str | Path, rating: int, color: int) -> Path:
    image = Path(image)
    sc = sidecar_path(image)
    label = LABELS.get(color, "")
    if sc.exists():
        text = sc.read_text(encoding="utf-8", errors="replace")
        text = _set_prop(text, "Rating", str(rating))
        text = _set_prop(text, "Label", label or None)
    else:
        text = TEMPLATE.format(rating=rating, label=f'\n    xmp:Label="{label}"' if label else "")
    sc.write_text(text, encoding="utf-8")
    return sc


def read_sidecar(image: str | Path) -> tuple[int | None, str | None]:
    sc = sidecar_path(Path(image))
    if not sc.exists():
        return None, None
    text = sc.read_text(encoding="utf-8", errors="replace")
    r = re.search(r'xmp:Rating(?:="|>)(-?\d+)', text)
    lab = re.search(r'xmp:Label(?:="|>)([^"<]*)', text)
    return (int(r.group(1)) if r else None, lab.group(1) if lab else None)
