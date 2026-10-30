"""Serien bilden (gleiches Motiv, gleicher Winkel) und pro Serie die Vorauswahl treffen."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from .analysis import ImageMetrics, Face

PICK, ALT, REJECT, SKIP = "pick", "alt", "reject", "skip"

MODES = {
    # faces: Gesichter auswerten · look: Gewicht "Blick in die Kamera" · eyes: Faktor auf die Augen-zu-Grenze
    "auto":        dict(faces=True,  look=0.15, eyes=1.0),
    "produkt":     dict(faces=False, look=0.0,  eyes=1.0),
    "architektur": dict(faces=False, look=0.0,  eyes=1.0),
    "prozess":     dict(faces=True,  look=0.0,  eyes=0.75),  # Reportage: Blick auf die Arbeit ist gewollt
    "people":      dict(faces=True,  look=0.35, eyes=1.0),
}

STRICTNESS = {
    #            absolute Schärfegrenze | relativ zum schärfsten Serienbild | Ähnlichkeit für "gleiche Serie"
    # sharp_rel: darunter (relativ zum schärfsten Serienbild) wird aussortiert
    # sharp_pick: mindestens so scharf (relativ) muss ein Bild sein, um als "letzter Schuss" zu gewinnen
    "locker": dict(sharp_abs=0.095, sharp_rel=0.60, sharp_pick=0.65, sim=0.91, layout=0.82, eyes=0.30),
    "normal": dict(sharp_abs=0.110, sharp_rel=0.68, sharp_pick=0.72, sim=0.90, layout=0.80, eyes=0.40),
    "streng": dict(sharp_abs=0.125, sharp_rel=0.75, sharp_pick=0.80, sim=0.87, layout=0.74, eyes=0.50),
}

MIN_FACE = 0.035  # Gesichter kleiner als 3,5 % der Bildbreite gelten als Hintergrund


@dataclass
class Settings:
    mode: str = "auto"
    strictness: str = "normal"
    picks_per_group: int = 1
    max_gap_s: float = 600.0     # max. Zeit zwischen zwei Bildern derselben Serie
    lookback_groups: int = 3      # A-B-A: späteres A wird der früheren A-Serie zugeordnet
    rating_pick: int = 3
    rating_alt: int = 1
    rating_reject: int = 0
    color_pick: int = 4           # Capture One: 0 keine, 1 rot, 2 orange, 3 gelb, 4 grün, 5 blau, 6 pink, 7 lila
    color_alt: int = 0
    color_reject: int = 1

    @property
    def m(self):
        return MODES.get(self.mode, MODES["auto"])

    @property
    def t(self):
        return STRICTNESS.get(self.strictness, STRICTNESS["normal"])


@dataclass
class Item:
    index: int                    # Position in der Eingabeliste
    path: str
    time: datetime | None
    met: ImageMetrics
    group: int = -1
    status: str = ALT
    reason: str = ""
    score: float = 0.0
    rating: int | None = 0
    color: int | None = 0
    notes: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ Ähnlichkeit

def _corr(x, y) -> float:
    x = x - x.mean()
    y = y - y.mean()
    d = float(np.linalg.norm(x) * np.linalg.norm(y))
    return float((x * y).sum() / d) if d > 1e-6 else 1.0


def _layout_corr(a: list[float], b: list[float]) -> float:
    """Korrelation der 16x16-Miniaturen; toleriert ein Pixel Versatz (~6 % des Bildes, Freihand)."""
    if not a or not b:
        return 0.0
    x = np.asarray(a, np.float32).reshape(16, 16)
    y = np.asarray(b, np.float32).reshape(16, 16)
    best = -1.0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            xs = x[max(0, dy):16 + min(0, dy), max(0, dx):16 + min(0, dx)]
            ys = y[max(0, -dy):16 + min(0, -dy), max(0, -dx):16 + min(0, -dx)]
            best = max(best, _corr(xs, ys))
    return best


def similarity(a: ImageMetrics, b: ImageMetrics) -> tuple[float, float]:
    """(Inhalt, Bildaufbau). Inhalt: Bild-Fingerabdruck per neuronalem Netz, Aufbau: Miniatur-Korrelation."""
    if a.embedding and b.embedding:
        emb = float(np.dot(np.asarray(a.embedding), np.asarray(b.embedding)))
    else:
        emb = 0.0
    return emb, _layout_corr(a.tiny, b.tiny)


def same_shot(a: ImageMetrics, b: ImageMetrics, s: Settings, burst: bool = False) -> bool:
    # Hoch- und Querformat sind nie dieselbe Einstellung
    if (a.width >= a.height) != (b.width >= b.height):
        return False
    emb, lay = similarity(a, b)
    t_sim, t_lay = s.t["sim"], s.t["layout"]
    if burst:  # Serienbild (< 2 s Abstand): Person/Maschine bewegt sich, Bild ändert sich stärker
        t_sim, t_lay = t_sim - 0.06, t_lay - 0.10
    if emb >= t_sim and lay >= t_lay:
        return True
    # sehr hohe Übereinstimmung in einem Kriterium gleicht leichte Schwäche im anderen aus
    if emb >= t_sim + 0.05 and lay >= t_lay - 0.15:
        return True
    if lay >= 0.95 and emb >= t_sim - 0.06:
        return True
    return False


# ------------------------------------------------------------------ Serien

def _gap(a: Item, b: Item) -> float:
    if a.time is None or b.time is None:
        return 0.0
    return abs((b.time - a.time).total_seconds())


def build_groups(items: list[Item], s: Settings) -> list[list[Item]]:
    order = sorted(items, key=lambda it: (it.time or datetime.min, _nat(it.path)))
    groups: list[list[Item]] = []
    for it in order:
        if it.met.error:
            groups.append([it])
            continue
        target = None
        for g in reversed(groups[-s.lookback_groups:]):
            last = g[-1]
            if last.met.error or _gap(last, it) > s.max_gap_s:
                continue
            # Ähnlich zu einem der letzten Bilder der Serie (ein verwackeltes Bild dazwischen darf
            # die Serie nicht trennen) und, gegen schleichendes Abdriften, grob ähnlich zum ersten
            burst = _gap(last, it) <= 2.0 and last.time is not None and it.time is not None
            recent = [m for m in g[-3:] if not m.met.error]
            if any(same_shot(m.met, it.met, s, burst) for m in recent) and (
                    len(g) == 1 or _loose_same(g[0].met, it.met, s)):
                target = g
                break
        if target is None:
            groups.append([it])
        else:
            target.append(it)
    for gi, g in enumerate(groups):
        for it in g:
            it.group = gi
    return groups


def _loose_same(a, b, s):
    emb, lay = similarity(a, b)
    return emb >= s.t["sim"] - 0.06 and lay >= s.t["layout"] - 0.15


def _nat(p):
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.rsplit("/", 1)[-1])]


# ------------------------------------------------------------------ Bewertung

def relevant_faces(met: ImageMetrics) -> list[Face]:
    if not met.faces:
        return []
    biggest = max(f.size for f in met.faces)
    return [f for f in met.faces if f.size >= MIN_FACE and f.size >= 0.3 * biggest]


def _eyes_closed(f: Face, s: Settings) -> bool:
    if not f.landmarks_ok:
        return False
    if abs(f.yaw) > 50:
        return False
    # Blick nach unten (z. B. aufs Werkstück) senkt die Lider -> nur eindeutig geschlossene Augen zählen
    if f.pitch > 15:
        return f.blink > 0.85
    # Lachen kneift die Augen zusammen -> großzügiger
    if f.smile > 0.5:
        return f.blink > 0.75
    return f.eyes_open < s.t["eyes"] * s.m["eyes"]


def technical_reject(it: Item, s: Settings) -> str:
    m = it.met
    # Nur echte Fehlauslösungen: Low-Key- und Freisteller-auf-Weiß-Bilder sind gewollt dunkel/hell
    if m.brightness < 0.04 and m.p99 < 0.2:
        return "fast schwarz (Fehlauslösung/Blitz nicht ausgelöst?)"
    if m.brightness > 0.97 and m.clip_high > 0.9:
        return "fast weiß (stark überbelichtet)"
    if m.sharpness < s.t["sharp_abs"]:
        return f"unscharf/verwackelt (Schärfe {m.sharpness:.2f})"
    if s.m["faces"]:
        faces = relevant_faces(m)
        big = [f for f in faces if f.size >= 0.10 and f.landmarks_ok and f.sharpness > 0]
        # Großes Gesicht im Bild, aber Gesicht selbst deutlich unscharf -> Fokus daneben
        if big and max(f.sharpness for f in big) < s.t["sharp_abs"] * 0.85 and m.sharpness < 0.2:
            return "Fokus nicht auf dem Gesicht"
    return ""


def people_score(it: Item, s: Settings) -> tuple[float | None, str]:
    """Qualität der Gesichter. Gesättigt: "offen" ist offen, kleine Messschwankungen zählen nicht.
    None = keine relevanten Gesichter im Bild."""
    faces = relevant_faces(it.met)
    if not faces:
        return None, ""
    eyes = [float(np.clip((f.eyes_open - 0.2) / 0.4, 0, 1)) if f.landmarks_ok else 1.0 for f in faces]
    look = float(np.mean([min(1.0, f.looking / 0.5) for f in faces]))
    closed = [f for f in faces if _eyes_closed(f, s)]
    score = 0.7 * min(eyes) + 0.3 * float(np.mean(eyes)) + s.m["look"] * look
    note = ""
    if closed:
        note = "Augen zu" if len(faces) == 1 else f"Augen zu ({len(closed)} von {len(faces)} Personen)"
        score -= 0.6
    return score, note


def select(items: list[Item], s: Settings) -> list[list[Item]]:
    groups = build_groups(items, s)
    for g in groups:
        _select_group(g, s)
    for it in items:
        if it.status == PICK:
            it.rating, it.color = s.rating_pick, s.color_pick
        elif it.status == REJECT:
            it.rating, it.color = s.rating_reject, s.color_reject
        elif it.status == SKIP:
            it.rating, it.color = None, None
        else:
            it.rating, it.color = s.rating_alt, s.color_alt
    return groups


def _select_group(g: list[Item], s: Settings):
    # Nicht lesbare Dateien (z. B. brandneues RAW-Format) bleiben unangetastet
    for it in g:
        if it.met.error:
            it.status, it.reason = SKIP, "nicht analysierbar – Bewertung bleibt unverändert"
    g = [it for it in g if it.status != SKIP]
    if not g:
        return
    n = len(g)
    # 1) technisch unbrauchbar
    for it in g:
        r = technical_reject(it, s)
        if r:
            it.status, it.reason = REJECT, r
    ok = [it for it in g if it.status != REJECT]
    if not ok:
        return

    # 2) innerhalb der Serie deutlich unschärfer als das schärfste Bild -> raus
    best_sharp = max(it.met.sharpness for it in ok)
    if n > 1:
        for it in ok:
            if it.met.sharpness < s.t["sharp_rel"] * best_sharp:
                it.status = REJECT
                it.reason = f"unschärfer als andere Bilder der Serie ({it.met.sharpness:.2f} vs. {best_sharp:.2f})"
        ok = [it for it in ok if it.status != REJECT]

    people = s.m["faces"] and any(relevant_faces(it.met) for it in ok)

    # 3) Personen: geschlossene Augen raus, solange die Serie bessere Bilder hat.
    #    Einzelbild mit geschlossenen Augen -> raus. Haben ALLE Bilder einer Serie das Problem
    #    (z. B. Lachen), bleibt das beste mit Hinweis drin, damit der Moment nicht verloren geht.
    ps = {}
    if people:
        notes = {}
        for it in ok:
            sc, notes[id(it)] = people_score(it, s)
            if sc is not None:
                ps[id(it)] = sc
        with_open = [it for it in ok if not notes[id(it)]]
        for it in ok:
            note = notes[id(it)]
            if note and (with_open or n == 1):
                it.status, it.reason = REJECT, note
            elif note:
                it.notes.append(note + "?")
        ok = [it for it in ok if it.status != REJECT]
        if not ok:
            return

    # 4) Auswahl. Grundregel aus der Praxis: bei Wiederholungen ist der letzte Schuss der gewollte.
    #    In Frage kommen nur Bilder, die fast so scharf sind wie das beste und (bei Personen)
    #    bei Augen/Blick nicht klar schlechter sind als das beste Bild.
    pos = {id(it): i for i, it in enumerate(g)}
    best_sharp = max(it.met.sharpness for it in ok)
    best_ps = max(ps.values()) if ps else 0.0
    margin = 0.06 if s.mode == "people" else 0.12

    def eligible(it):
        sharp_ok = it.met.sharpness >= s.t["sharp_pick"] * best_sharp
        # Bilder ohne erkanntes Gesicht (z. B. Kopf kurz weggedreht) werden neutral behandelt
        people_ok = id(it) not in ps or ps[id(it)] >= best_ps - margin
        return sharp_ok and people_ok

    for it in ok:
        quality = (ps.get(id(it), 0.0) + 0.25 * it.met.sharpness / best_sharp) if best_sharp > 0 else 0
        it.score = (10.0 if eligible(it) else 0.0) + pos[id(it)] / max(1, n - 1) + 0.01 * quality
    k = s.picks_per_group + (1 if n >= 12 else 0)
    ranked = sorted(ok, key=lambda it: -it.score)
    for i, it in enumerate(ranked):
        if i < k:
            it.status = PICK
            if n == 1:
                it.reason = "Einzelbild, technisch in Ordnung"
            elif people:
                it.reason = f"letztes Bild der Serie ({n} Bilder) mit voller Schärfe, Augen/Blick ok"
            else:
                it.reason = f"letztes scharfes Bild der Serie ({n} Bilder)"
        else:
            it.status = ALT
            it.reason = f"Alternative in Serie ({n} Bilder)"
    for it in ok:
        if it.notes:
            it.reason += " – Hinweis: " + ", ".join(it.notes)
