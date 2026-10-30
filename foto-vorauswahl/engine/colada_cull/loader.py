"""Dateien finden, Aufnahmezeit lesen, Vorschaubild laden (RAW + JPEG/TIFF)."""

from __future__ import annotations

import io
import os
import re
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
SUPPORTED_EXT = RAW_EXT | IMG_EXT


def natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def list_images(folder: str | Path, recursive: bool = False) -> list[Path]:
    folder = Path(folder)
    it = folder.rglob("*") if recursive else folder.iterdir()
    files = [
        p for p in it
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXT and not p.name.startswith("._")
        # Capture-One-Sessions: Unterordner wie CaptureOne/Cache nicht mitnehmen
        and "CaptureOne" not in p.parts[len(folder.parts):-1]
    ]
    # Wenn RAW und JPEG mit gleichem Namen existieren (RAW+JPEG), nur das RAW nehmen
    raws = {p.with_suffix("").as_posix().lower() for p in files if p.suffix.lower() in RAW_EXT}
    files = [p for p in files if p.suffix.lower() in RAW_EXT or p.with_suffix("").as_posix().lower() not in raws]
    return sorted(files, key=lambda p: natural_key(p.name))


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


def _cr3_capture_time(path: Path) -> datetime | None:
    """Canon CR3 (ISO-BMFF): EXIF steckt als TIFF in den Boxen CMT1/CMT2 am Dateianfang."""
    with open(path, "rb") as fh:
        head = fh.read(4 * 1024 * 1024)
    best = None
    for box in (b"CMT2", b"CMT1"):
        pos = head.find(box)
        if pos < 4:
            continue
        size = int.from_bytes(head[pos - 4:pos], "big")
        tiff = head[pos + 4:pos - 4 + size]
        dt = _exif_from_bytes(tiff)
        if dt and best is None:
            best = dt
    return best


def capture_time(path: str | Path, preview_jpeg: bytes | None = None) -> tuple[datetime | None, str]:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".cr3":
        dt = _cr3_capture_time(path)
        if dt:
            return dt, "exif"
    if exifread is not None and ext != ".cr3":
        try:
            with open(path, "rb") as fh:
                tags = exifread.process_file(fh, details=False)
            dt = _parse_exif_dt(tags)
            if dt:
                return dt, "exif"
        except Exception:
            pass
    if ext == ".raf":
        # Fuji: eingebettetes JPEG (mit EXIF) beginnt laut Header-Offset bei Byte 84
        try:
            with open(path, "rb") as fh:
                hdr = fh.read(100)
                off = int.from_bytes(hdr[84:88], "big")
                length = int.from_bytes(hdr[88:92], "big")
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
        return datetime.fromtimestamp(path.stat().st_mtime), "mtime"
    except OSError:
        return None, "none"


# ---------------------------------------------------------------- Vorschau

def _largest_embedded_jpeg(path: Path) -> bytes | None:
    """Notnagel: größtes eingebettetes JPEG in einer RAW-Datei suchen."""
    data = path.read_bytes()
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


def load_preview(path: str | Path, max_side: int = 2048) -> tuple[np.ndarray, bytes | None]:
    """Gibt (RGB-Array, eingebettete JPEG-Bytes oder None) zurück."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in RAW_EXT:
        im = Image.open(path)
        if im.format == "JPEG":
            im.draft("RGB", (max_side, max_side))
        im = ImageOps.exif_transpose(im)
        return np.asarray(_fit(im, max_side)), None

    jpeg = None
    flip = 0
    im = None
    if rawpy is not None:
        try:
            with rawpy.imread(str(path)) as raw:
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
        jpeg = _largest_embedded_jpeg(path)
        if jpeg is None:
            raise ValueError(f"Kein Vorschaubild lesbar: {path.name}")
        im = _open_jpeg_bytes(jpeg, max_side)
        im = ImageOps.exif_transpose(im)
    else:
        im = _apply_flip(im, flip)
    return np.asarray(_fit(im, max_side)), jpeg


def file_identity(path: Path) -> str:
    st = path.stat()
    return f"{path.resolve()}|{st.st_size}|{int(st.st_mtime)}"


def exists(path: str) -> bool:
    return os.path.isfile(path)
