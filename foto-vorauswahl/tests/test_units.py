"""Einzeltests ohne KI-Modelle: XMP-Ergänzung, Drehung, Aufnahmezeit, Serien-Logik.

Aufruf: python -m pytest tests/test_units.py   (oder: python tests/test_units.py)
"""

import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))

from colada_cull import xmp  # noqa: E402
from colada_cull.analysis import ImageMetrics, Face  # noqa: E402
from colada_cull.culling import Item, Settings, select, PICK, REJECT, ALT  # noqa: E402
from colada_cull.loader import load_preview, capture_time, list_images  # noqa: E402

CAMERA_XMP = """<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmp:CreatorTool="Kamera">
   <xmp:Rating>5</xmp:Rating>
   <dc:creator><rdf:Seq><rdf:li>Gina</rdf:li></rdf:Seq></dc:creator>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>"""


def test_xmp_new_and_merge():
    with tempfile.TemporaryDirectory() as d:
        img = Path(d) / "IMG_0001.CR3"
        img.write_bytes(b"x")
        xmp.write_sidecar(img, 3, 4)
        assert xmp.read_sidecar(img) == (3, "Green")
        xmp.write_sidecar(img, 0, 1)
        assert xmp.read_sidecar(img) == (0, "Red")
        xmp.write_sidecar(img, 1, 0)
        assert xmp.read_sidecar(img) == (1, None)
        # vorhandene Datei (Element-Schreibweise) wird ergänzt, andere Metadaten bleiben
        (Path(d) / "IMG_0001.xmp").write_text(CAMERA_XMP)
        xmp.write_sidecar(img, 3, 4)
        text = (Path(d) / "IMG_0001.xmp").read_text()
        assert xmp.read_sidecar(img) == (3, "Green")
        assert "Gina" in text and "CreatorTool" in text and text.count("Rating") == 2  # <xmp:Rating> öffnend+schließend


def test_orientation_and_time():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "hoch.jpg"
        im = Image.fromarray(np.zeros((400, 600, 3), np.uint8))
        exif = Image.Exif()
        exif[0x0112] = 6  # 90° gedreht
        exif.get_ifd(0x8769)[0x9003] = "2026:10:28 09:15:02"
        exif.get_ifd(0x8769)[0x9291] = "45"  # SubSecTimeOriginal
        im.save(p, exif=exif.tobytes())
        rgb, _ = load_preview(p)
        assert rgb.shape[:2] == (600, 400), rgb.shape
        dt, src = capture_time(p)
        assert dt == datetime(2026, 10, 28, 9, 15, 2, 450000) and src == "exif", (dt, src)


def test_list_images_raw_jpeg_pairs():
    with tempfile.TemporaryDirectory() as d:
        for n in ("A_0001.CR3", "A_0001.JPG", "A_0002.jpg", "A_0010.NEF", "._A_0003.CR3", "notiz.txt"):
            (Path(d) / n).write_bytes(b"x")
        names = [p.name for p in list_images(d)]
        assert names == ["A_0001.CR3", "A_0002.jpg", "A_0010.NEF"], names


def _met(name, emb, tiny, sharp=0.3, faces=()):
    return ImageMetrics(path=name, width=2000, height=1333, sharpness=sharp, sharpness_global=sharp * 0.6,
                        brightness=0.45, p99=0.9, embedding=list(emb), tiny=list(tiny), faces=list(faces))


def _face(open_):
    return Face(box=(0.4, 0.2, 0.2, 0.3), size=0.2, det_score=0.95, eyes_open=open_, blink=1 - open_, yaw=0, pitch=0,
                gaze_off=0.1, looking=0.8, sharpness=0.3, landmarks_ok=True)


def test_last_shot_wins_and_blur_rejected():
    rng = np.random.default_rng(0)
    e1 = rng.normal(size=64); e1 /= np.linalg.norm(e1)
    e2 = rng.normal(size=64); e2 /= np.linalg.norm(e2)
    t1 = rng.random(256)
    t2 = rng.random(256)
    t0 = datetime(2026, 1, 1, 10)
    items = []
    specs = [(e1, t1, 0.30), (e1, t1, 0.31), (e1, t1, 0.12),   # Serie 1: letzter unscharf
             (e2, t2, 0.28), (e2, t2, 0.27)]                    # Serie 2: letzter gewinnt
    for i, (e, t, sh) in enumerate(specs):
        items.append(Item(index=i, path=f"/x/IMG_{i}.jpg", time=t0 + timedelta(seconds=5 * i), met=_met(f"/x/IMG_{i}.jpg", e, t, sh)))
    groups = select(items, Settings())
    assert len(groups) == 2
    assert [it.status for it in items] == [ALT, PICK, REJECT, ALT, PICK], [it.status for it in items]


def test_closed_eyes():
    rng = np.random.default_rng(1)
    e = rng.normal(size=64); e /= np.linalg.norm(e)
    t = rng.random(256)
    t0 = datetime(2026, 1, 1, 10)
    opens = [0.9, 0.95, 0.1]  # letzter Schuss: Augen zu
    items = [Item(index=i, path=f"/x/P_{i}.jpg", time=t0 + timedelta(seconds=i),
                  met=_met(f"/x/P_{i}.jpg", e, t, 0.3, faces=[_face(o)])) for i, o in enumerate(opens)]
    select(items, Settings(mode="people"))
    assert [it.status for it in items] == [ALT, PICK, REJECT], [(it.status, it.reason) for it in items]
    # Einzelbild mit geschlossenen Augen -> raus
    single = [Item(index=0, path="/x/S.jpg", time=t0, met=_met("/x/S.jpg", e, t, 0.3, faces=[_face(0.05)]))]
    select(single, Settings())
    assert single[0].status == REJECT


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
