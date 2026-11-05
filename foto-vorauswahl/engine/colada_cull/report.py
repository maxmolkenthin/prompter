"""HTML-Prüfbericht und CSV: alle Serien als Kontaktbogen, mit Originaldatei und Begründung pro Bild.

Der Bericht ist eine einzelne Datei (Vorschaubilder eingebettet) und lässt sich weitergeben.
"""

from __future__ import annotations

import base64
import csv
import html
import io
import os
from collections import Counter
from pathlib import Path

from .culling import Item, PICK, ALT, DUP, REJECT, SKIP, LABELS, Settings
from .pipeline import thumb_path

CSS = """
:root{--bg:#f6f5f2;--card:#fff;--ink:#1c1c1c;--mute:#6b6b6b;--pick:#2e9e4f;--res:#c99a10;--dup:#9a9a9a;--rej:#d64545;--line:#e3e1dc}
@media (prefers-color-scheme:dark){:root{--bg:#161616;--card:#222;--ink:#eee;--mute:#9a9a9a;--line:#333}}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 -apple-system,BlinkMacSystemFont,"Helvetica Neue",sans-serif;background:var(--bg);color:var(--ink)}
header{position:sticky;top:0;background:var(--bg);padding:14px 20px;border-bottom:1px solid var(--line);z-index:2}
h1{font-size:18px;margin:0 0 4px}.sum{color:var(--mute)}.inv{color:var(--mute);font-size:12px;margin-top:4px}
.filters{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap}.filters button{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:14px;padding:3px 10px;cursor:pointer}
.filters button.on{background:var(--ink);color:var(--bg)}
main{padding:12px 20px 60px}.grp{background:var(--card);border:1px solid var(--line);border-radius:8px;margin:10px 0;padding:10px}
.gh{color:var(--mute);font-size:12px;margin-bottom:6px}.row{display:flex;gap:8px;flex-wrap:wrap}
.it{width:200px;border:3px solid var(--dup);border-radius:6px;padding:3px;position:relative}
.it img{width:100%;height:130px;object-fit:contain;background:#0002;border-radius:3px;display:block}
.it.pick{border-color:var(--pick)}.it.alt{border-color:var(--res)}.it.reject{border-color:var(--rej);opacity:.8}.it.dup{opacity:.8}
.n{font-size:12px;font-weight:700;word-break:break-all}.p{font-size:10.5px;color:var(--mute);word-break:break-all}.r{font-size:11px;color:var(--mute)}
.b{position:absolute;top:8px;left:8px;font-size:11px;font-weight:700;color:#fff;padding:1px 6px;border-radius:9px;background:var(--dup)}
.pick .b{background:var(--pick)}.alt .b{background:var(--res)}.reject .b{background:var(--rej)}.skip .b{background:#7a5b00}
.hide{display:none}
"""

JS = """
function f(k){document.querySelectorAll('.filters button').forEach(b=>b.classList.toggle('on',b.dataset.k===k));
document.querySelectorAll('.it').forEach(e=>e.classList.toggle('hide',k!=='all'&&!e.classList.contains(k)));
document.querySelectorAll('.grp').forEach(g=>g.classList.toggle('hide',!g.querySelector('.it:not(.hide)')));}
"""

STARS = {3: "★★★", 2: "★★", 1: "★", 0: "–"}
COLORS = {0: "", 1: "Rot", 2: "Orange", 3: "Gelb", 4: "Grün", 5: "Blau", 6: "Pink", 7: "Lila"}


def _thumb_data(path: str) -> str:
    tp = thumb_path(path)
    if not tp.exists():
        return ""
    try:
        from PIL import Image
        im = Image.open(tp)
        im.thumbnail((260, 260))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=70)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def _common_root(items: list[Item]) -> str:
    try:
        return os.path.commonpath([os.path.dirname(it.path) for it in items])
    except ValueError:
        return ""


