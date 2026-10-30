"""Zweites, unabhängiges Test-Shooting (nicht zum Kalibrieren benutzt): andere Motive,
stärkeres Verwackeln aus der Hand, Rauschen (hohe ISO), Produkt auf Weiß, leichte Unschärfe.

Aufruf: python make_holdout.py <quellordner> <zielordner>
"""

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from make_testshoot import Shoot, load, jitter, defocus, shake, crop  # noqa: E402


def noisy(im, sigma):
    out = im.astype(np.float32) + np.random.default_rng(3).normal(0, sigma, im.shape)
    return np.clip(out, 0, 255).astype(np.uint8)


def sharp_product(size=(2400, 1600)):
    """Gestochen scharfes Freisteller-Motiv (Bauteil mit Bohrungen, Kanten, Gravur) auf Weiß."""
    W, H = size
    im = np.full((H, W, 3), 246, np.uint8)
    cx, cy = W // 2, H // 2
    cv2.rectangle(im, (cx - 520, cy - 300), (cx + 520, cy + 300), (90, 95, 105), -1, cv2.LINE_AA)
    cv2.rectangle(im, (cx - 500, cy - 280), (cx + 500, cy + 280), (150, 155, 165), -1, cv2.LINE_AA)
    for dx in (-380, 380):
        for dy in (-170, 170):
            cv2.circle(im, (cx + dx, cy + dy), 46, (40, 40, 45), -1, cv2.LINE_AA)
            cv2.circle(im, (cx + dx, cy + dy), 30, (200, 200, 205), -1, cv2.LINE_AA)
    cv2.circle(im, (cx, cy), 150, (70, 72, 80), 6, cv2.LINE_AA)
    for k in range(0, 360, 15):
        a = np.deg2rad(k)
        cv2.line(im, (int(cx + 150 * np.cos(a)), int(cy + 150 * np.sin(a))),
                 (int(cx + 190 * np.cos(a)), int(cy + 190 * np.sin(a))), (60, 60, 66), 3, cv2.LINE_AA)
    cv2.putText(im, "PC-4711  M8 x 1.25", (cx - 330, cy + 250), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (30, 30, 35), 3, cv2.LINE_AA)
    return im


def product_on_white(obj, size=(2400, 1600), scale=0.55):
    canvas = np.full((size[1], size[0], 3), 245, np.uint8)
    h, w = obj.shape[:2]
    f = scale * size[1] / h
    o = cv2.resize(obj, (int(w * f), int(h * f)), interpolation=cv2.INTER_CUBIC)
    o = cv2.GaussianBlur(o, (0, 0), 0.5)
    y0, x0 = (size[1] - o.shape[0]) // 2, (size[0] - o.shape[1]) // 2
    canvas[y0:y0 + o.shape[0], x0:x0 + o.shape[1]] = o
    return canvas


def hand(im):
    return jitter(im, shift=0.03, rot=1.5, expo=0.10, noise=3.0)


def build(src: Path, out: Path):
    S = Shoot(out)
    S.n = 2000
    boat2 = cv2.resize(load(src / "boat2.jpg"), (2400, 1600), interpolation=cv2.INTER_AREA)
    news2 = load(src / "newspaper2.jpg")
    buda3 = load(src / "budapest3.jpg")
    a1 = load(src / "a1.png")
    starry = load(src / "starry_night.jpg")
    baboon = load(src / "baboon.jpg")
    biden = load(src / "biden.jpg")
    two = load(src / "two_people.jpg")

    # Produkt auf Weiß (wenig Struktur), 3x aus der Hand, letzter gewinnt
    prod = sharp_product()
    for i in range(3):
        S.shot(hand(prod), "W", "pick" if i == 2 else "notpick", "Produkt auf Weiß, aus der Hand")
    S.pause(2)
    # Gleicher Winkel, große Handverwacklung, mittleres Bild leicht unscharf (Sigma 1.5)
    base = crop(load(src / "boat2.jpg"), 0.5, 0.4, 0.55, resize=False)
    S.shot(hand(base), "B2", "notpick", "Wiederholung")
    S.shot(defocus(hand(base), 1.5), "B2", "notpick", "leicht unscharf (1.5)")
    S.shot(hand(base), "B2", "pick", "letzter scharfer")
    S.pause(2)
    # Hohe ISO: scharf+Rauschen vs. unscharf+Rauschen
    S.shot(noisy(hand(news2), 10), "N", "notpick", "ISO-Rauschen scharf")
    S.shot(noisy(defocus(hand(news2), 2.5), 10), "N", "reject", "ISO-Rauschen und unscharf")
    S.shot(noisy(hand(news2), 10), "N", "pick", "ISO-Rauschen scharf, letzter")
    S.pause(3)
    # Einzelbilder, verschiedene Motive
    S.shot(buda3, "S1", "pick", "Architektur")
    S.shot(a1, "S2", "pick", "Innenraum")
    S.shot(starry, "S3", "pick", "Gemälde/Detail")
    S.shot(baboon, "S4", "pick", "Tier/Textur")
    S.pause(2)
    # Verwackelt diagonal, Einzelbild
    S.shot(shake(buda3, 15, 45), "S5", "reject", "Einzelbild diagonal verwackelt")
    S.pause(2)
    # Wiederholung nach 8 Minuten (Licht umgebaut), gleiches Motiv -> eine Serie, letzter gewinnt
    S.shot(hand(a1), "L", "notpick", "vor Lichtumbau")
    S.pause(8)
    S.shot(jitter(a1, expo=0.2), "L", "pick", "nach Lichtumbau, letzter")
    S.pause(15)
    # Porträts
    S.shot(biden, "P1", "pick", "Porträt")
    S.shot(hand(two), "P2", "notpick", "Doppelporträt 1")
    S.shot(hand(two), "P2", "pick", "Doppelporträt 2 (letzter)")
    S.shot(defocus(hand(two), 2.0), "P2", "reject", "Doppelporträt unscharf")
    import json
    (out / "_truth.json").write_text(json.dumps(S.truth, indent=1, ensure_ascii=False))
    print(f"{len(S.truth)} Bilder geschrieben nach {out}")


if __name__ == "__main__":
    build(Path(sys.argv[1]), Path(sys.argv[2]))
