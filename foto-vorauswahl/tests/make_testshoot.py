"""Erzeugt ein realistisches Test-"Shooting" mit bekannter Soll-Auswahl.

Basis sind echte Fotos/Videobilder (OpenCV-Beispieldaten, Hamilton-Clip aus face_recognition).
Daraus werden typische Shooting-Situationen gebaut: Wiederholungen aus gleichem Winkel mit leichtem
Verwackeln, unscharfe/verwackelte Auslösungen, Perspektivwechsel, Hoch-/Querformat, Fehlbelichtung,
Personen-Serien mit Blinzeln.

Aufruf: python make_testshoot.py <quellordner> <frames-ordner> <zielordner>
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

import os
rng = np.random.default_rng(int(os.environ.get("SEED", "7")))


def load(p):
    im = cv2.imread(str(p))
    if im is None:
        raise FileNotFoundError(p)
    return im


def jitter(im, shift=0.01, rot=0.4, expo=0.05, noise=2.0):
    """Wiederholungsschuss aus der Hand: minimal verschoben/gedreht, Belichtung leicht anders."""
    h, w = im.shape[:2]
    dx, dy = rng.uniform(-shift, shift) * w, rng.uniform(-shift, shift) * h
    M = cv2.getRotationMatrix2D((w / 2, h / 2), rng.uniform(-rot, rot), 1.0 + rng.uniform(0, shift))
    M[:, 2] += (dx, dy)
    out = cv2.warpAffine(im, M, (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT)
    out = out.astype(np.float32) * (1 + rng.uniform(-expo, expo))
    out += rng.normal(0, noise, out.shape)
    return np.clip(out, 0, 255).astype(np.uint8)


def defocus(im, sigma):
    return cv2.GaussianBlur(im, (0, 0), sigma)


def shake(im, length, angle=0):
    k = np.zeros((length, length), np.float32)
    k[length // 2, :] = 1.0 / length
    M = cv2.getRotationMatrix2D((length / 2 - 0.5, length / 2 - 0.5), angle, 1)
    k = cv2.warpAffine(k, M, (length, length))
    k /= k.sum()
    return cv2.filter2D(im, -1, k)


def crop(im, f, cx=0.5, cy=0.5, resize=True):
    """Bildausschnitt; resize=False behält die Original-Pixel (wie ein echtes Tele/Zoom-Foto)."""
    h, w = im.shape[:2]
    nw, nh = int(w * f), int(h * f)
    x0 = int(min(max(0, cx * w - nw / 2), w - nw))
    y0 = int(min(max(0, cy * h - nh / 2), h - nh))
    c = im[y0:y0 + nh, x0:x0 + nw]
    return cv2.resize(c, (w, h), interpolation=cv2.INTER_CUBIC) if resize else c.copy()


def perspective(im, amount):
    h, w = im.shape[:2]
    a = amount
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[w * a, h * a * 0.6], [w * (1 - a * 0.2), 0], [w, h], [w * a * 0.4, h * (1 - a)]])
    return cv2.warpPerspective(im, cv2.getPerspectiveTransform(src, dst), (w, h), borderMode=cv2.BORDER_REFLECT)


class Shoot:
    def __init__(self, out: Path):
        self.out = out
        out.mkdir(parents=True, exist_ok=True)
        self.t = datetime(2026, 10, 28, 9, 0, 0)
        self.n = 1000
        self.truth = []

    def shot(self, im, series, expect, note, dt=4.0):
        self.t += timedelta(seconds=dt)
        self.n += 1
        name = f"PC_{self.n:04d}.jpg"
        pil = Image.fromarray(cv2.cvtColor(im, cv2.COLOR_BGR2RGB))
        exif = Image.Exif()
        exif[0x0110] = "Testkamera"
        exif.get_ifd(0x8769)[0x9003] = self.t.strftime("%Y:%m:%d %H:%M:%S")
        pil.save(self.out / name, quality=93, exif=exif.tobytes())
        self.truth.append(dict(file=name, series=series, expect=expect, note=note))

    def pause(self, minutes):
        self.t += timedelta(minutes=minutes)


def build(src: Path, frames: Path, out: Path):
    S = Shoot(out)
    boat = [load(src / f"boat{i}.jpg") for i in (1, 2, 3)]
    boat = [cv2.resize(b, (2400, 1600), interpolation=cv2.INTER_AREA) for b in boat]
    news = load(src / "newspaper1.jpg")
    s1 = load(src / "s1.jpg")
    buda = load(src / "budapest1.jpg")
    fruits = load(src / "fruits.jpg")
    building = load(src / "building.jpg")
    obama = load(src / "obama.jpg")
    graf = load(src / "graf1.png")

    # 1) Produkt, gleicher Winkel, 4 Wiederholungen -> letzter Schuss
    for i in range(4):
        S.shot(jitter(news), "A", "pick" if i == 3 else "notpick", "Wiederholung gleicher Winkel")
    S.pause(1)
    # 2) gleicher Winkel 4x, letzter Schuss unscharf -> dritter gewinnt, letzter raus
    base = crop(load(src / "boat1.jpg"), 0.6, 0.45, 0.5, resize=False)
    for i in range(3):
        S.shot(jitter(base), "B", "pick" if i == 2 else "notpick", "Wiederholung")
    S.shot(defocus(jitter(base), 3.0), "B", "reject", "letzter Schuss Fokus daneben")
    S.pause(1)
    # 3) Serie mit verwackeltem Bild in der Mitte
    base = s1
    S.shot(jitter(base), "C", "notpick", "Serie")
    S.shot(shake(jitter(base), 13, 0), "C", "reject", "verwackelt (13 px)")
    S.shot(jitter(base), "C", "pick", "letzter scharfer Schuss")
    S.pause(2)
    # 4) Schwenk: drei verschiedene Bildausschnitte derselben Szene -> drei Einzelbilder
    for i, b in enumerate(boat):
        S.shot(b, f"D{i}", "pick", "anderer Blickwinkel", dt=8)
    S.pause(2)
    # 5) Totale + Detail desselben Motivs -> zwei verschiedene Einstellungen
    S.shot(buda, "E1", "notpick", "Totale")
    S.shot(jitter(buda), "E1", "pick", "Totale, Wiederholung = letzter Schuss")
    S.shot(crop(buda, 0.45, 0.6, 0.5, resize=False), "E2", "pick", "Detail (Zoom)")
    S.pause(3)
    # 6) Perspektivwechsel deutlich (anderer Winkel) -> getrennte Serien
    S.shot(graf, "F1", "pick", "Winkel 1")
    S.shot(perspective(graf, 0.25), "F2", "pick", "deutlich anderer Winkel")
    S.pause(2)
    # 7) Hoch- vs. Querformat desselben Motivs
    S.shot(fruits, "G1", "pick", "Querformat")
    S.shot(cv2.rotate(crop(fruits, 0.7, resize=False), cv2.ROTATE_90_CLOCKWISE), "G2", "pick", "Hochformat")
    S.pause(2)
    # 8) Fehlauslösung: fast schwarz (Blitz nicht ausgelöst)
    S.shot((building * 0.04).astype(np.uint8), "H0", "reject", "Blitz nicht ausgelöst")
    S.shot(building, "H", "pick", "korrekt belichtet")
    S.pause(2)
    # 9) Einzelbild leicht unscharf vs. stark unscharf
    S.shot(defocus(jitter(news), 3.5), "I", "reject", "Einzelbild stark unscharf")
    S.pause(5)
    # 10) A-B-A: Produkt X, kurz Produkt Y, dann wieder X -> letztes X gewinnt
    S.shot(jitter(s1), "X", "notpick", "Produkt X")
    S.shot(jitter(buda), "Y", "pick", "Produkt Y")
    S.shot(jitter(s1), "X", "pick", "wieder Produkt X, letzter Schuss")
    S.pause(5)
    # 11) Porträt-Einzelbild
    S.shot(obama, "P0", "pick", "Porträt, Augen offen")
    S.pause(5)
    # 12) Personen-Serie (Videobilder): Augen zu in h1764, Blick nach unten in h1392
    for f in ("h1749", "h1752", "h1755", "h1758", "h1761", "h1764"):
        S.shot(load(frames / f"{f}.jpg"), "Q", "any", "Personen-Serie", dt=0.5)
    S.pause(3)
    for f in ("h1386", "h1389", "h1392", "h1395"):
        S.shot(load(frames / f"{f}.jpg"), "R", "any", "Personen-Serie Blick nach unten", dt=0.5)
    S.pause(3)
    for f in ("h0750", "h0753", "h0756"):
        S.shot(load(frames / f"{f}.jpg"), "T", "any", "Publikum lacht", dt=0.5)
    (out / "_truth.json").write_text(json.dumps(S.truth, indent=1, ensure_ascii=False))
    print(f"{len(S.truth)} Bilder geschrieben nach {out}")


if __name__ == "__main__":
    build(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
