"""Dateien finden, Aufnahmezeit lesen, Vorschaubild laden (RAW, EIP, JPEG/TIFF).

Alle Originaldateien werden ausschließlich lesend geöffnet. EIP-Dateien (Capture One
"Enhanced Image Package") sind ZIP-Pakete mit der Original-RAW-Datei und Capture-One-
Einstellungen; das RAW wird im Arbeitsspeicher gelesen, die EIP bleibt unverändert.
"""

from __future__ import annotations

import io
import os
import re
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

try:
    import exifread
except ImportError:  # pragma: no cover
    exifread = None

try:
    import rawpy
except ImportError:  # pragma: no cover
    rawpy = None

Image.MAX_IMAGE_PIXELS = None

RAW_EXT = {
    ".cr2", ".cr3", ".crw", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".raf", ".rw2",
    ".orf", ".dng", ".pef", ".iiq", ".3fr", ".fff", ".rwl", ".srw", ".x3f", ".erf",
    ".mos", ".mrw", ".kdc", ".dcr", ".gpr",
}
IMG_EXT = {".jpg", ".jpeg", ".tif", ".tiff", ".png"}
EIP_EXT = {".eip"}
SUPPORTED_EXT = RAW_EXT | IMG_EXT | EIP_EXT

# Unterordner, die keine Original-Aufnahmen enthalten (Capture-One-Sessions)
SKIP_DIRS = {"captureone", "cache", "proxies", "thumbnails", "trash", "output", "settings"}


def natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def scan_folder(folder: str | Path, recursive: bool = False) -> tuple[list[Path], Counter]:
    """Bilder im Ordner finden. Gibt (Bilder, Zähler der übersprungenen Dateiendungen) zurück."""
    folder = Path(folder)
    it = folder.rglob("*") if recursive else folder.iterdir()
    files, ignored = [], Counter()
    for p in it:
        if not p.is_file() or p.name.startswith("."):
            continue
        sub = [d.lower() for d in p.parts[len(folder.parts):-1]]
        if any(d in SKIP_DIRS for d in sub):
            continue
        if p.suffix.lower() in SUPPORTED_EXT:
            files.append(p)
        else:
            ignored[p.suffix.lower() or "(ohne Endung)"] += 1
    # RAW+JPEG bzw. EIP+JPEG mit gleichem Namen: nur das Original nehmen
    originals = {p.with_suffix("").as_posix().lower() for p in files if p.suffix.lower() in RAW_EXT | EIP_EXT}
    keep = []
    for p in files:
        if p.suffix.lower() in IMG_EXT and p.with_suffix("").as_posix().lower() in originals:
            ignored[p.suffix.lower() + " (Begleit-JPEG/TIFF)"] += 1
        else:
            keep.append(p)
    return sorted(keep, key=lambda p: natural_key(p.as_posix())), ignored


def list_images(folder: str | Path, recursive: bool = False) -> list[Path]:
    return scan_folder(folder, recursive)[0]


# ---------------------------------------------------------------- EIP

def eip_member(zf: zipfile.ZipFile) -> zipfile.ZipInfo:
    """Die eigentliche Aufnahme im EIP-Paket: größte Bilddatei außerhalb des CaptureOne-Ordners."""
    cands = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        parts = [x.lower() for x in info.filename.replace("\\", "/").split("/")]
        if any(x in SKIP_DIRS for x in parts[:-1]):
            continue
        if Path(parts[-1]).suffix in RAW_EXT | IMG_EXT:
            cands.append(info)
    if not cands:
        raise ValueError("keine Bilddatei im EIP-Paket gefunden")
    return max(cands, key=lambda i: i.file_size)


def read_eip(path: str | Path) -> tuple[bytes, str, str]:
    """Liest die Original-Aufnahme aus einer EIP (nur lesend). -> (Bytes, Endung, Name im Paket)."""
    with open(path, "rb") as fh:  # ausdrücklich nur lesend
        with zipfile.ZipFile(fh, "r") as zf:
            info = eip_member(zf)
            data = zf.read(info)
    return data, Path(info.filename).suffix.lower(), info.filename


