"""HTML-Prüfbericht: alle Serien als Kontaktbogen, mit Begründung pro Bild."""

from __future__ import annotations

import html
from collections import Counter
from pathlib import Path

from .culling import Item, PICK, ALT, REJECT, SKIP, Settings
from .pipeline import thumb_path

CSS = """
:root{--bg:#f6f5f2;--card:#fff;--ink:#1c1c1c;--mute:#6b6b6b;--pick:#2e9e4f;--alt:#b5b5b5;--rej:#d64545;--line:#e3e1dc}
@media (prefers-color-scheme:dark){:root{--bg:#161616;--card:#222;--ink:#eee;--mute:#9a9a9a;--line:#333}}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 -apple-system,BlinkMacSystemFont,"Helvetica Neue",sans-serif;background:var(--bg);color:var(--ink)}
header{position:sticky;top:0;background:var(--bg);padding:14px 20px;border-bottom:1px solid var(--line);z-index:2}
h1{font-size:18px;margin:0 0 4px}.sum{color:var(--mute)}
.filters{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap}.filters button{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:14px;padding:3px 10px;cursor:pointer}
.filters button.on{background:var(--ink);color:var(--bg)}
main{padding:12px 20px 60px}.grp{background:var(--card);border:1px solid var(--line);border-radius:8px;margin:10px 0;padding:10px}
.gh{color:var(--mute);font-size:12px;margin-bottom:6px}.row{display:flex;gap:8px;flex-wrap:wrap}
.it{width:190px;border:3px solid transparent;border-radius:6px;padding:3px;position:relative}
.it img{width:100%;height:130px;object-fit:contain;background:#0002;border-radius:3px;display:block}
.it.pick{border-color:var(--pick)}.it.reject{border-color:var(--rej);opacity:.75}.it.alt{border-color:var(--alt);opacity:.85}
.n{font-size:11px;font-weight:600;word-break:break-all}.r{font-size:11px;color:var(--mute)}
.b{position:absolute;top:8px;left:8px;font-size:11px;font-weight:700;color:#fff;padding:1px 6px;border-radius:9px}
.skip .b{background:#b08a00}.pick .b{background:var(--pick)}.reject .b{background:var(--rej)}.alt .b{background:#888}
.hide{display:none}
"""

JS = """
function f(k){document.querySelectorAll('.filters button').forEach(b=>b.classList.toggle('on',b.dataset.k===k));
document.querySelectorAll('.it').forEach(e=>e.classList.toggle('hide',k!=='all'&&!e.classList.contains(k)));
document.querySelectorAll('.grp').forEach(g=>g.classList.toggle('hide',!g.querySelector('.it:not(.hide)')));}
"""

LABEL = {PICK: "Auswahl", ALT: "Alternative", REJECT: "Aussortiert", SKIP: "Nicht lesbar"}


def write_report(items: list[Item], groups: list[list[Item]], settings: Settings, out: str | Path,
                 title: str = "Vorauswahl") -> Path:
    out = Path(out)
    c = Counter(it.status for it in items)
    parts = [f"<!doctype html><html lang=de><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
             f"<title>{html.escape(title)}</title><style>{CSS}</style><script>{JS}</script><body>"
             f"<header><h1>{html.escape(title)}</h1><div class=sum>{len(items)} Bilder · {len(groups)} Serien · "
             f"<b style='color:var(--pick)'>{c[PICK]} Auswahl</b> · {c[ALT]} Alternativen · "
             f"<b style='color:var(--rej)'>{c[REJECT]} aussortiert</b> · Modus: {settings.mode}, Strenge: {settings.strictness}</div>"
             "<div class=filters><button class=on data-k=all onclick=f('all')>Alle</button>"
             "<button data-k=pick onclick=f('pick')>Auswahl</button><button data-k=alt onclick=f('alt')>Alternativen</button>"
             "<button data-k=reject onclick=f('reject')>Aussortiert</button></div></header><main>"]
    for gi, g in enumerate(groups):
        t0 = g[0].time.strftime("%H:%M:%S") if g[0].time else ""
        parts.append(f"<div class=grp><div class=gh>Serie {gi + 1} · {len(g)} Bild(er) · {t0}</div><div class=row>")
        for it in g:
            tp = thumb_path(it.path)
            src = tp.as_uri() if tp.exists() else ""
            name = Path(it.path).name
            faces = ""
            if it.met.faces:
                faces = " · Gesichter: " + ", ".join(
                    f"Augen {f.eyes_open:.0%}, Blick {f.looking:.0%}" for f in it.met.faces[:3])
            parts.append(
                f"<div class='it {it.status}' title='{html.escape(it.path)}'><span class=b>{LABEL[it.status]}</span>"
                f"<img loading=lazy src='{src}'><div class=n>{html.escape(name)}</div>"
                f"<div class=r>{html.escape(it.reason)}</div>"
                f"<div class=r>Schärfe {it.met.sharpness:.2f}{html.escape(faces)}</div></div>")
        parts.append("</div></div>")
    parts.append("</main></body></html>")
    out.write_text("".join(parts), encoding="utf-8")
    return out