def write_report(items: list[Item], groups: list[list[Item]], settings: Settings, out: str | Path,
                 title: str = "Vorauswahl", inventory: dict | None = None) -> Path:
    out = Path(out)
    c = Counter(it.status for it in items)
    inv = inventory or {}
    root = _common_root(items)
    types = ", ".join(f"{n}× {e.lstrip('.').upper()}" for e, n in Counter(inv.get("types", {})).most_common())
    ign = inv.get("ignored") or {}
    inv_line = (f"Ordner: {html.escape(root)} · gefunden: {inv.get('found', len(items))} Fotos ({html.escape(types)}) · "
                f"analysiert: {inv.get('analysed', len(items))}")
    if inv.get("skipped"):
        inv_line += f" · nicht lesbar: {inv['skipped']}"
    if ign:
        inv_line += " · nicht berücksichtigt (keine Fotos): " + html.escape(
            ", ".join(f"{n}× {e}" for e, n in sorted(ign.items(), key=lambda x: -x[1])))
    parts = [f"<!doctype html><html lang=de><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
             f"<title>{html.escape(title)}</title><style>{CSS}</style><script>{JS}</script><body>"
             f"<header><h1>{html.escape(title)}</h1><div class=sum>{inv.get('analysed', len(items))} Fotos · {len(groups)} Serien · "
             f"<b style='color:var(--pick)'>{c[PICK]} Top-Auswahl</b> · <b style='color:var(--res)'>{c[ALT]} Reserve</b> · "
             f"{c[DUP]} Duplikate/schwächer · <b style='color:var(--rej)'>{c[REJECT]} aussortiert</b> · "
             f"Modus: {settings.mode}, Strenge: {settings.strictness}</div><div class=inv>{inv_line}</div>"
             "<div class=filters><button class=on data-k=all onclick=f('all')>Alle</button>"
             "<button data-k=pick onclick=f('pick')>Top-Auswahl</button><button data-k=alt onclick=f('alt')>Reserve</button>"
             "<button data-k=dup onclick=f('dup')>Duplikate/schwächer</button>"
             "<button data-k=reject onclick=f('reject')>Aussortiert</button></div></header><main>"]
    for gi, g in enumerate(groups):
        t0 = g[0].time.strftime("%d.%m. %H:%M:%S") if g[0].time else ""
        parts.append(f"<div class=grp><div class=gh>Serie {gi + 1} · {len(g)} Foto(s) · {t0}</div><div class=row>")
        for it in g:
            p = Path(it.path)
            rel = os.path.relpath(it.path, root) if root else it.path
            folder = os.path.dirname(rel)
            inner = f" (enthält {html.escape(Path(it.met.inner).name)})" if it.met.inner else ""
            faces = ""
            if it.met.faces:
                faces = " · Gesichter: " + ", ".join(f"Augen {f.eyes_open:.0%}" for f in it.met.faces[:3])
            stars = STARS.get(it.rating, "") if it.rating is not None else ""
            col = COLORS.get(it.color, "") if it.color is not None else ""
            mark = " ".join(x for x in (stars, col) if x)
            parts.append(
                f"<div class='it {it.status}' title='{html.escape(it.path)}'><span class=b>{LABELS[it.status]}</span>"
                f"<img loading=lazy alt='' src='{_thumb_data(it.path)}'>"
                f"<div class=n>{html.escape(p.name)}</div>"
                f"<div class=p>{html.escape(folder + '/' if folder else '')}{inner}</div>"
                f"<div class=r>{html.escape(it.reason)}</div>"
                f"<div class=r>{html.escape(mark)} · Schärfe {it.met.sharpness:.2f}{html.escape(faces)}</div></div>")
        parts.append("</div></div>")
    parts.append("</main></body></html>")
    out.write_text("".join(parts), encoding="utf-8")
    return out


def write_csv(items: list[Item], out: str | Path) -> Path:
    """Tabelle zum Nachprüfen/Filtern in Numbers oder Excel: eine Zeile pro Originaldatei."""
    out = Path(out)
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Originaldatei", "Aufnahme im EIP", "Kategorie", "Sterne", "Farbe", "Serie",
                    "Aufnahmezeit", "Schärfe", "Begründung"])
        for it in sorted(items, key=lambda x: x.index):
            w.writerow([it.path, Path(it.met.inner).name if it.met.inner else "", LABELS[it.status],
                        "" if it.rating is None else it.rating, "" if it.color is None else COLORS.get(it.color, ""),
                        it.group + 1, it.time.strftime("%Y-%m-%d %H:%M:%S") if it.time else "",
                        f"{it.met.sharpness:.2f}".replace(".", ","), it.reason])
    return out