class Source:
    """Eine Aufnahme: entweder eine Datei auf der Platte oder Bytes aus einer EIP."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.inner = None
        if self.path.suffix.lower() in EIP_EXT:
            self.data, self.ext, self.inner = read_eip(self.path)
        else:
            self.data, self.ext = None, self.path.suffix.lower()

    def open(self):
        return io.BytesIO(self.data) if self.data is not None else open(self.path, "rb")

    def head(self, n: int) -> bytes:
        if self.data is not None:
            return self.data[:n]
        with open(self.path, "rb") as fh:
            return fh.read(n)

    def all(self) -> bytes:
        return self.data if self.data is not None else self.path.read_bytes()


# ---------------------------------------------------------------- Aufnahmezeit

def _parse_exif_dt(tags: dict) -> datetime | None:
    dt_val = None
    sub = "0"
    for key, val in tags.items():
        if key.endswith("DateTimeOriginal") and dt_val is None:
            dt_val = str(val)
        if key.endswith("SubSecTimeOriginal"):
            sub = str(val).strip() or "0"
    if dt_val is None:
        for key, val in tags.items():
            if key.endswith("DateTimeDigitized") or key == "Image DateTime":
                dt_val = str(val)
                break
    if not dt_val:
        return None
    try:
        dt = datetime.strptime(dt_val.strip()[:19], "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    try:
        frac = float("0." + re.sub(r"\D", "", sub)) if sub else 0.0
    except ValueError:
        frac = 0.0
    return dt.replace(microsecond=int(frac * 1_000_000) % 1_000_000)


def _exif_from_bytes(data: bytes) -> datetime | None:
    if exifread is None:
        return None
    try:
        tags = exifread.process_file(io.BytesIO(data), details=False)
    except Exception:
        return None
    return _parse_exif_dt(tags)


def _cr3_capture_time(head: bytes) -> datetime | None:
    """Canon CR3 (ISO-BMFF): EXIF steckt als TIFF in den Boxen CMT1/CMT2 am Dateianfang."""
    for box in (b"CMT2", b"CMT1"):
        pos = head.find(box)
        if pos < 4:
            continue
        size = int.from_bytes(head[pos - 4:pos], "big")
        dt = _exif_from_bytes(head[pos + 4:pos - 4 + size])
        if dt:
            return dt
    return None


def _capture_time(src: Source, preview_jpeg: bytes | None = None) -> tuple[datetime | None, str]:
    ext = src.ext
    if ext == ".cr3":
        dt = _cr3_capture_time(src.head(4 * 1024 * 1024))
        if dt:
            return dt, "exif"
    elif exifread is not None:
        try:
            with src.open() as fh:
                tags = exifread.process_file(fh, details=False)
            dt = _parse_exif_dt(tags)
            if dt:
                return dt, "exif"
        except Exception:
            pass
    if ext == ".raf":
        # Fuji: eingebettetes JPEG (mit EXIF) beginnt laut Header-Offset bei Byte 84
        try:
            hdr = src.head(100)
            off = int.from_bytes(hdr[84:88], "big")
            length = int.from_bytes(hdr[88:92], "big")
            with src.open() as fh:
                fh.seek(off)
                dt = _exif_from_bytes(fh.read(min(length, 256 * 1024)))
            if dt:
                return dt, "exif"
        except Exception:
            pass
    if preview_jpeg:
        dt = _exif_from_bytes(preview_jpeg[:256 * 1024])
        if dt:
            return dt, "exif-preview"
    try:
        return datetime.fromtimestamp(src.path.stat().st_mtime), "mtime"
    except OSError:
        return None, "none"


def capture_time(path: str | Path, preview_jpeg: bytes | None = None) -> tuple[datetime | None, str]:
    return _capture_time(Source(path), preview_jpeg)


# ---------------------------------------------------------------- Vorschau

def _largest_embedded_jpeg(data: bytes) -> bytes | None:
    """Notnagel: größtes eingebettetes JPEG in einer RAW-Datei suchen."""
    best = None
    start = 0
    while True:
        s = data.find(b"\xff\xd8\xff", start)
        if s < 0:
            break
        e = data.find(b"\xff\xd9", s + 3)
        # bei verschachtelten Thumbnails: weitersuchen bis Dekodierung klappt
        while e > 0:
            cand = data[s:e + 2]
            if len(cand) > 20000:
                try:
                    Image.open(io.BytesIO(cand)).verify()
                    if best is None or len(cand) > len(best):
                        best = cand
                    break
                except Exception:
                    pass
            e = data.find(b"\xff\xd9", e + 2)
            if e < 0 or e - s > 60_000_000:
                break
        start = s + 3
    return best


def _open_jpeg_bytes(data: bytes, max_side: int) -> Image.Image:
    im = Image.open(io.BytesIO(data))
    im.draft("RGB", (max_side, max_side))
    return im


def _fit(im: Image.Image, max_side: int) -> Image.Image:
    im = im.convert("RGB")
    w, h = im.size
    scale = max_side / max(w, h)
    if scale < 1:
        im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.Resampling.BILINEAR)
    return im


def _apply_flip(im: Image.Image, flip: int) -> Image.Image:
    # LibRaw: 3 = 180°, 5 = 90° gegen den Uhrzeigersinn, 6 = 90° im Uhrzeigersinn
    if flip == 3:
        return im.transpose(Image.Transpose.ROTATE_180)
    if flip == 5:
        return im.transpose(Image.Transpose.ROTATE_90)
    if flip == 6:
        return im.transpose(Image.Transpose.ROTATE_270)
    return im


def _load_preview(src: Source, max_side: int = 2048) -> tuple[np.ndarray, bytes | None]:
    if src.ext not in RAW_EXT:
        with src.open() as fh:
            im = Image.open(fh)
            if im.format == "JPEG":
                im.draft("RGB", (max_side, max_side))
            im = ImageOps.exif_transpose(im)
            return np.asarray(_fit(im, max_side)), None

    jpeg = None
    flip = 0
    im = None
    if rawpy is not None:
        try:
            raw_in = io.BytesIO(src.data) if src.data is not None else str(src.path)
            with rawpy.imread(raw_in) as raw:
                flip = int(raw.sizes.flip)
                try:
                    th = raw.extract_thumb()
                    if th.format == rawpy.ThumbFormat.JPEG:
                        jpeg = bytes(th.data)
                        im = _open_jpeg_bytes(jpeg, max_side)
                    elif th.format == rawpy.ThumbFormat.BITMAP:
                        im = Image.fromarray(th.data)
                except Exception:
                    im = None
                if im is None or max(im.size) < 800:
                    rgb = raw.postprocess(half_size=True, use_camera_wb=True, no_auto_bright=False, output_bps=8)
                    im = Image.fromarray(rgb)
                    flip = 0  # postprocess dreht bereits selbst
        except Exception:
            im = None
    if im is None:
        jpeg = _largest_embedded_jpeg(src.all())
        if jpeg is None:
            raise ValueError(f"Kein Vorschaubild lesbar: {src.path.name}")
        im = _open_jpeg_bytes(jpeg, max_side)
        im = ImageOps.exif_transpose(im)
    else:
        im = _apply_flip(im, flip)
    return np.asarray(_fit(im, max_side)), jpeg


def load_preview(path: str | Path, max_side: int = 2048) -> tuple[np.ndarray, bytes | None]:
    """Gibt (RGB-Array, eingebettete JPEG-Bytes oder None) zurück."""
    return _load_preview(Source(path), max_side)


def load_image(path: str | Path, max_side: int = 2048):
    """Vorschau + Aufnahmezeit mit nur einem Lesevorgang (wichtig für EIPs auf dem NAS).
    -> (RGB, Aufnahmezeit, Quelle der Zeit, Name der Aufnahme im EIP-Paket oder None)"""
    src = Source(path)
    rgb, jpeg = _load_preview(src, max_side)
    dt, how = _capture_time(src, jpeg)
    return rgb, dt, how, src.inner


def exists(path: str) -> bool:
    return os.path.isfile(path)
