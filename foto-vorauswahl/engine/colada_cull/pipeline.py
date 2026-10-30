"""Analyse vieler Bilder parallel, mit Zwischenspeicher (zweiter Lauf mit anderen Einstellungen ist sofort fertig)."""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from .analysis import ImageMetrics, Models, analyze
from .loader import capture_time, load_preview

CACHE_VERSION = 5
_models = None


def cache_dir() -> Path:
    if sys.platform == "darwin":
        d = Path.home() / "Library" / "Caches" / "ColadaCull"
    else:
        d = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "colada-cull"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _key(path: str) -> str:
    st = os.stat(path)
    raw = f"{CACHE_VERSION}|{os.path.abspath(path)}|{st.st_size}|{int(st.st_mtime)}"
    return hashlib.sha1(raw.encode()).hexdigest()


def _init_worker(model_dir):
    global _models
    os.environ.setdefault("GLOG_minloglevel", "2")
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    _models = Models(model_dir) if model_dir else None


def thumb_path(path: str) -> Path:
    return cache_dir() / f"{_key(path)}.jpg"


def _save_thumb(path: str, rgb):
    from PIL import Image
    try:
        im = Image.fromarray(rgb)
        im.thumbnail((360, 360))
        im.save(thumb_path(path), quality=75)
    except Exception:
        pass


def _work(path: str) -> dict:
    t0 = time.time()
    try:
        rgb, jpeg = load_preview(path)
        dt, src = capture_time(path, jpeg)
        met = analyze(path, rgb, _models)
        _save_thumb(path, rgb)
    except Exception as e:  # einzelne defekte Dateien dürfen den Lauf nicht abbrechen
        met = ImageMetrics(path=path, error=f"{type(e).__name__}: {e}")
        try:
            dt, src = capture_time(path)
        except Exception:
            dt, src = None, "none"
    d = met.to_dict()
    d["time"] = dt.isoformat() if dt else None
    d["time_src"] = src
    d["secs"] = round(time.time() - t0, 3)
    return d


def analyze_all(paths: list[str], model_dir: str | None, workers: int | None = None,
                progress=None, use_cache: bool = True) -> list[tuple[ImageMetrics, datetime | None]]:
    """Gibt pro Pfad (in Eingabereihenfolge) (Metriken, Aufnahmezeit) zurück."""
    cdir = cache_dir()
    results: dict[str, dict] = {}
    todo = []
    unique = list(dict.fromkeys(paths))
    for p in unique:
        cf = None
        if use_cache:
            try:
                cf = cdir / f"{_key(p)}.json"
            except OSError:
                cf = None
        if cf is not None and cf.exists():
            try:
                results[p] = json.loads(cf.read_text())
                continue
            except Exception:
                pass
        todo.append(p)

    done = len(results)
    total = len(unique)
    if progress:
        progress(done, total)
    if todo:
        workers = workers or max(1, min(len(todo), (os.cpu_count() or 4) - 1))
        if workers == 1:
            _init_worker(model_dir)
            it = map(_work, todo)
            pool = None
        else:
            ctx = mp.get_context("spawn")
            pool = ctx.Pool(workers, initializer=_init_worker, initargs=(model_dir,))
            it = pool.imap(_work, todo, chunksize=1)
        try:
            for d in it:
                results[d["path"]] = d
                if use_cache and not d.get("error"):
                    try:
                        (cdir / f"{_key(d['path'])}.json").write_text(json.dumps(d))
                    except OSError:
                        pass
                done += 1
                if progress:
                    progress(done, total)
        finally:
            if pool is not None:
                pool.close()
                pool.join()

    out = []
    for p in paths:
        d = dict(results[p])
        t = d.pop("time", None)
        d.pop("time_src", None)
        d.pop("secs", None)
        out.append((ImageMetrics.from_dict(d), datetime.fromisoformat(t) if t else None))
    return out
