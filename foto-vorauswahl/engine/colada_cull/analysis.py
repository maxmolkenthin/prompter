"""Bildanalyse: Schärfe, Belichtung, Gesichter (Augen, Blickrichtung), Bild-Fingerabdruck."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

import cv2
import numpy as np

MODEL_DIR = Path(os.environ.get("COLADA_CULL_MODELS", Path(__file__).resolve().parent.parent / "models"))
MODEL_FILES = {
    "detector": "blaze_face_full_range.tflite",
    "detector_short": "blaze_face_short_range.tflite",
    "landmarker": "face_landmarker.task",
    "embedder": "mobilenet_v3_large.tflite",
}
MODEL_URLS = {
    "blaze_face_full_range.tflite": "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_full_range/float16/latest/blaze_face_full_range.tflite",
    "blaze_face_short_range.tflite": "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite",
    "face_landmarker.task": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
    "mobilenet_v3_large.tflite": "https://storage.googleapis.com/mediapipe-models/image_embedder/mobilenet_v3_large/float32/latest/mobilenet_v3_large.tflite",
}

SHARP_SIDE = 1600  # Schärfe wird auf einheitlicher Größe gemessen, damit Werte vergleichbar sind


@dataclass
class Face:
    box: tuple[float, float, float, float]  # x, y, w, h relativ (0..1)
    size: float            # Gesichtsbreite relativ zur Bildbreite
    det_score: float
    eyes_open: float       # 0 = zu, 1 = offen
    blink: float           # max. Blinzel-Wert beider Augen (Blendshape)
    yaw: float             # Kopfdrehung in Grad (0 = frontal)
    pitch: float
    gaze_off: float        # 0 = Augen schauen geradeaus, 1 = stark seitlich
    looking: float         # 0..1 Blick in die Kamera (Kopf + Augen)
    sharpness: float       # Schärfe im Augen-/Gesichtsbereich
    landmarks_ok: bool
    look_down: float = 0.0  # Blick nach unten (Lider wirken dann geschlossen)
    smile: float = 0.0      # Lachen (Augen oft zusammengekniffen)


@dataclass
class ImageMetrics:
    path: str
    width: int = 0
    height: int = 0
    sharpness: float = 0.0          # Schärfster Bildbereich (0.1 = deutlich unscharf, >0.2 = scharf)
    sharpness_global: float = 0.0   # Median über alle Bildbereiche
    brightness: float = 0.0
    clip_high: float = 0.0
    clip_low: float = 0.0
    p99: float = 0.0                # Helligkeit der hellsten 1 % (Fehlauslösung: keine Lichter)
    faces: list[Face] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)
    tiny: list[float] = field(default_factory=list)  # 16x16 Graustufen-Miniatur für Feinvergleich
    error: str = ""

    def to_dict(self):
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(d):
        faces = [Face(**f) for f in d.get("faces", [])]
        d = dict(d)
        d["faces"] = faces
        return ImageMetrics(**d)


# ------------------------------------------------------------------ Schärfe

def _directional_sharpness(gray: np.ndarray, grid: int = 8, mask_rect=None):
    """Kantenschärfe = |2. Ableitung| / |1. Ableitung| an den stärksten Kanten.

    Das Verhältnis ist weitgehend unabhängig vom Bildinhalt (Kontrast, Textur) und fällt
    bei Unschärfe stark ab. Es wird in vier Richtungen gemessen und pro Kachel das Minimum
    genommen, damit auch Verwacklung (Bewegungsunschärfe in nur einer Richtung) auffällt.
    """
    g = cv2.GaussianBlur(gray, (0, 0), 0.6)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    gxx = cv2.Sobel(g, cv2.CV_32F, 2, 0, ksize=3)
    gyy = cv2.Sobel(g, cv2.CV_32F, 0, 2, ksize=3)
    gxy = cv2.Sobel(g, cv2.CV_32F, 1, 1, ksize=3)
    H, W = g.shape
    if mask_rect is not None:
        x0, y0, x1, y1 = mask_rect
        sl = (slice(y0, y1), slice(x0, x1))
        gx, gy, gxx, gyy, gxy = (a[sl] for a in (gx, gy, gxx, gyy, gxy))
        H, W = gx.shape
    th, tw = max(1, H // grid), max(1, W // grid)
    per_dir = []
    for t in (0.0, math.pi / 4, math.pi / 2, 3 * math.pi / 4):
        c, s = math.cos(t), math.sin(t)
        d1 = np.abs(c * gx + s * gy)
        d2 = np.abs(c * c * gxx + 2 * c * s * gxy + s * s * gyy)
        # Rauschboden (hohe ISO) aus den ruhigen Bildbereichen schätzen und abziehen,
        # sonst wirkt Rauschen wie Schärfe und ein unscharfes, verrauschtes Bild gilt als scharf
        low = d1 < np.percentile(d1, 40)
        n1 = float(np.median(d1[low])) if low.any() else 0.0
        n2 = float(np.median(d2[low])) if low.any() else 0.0
        vals = []
        for i in range(grid):
            for j in range(grid):
                D1 = d1[i * th:(i + 1) * th, j * tw:(j + 1) * tw]
                if D1.size < 100:
                    vals.append(np.nan)
                    continue
                thr = max(0.08, float(np.percentile(D1, 95)))
                m = D1 >= thr
                if m.sum() < 30:
                    vals.append(np.nan)
                    continue
                D2 = d2[i * th:(i + 1) * th, j * tw:(j + 1) * tw]
                vals.append(max(0.0, float(D2[m].mean()) - n2) / max(1e-6, float(D1[m].mean()) - n1))
        per_dir.append(vals)
    arr = np.array(per_dir)
    valid_cols = ~np.all(np.isnan(arr), axis=0)
    if not valid_cols.any():
        return 0.0, 0.0
    per_tile = np.nanmin(arr[:, valid_cols], axis=0)
    return float(np.percentile(per_tile, 95)), float(np.median(per_tile))


def sharpness(gray: np.ndarray, rect=None, grid: int = 8):
    return _directional_sharpness(gray, grid=grid, mask_rect=rect)


# ------------------------------------------------------------------ Modelle

class Models:
    """Lädt MediaPipe-Modelle einmal pro Prozess."""

    def __init__(self, model_dir: Path = MODEL_DIR, use_faces=True, use_embedding=True):
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        self.mp = mp
        self.vision = vision
        md = Path(model_dir)
        self.detector = self.detector_short = self.landmarker = self.embedder = None
        if use_faces:
            self.detector = vision.FaceDetector.create_from_options(vision.FaceDetectorOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(md / MODEL_FILES["detector"])),
                min_detection_confidence=0.5))
            self.detector_short = vision.FaceDetector.create_from_options(vision.FaceDetectorOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(md / MODEL_FILES["detector_short"])),
                min_detection_confidence=0.6))
            self.landmarker = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(md / MODEL_FILES["landmarker"])),
                output_face_blendshapes=True,
                output_facial_transformation_matrixes=True,
                num_faces=1,
                min_face_detection_confidence=0.3,
                min_face_presence_confidence=0.3))
        if use_embedding:
            self.embedder = vision.ImageEmbedder.create_from_options(vision.ImageEmbedderOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(md / MODEL_FILES["embedder"])),
                l2_normalize=True, quantize=False))

    def mp_image(self, rgb: np.ndarray):
        return self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))


# ------------------------------------------------------------------ Gesichter

def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x0, y0 = max(ax, bx), max(ay, by)
    x1, y1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0


def _detect_faces(models: Models, rgb: np.ndarray):
    """Gesichter auf dem Gesamtbild und (für kleine Gesichter) auf überlappenden Kacheln suchen."""
    H, W = rgb.shape[:2]
    boxes = []  # (x, y, w, h, score) in Pixeln

    def run(img, ox, oy, det):
        res = det.detect(models.mp_image(img))
        for d in res.detections:
            bb = d.bounding_box
            boxes.append((bb.origin_x + ox, bb.origin_y + oy, bb.width, bb.height, d.categories[0].score))

    run(rgb, 0, 0, models.detector)
    run(rgb, 0, 0, models.detector_short)
    # Kacheln 2x2 mit Überlappung -> findet auch Personen im Hintergrund einer Halle
    tw, th = int(W * 0.6), int(H * 0.6)
    for ox in (0, W - tw):
        for oy in (0, H - th):
            run(rgb[oy:oy + th, ox:ox + tw], ox, oy, models.detector)

    # Non-Maximum-Suppression
    boxes.sort(key=lambda b: -b[4])
    kept = []
    for b in boxes:
        if b[2] < 12 or b[3] < 12:
            continue
        if all(_iou(b[:4], k[:4]) < 0.3 for k in kept):
            kept.append(b)
    return kept


_EYE_L = (33, 133, 159, 145)   # Ecke außen, Ecke innen, Lid oben, Lid unten
_EYE_R = (263, 362, 386, 374)


def _ear(lm, idx):
    a, b, t, u = (np.array([lm[i].x, lm[i].y]) for i in idx)
    w = np.linalg.norm(a - b)
    return float(np.linalg.norm(t - u) / w) if w > 1e-6 else 0.0


def _analyze_face(models: Models, rgb: np.ndarray, gray: np.ndarray, box) -> Face:
    H, W = rgb.shape[:2]
    x, y, w, h, score = box
    # großzügiger Ausschnitt, damit der Landmarker das Gesicht sicher wiederfindet
    m = 0.6
    cx0, cy0 = int(max(0, x - m * w)), int(max(0, y - m * h * 1.2))
    cx1, cy1 = int(min(W, x + w * (1 + m))), int(min(H, y + h * (1 + m)))
    crop = rgb[cy0:cy1, cx0:cx1]
    target = 384
    s = target / max(crop.shape[:2])
    crop_s = cv2.resize(crop, (max(1, int(crop.shape[1] * s)), max(1, int(crop.shape[0] * s))),
                        interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)

    face_sharp = sharpness(gray, rect=(int(x), int(y), int(x + w), int(y + h)), grid=2)[0] if w >= 40 else 0.0
    base = dict(box=(x / W, y / H, w / W, h / H), size=w / W, det_score=float(score), sharpness=face_sharp)

    res = models.landmarker.detect(models.mp_image(crop_s))
    if not res.face_landmarks:
        return Face(eyes_open=1.0, blink=0.0, yaw=0.0, pitch=0.0, gaze_off=0.0, looking=0.5,
                    landmarks_ok=False, **base)

    bs = {c.category_name: c.score for c in res.face_blendshapes[0]}
    lm = res.face_landmarks[0]
    blink = max(bs.get("eyeBlinkLeft", 0), bs.get("eyeBlinkRight", 0))
    ear = min(_ear(lm, _EYE_L), _ear(lm, _EYE_R))

    # Kopfhaltung aus Transformationsmatrix
    M = np.array(res.facial_transformation_matrixes[0])[:3, :3]
    yaw = math.degrees(math.atan2(-M[2, 0], math.hypot(M[2, 1], M[2, 2])))
    pitch = math.degrees(math.atan2(M[2, 1], M[2, 2]))  # positiv = Kopf nach unten geneigt
    gaze_off = max(bs.get(k, 0) for k in (
        "eyeLookOutLeft", "eyeLookOutRight", "eyeLookInLeft", "eyeLookInRight",
        "eyeLookUpLeft", "eyeLookUpRight", "eyeLookDownLeft", "eyeLookDownRight"))

    look_down = max(bs.get("eyeLookDownLeft", 0), bs.get("eyeLookDownRight", 0))
    smile = max(bs.get("mouthSmileLeft", 0), bs.get("mouthSmileRight", 0))

    # Augen offen: Blendshape und Lidabstand (EAR) kombinieren; seitliche Köpfe verfälschen EAR
    open_bs = 1.0 - blink
    open_ear = float(np.clip((ear - 0.12) / (0.24 - 0.12), 0, 1))
    eyes_open = 0.65 * open_bs + 0.35 * open_ear if abs(yaw) < 35 else open_bs

    head = max(0.0, 1 - (abs(yaw) / 30) ** 2 - (abs(pitch) / 30) ** 2)
    eyes = max(0.0, 1 - gaze_off / 0.6)
    looking = head * eyes
    return Face(eyes_open=float(eyes_open), blink=float(blink), yaw=float(yaw), pitch=float(pitch),
                gaze_off=float(gaze_off), looking=float(looking), landmarks_ok=True,
                look_down=float(look_down), smile=float(smile), **base)


# ------------------------------------------------------------------ Gesamt

def analyze(path: str, rgb: np.ndarray, models: Models | None) -> ImageMetrics:
    H, W = rgb.shape[:2]
    met = ImageMetrics(path=str(path), width=W, height=H)

    s = SHARP_SIDE / max(H, W)
    rgb_s = cv2.resize(rgb, (round(W * s), round(H * s)), interpolation=cv2.INTER_AREA) if s < 1 else rgb
    gray = cv2.cvtColor(rgb_s, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    met.sharpness, met.sharpness_global = sharpness(gray)

    lum = gray
    met.brightness = float(lum.mean())
    met.clip_high = float((lum > 0.985).mean())
    met.clip_low = float((lum < 0.015).mean())
    met.p99 = float(np.percentile(lum, 99))
    tiny = cv2.resize(gray, (16, 16), interpolation=cv2.INTER_AREA)
    met.tiny = [round(float(v), 4) for v in tiny.ravel()]

    if models is not None and models.detector is not None:
        boxes = _detect_faces(models, rgb_s)
        faces = [_analyze_face(models, rgb_s, gray, b) for b in boxes]
        # nur Gesichter, die der Landmarker bestätigt, oder sehr sichere Detektionen behalten
        met.faces = [f for f in faces if f.landmarks_ok or f.det_score > 0.85]

    if models is not None and models.embedder is not None:
        emb_in = cv2.resize(rgb_s, (round(rgb_s.shape[1] * 512 / max(rgb_s.shape[:2])),
                                    round(rgb_s.shape[0] * 512 / max(rgb_s.shape[:2]))),
                            interpolation=cv2.INTER_AREA)
        res = models.embedder.embed(models.mp_image(emb_in))
        met.embedding = [round(float(v), 5) for v in res.embeddings[0].embedding]
    return met
