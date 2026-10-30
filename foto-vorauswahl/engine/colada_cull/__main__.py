"""Kommandozeile.

Beispiele:
  python -m colada_cull --folder /Pfad/zum/Shooting --mode auto --strictness normal --xmp --report bericht.html
  python -m colada_cull --list pfade.txt --results ergebnis.tsv --progress-file fortschritt.txt   (für Capture One)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from pathlib import Path

os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")


def main(argv=None):
    from .analysis import MODEL_DIR
    from .culling import Item, Settings, select, MODES, STRICTNESS, PICK, ALT, REJECT, SKIP
    from .loader import list_images
    from .pipeline import analyze_all

    ap = argparse.ArgumentParser(prog="colada_cull", description="Automatische Vorauswahl für Fotoshootings")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--folder", help="Ordner mit Bildern (RAW/JPEG/TIFF)")
    src.add_argument("--list", help="Textdatei mit einem Bildpfad pro Zeile (Reihenfolge bleibt erhalten)")
    ap.add_argument("--recursive", action="store_true", help="Unterordner einbeziehen")
    ap.add_argument("--mode", default="auto", choices=sorted(MODES))
    ap.add_argument("--strictness", default="normal", choices=sorted(STRICTNESS))
    ap.add_argument("--picks", type=int, default=1, help="Bilder pro Serie in der Auswahl")
    ap.add_argument("--rating-pick", type=int, default=3)
    ap.add_argument("--rating-alt", type=int, default=1)
    ap.add_argument("--rating-reject", type=int, default=0)
    ap.add_argument("--results", help="TSV-Ausgabe: Sterne, Farbe, Status, Begründung (eine Zeile pro Eingabezeile)")
    ap.add_argument("--report", help="HTML-Prüfbericht schreiben")
    ap.add_argument("--xmp", action="store_true", help="Sterne/Label als XMP-Sidecar neben die Bilder schreiben")
    ap.add_argument("--progress-file", help="Fortschritt 'erledigt/gesamt' laufend in diese Datei schreiben")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--models", default=str(MODEL_DIR))
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args(argv)

    if a.folder:
        paths = [str(p) for p in list_images(a.folder, a.recursive)]
    else:
        paths = [l.strip() for l in Path(a.list).read_text(encoding="utf-8").splitlines()]
    valid = [p for p in paths if p and os.path.isfile(p)]
    if not valid:
        print("Keine Bilder gefunden.", file=sys.stderr)
        _write_progress(a.progress_file, "fehler", "Keine Bilder gefunden")
        return 2

    t0 = time.time()

    def progress(done, total):
        _write_progress(a.progress_file, done, total)
        if sys.stderr.isatty():
            print(f"\rAnalysiere {done}/{total}", end="", file=sys.stderr, flush=True)

    analysed = analyze_all(valid, a.models, workers=a.workers, progress=progress, use_cache=not a.no_cache)
    if sys.stderr.isatty():
        print(file=sys.stderr)
    by_path = {}
    items = []
    for i, (p, (met, dt)) in enumerate(zip(valid, analysed)):
        it = by_path.get(p)
        if it is None:
            it = Item(index=i, path=p, time=dt, met=met)
            by_path[p] = it
            items.append(it)

    s = Settings(mode=a.mode, strictness=a.strictness, picks_per_group=max(1, a.picks),
                 rating_pick=a.rating_pick, rating_alt=a.rating_alt, rating_reject=a.rating_reject)
    groups = select(items, s)

    if a.results:
        lines = []
        for p in paths:
            it = by_path.get(p)
            if it is None:
                lines.append("-\t-\tmissing\tDatei nicht gefunden")
            else:
                reason = it.reason.replace("\t", " ").replace("\n", " ")
                if it.status == SKIP:
                    lines.append(f"-\t-\t{it.status}\t{reason}")
                else:
                    lines.append(f"{it.rating}\t{it.color}\t{it.status}\t{reason}")
        Path(a.results).write_text("\n".join(lines) + "\n", encoding="utf-8")

    if a.xmp:
        from .xmp import write_sidecar, sidecar_path
        seen = set()
        for it in items:
            sc = sidecar_path(Path(it.path))
            if it.status == SKIP or sc in seen:  # gleicher Dateiname mit anderer Endung: nur einmal
                continue
            seen.add(sc)
            try:
                write_sidecar(it.path, it.rating, it.color)
            except OSError as e:
                print(f"XMP nicht geschrieben: {it.path}: {e}", file=sys.stderr)

    if a.report:
        from .report import write_report
        title = f"Vorauswahl – {Path(a.folder).name}" if a.folder else "Vorauswahl"
        write_report(items, groups, s, a.report, title=title)

    c = Counter(it.status for it in items)
    summary = (f"{len(items)} Bilder in {len(groups)} Serien: {c[PICK]} Auswahl, {c[ALT]} Alternativen, "
               f"{c[REJECT]} aussortiert ({time.time() - t0:.0f} s)")
    if c[SKIP]:
        summary += f" – {c[SKIP]} Datei(en) nicht analysierbar, unverändert"
    print(summary)
    _write_progress(a.progress_file, "fertig", summary)
    return 0


def _write_progress(path, a, b):
    if not path:
        return
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(f"{a}/{b}")
    os.replace(tmp, path)


if __name__ == "__main__":
    sys.exit(main())
