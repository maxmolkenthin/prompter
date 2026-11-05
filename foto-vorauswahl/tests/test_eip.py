"""EIP-Test nach Ginas Kriterien (mit kleinem Testprojekt aus EIP-Paketen).

Nachgewiesen wird:
 1. EIP-Dateien werden erkannt und analysiert
 2. die Anzahl der analysierten Fotos stimmt
 3. die Ergebnisse gehören zur richtigen Originaldatei
 4. keine Originaldatei wird verändert, verschoben oder gelöscht (Prüfsumme + Zeitstempel + Dateiliste)
 5. HTML-Bericht und CSV werden erstellt

Aufruf: python test_eip.py <ordner-mit-jpgs> [--models DIR] [--raw echte.NEF]
Die JPGs werden als "Aufnahme" in EIP-Pakete gepackt (Aufbau wie Capture One: Bild + CaptureOne/
Settings + manifest.xml, unkomprimiert). Optional wird ein echtes RAW als EIP mitgetestet.
"""

import argparse
import csv
import hashlib
import io
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ENGINE = Path(__file__).resolve().parent.parent / "engine"


def make_eip(dest: Path, inner_name: str, data: bytes):
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_STORED) as z:
        z.writestr("manifest.xml", "<?xml version='1.0'?><manifest><item>%s</item></manifest>" % inner_name)
        z.writestr("manifest50.xml", "<?xml version='1.0'?><manifest version='50'/>")
        z.writestr(f"CaptureOne/Settings116/{inner_name}.cos", "<?xml version='1.0'?><AD><E K='Rating' V='0'/></AD>")
        z.writestr(inner_name, data)


def snapshot(folder: Path) -> dict:
    out = {}
    for p in sorted(folder.rglob("*")):
        if p.is_file():
            st = p.stat()
            out[str(p.relative_to(folder))] = (hashlib.sha256(p.read_bytes()).hexdigest(), st.st_size, st.st_mtime_ns)
    return out


def jpg_bytes(im: Image.Image, dt: str) -> bytes:
    exif = Image.Exif()
    exif.get_ifd(0x8769)[0x9003] = dt
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92, exif=exif.tobytes())
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jpgs")
    ap.add_argument("--models", default=None)
    ap.add_argument("--raw", default=None)
    a = ap.parse_args()
    src = sorted(Path(a.jpgs).glob("*.jpg"))[:6]
    assert len(src) >= 4, "mindestens 4 JPGs als Ausgangsmaterial nötig"

    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "Projekt"
        cap = proj / "Capture"
        cap.mkdir(parents=True)
        expected = {}
        # Serie: dreimal dasselbe Motiv, mittleres unscharf -> letztes = Top-Auswahl, mittleres raus
        base = Image.open(src[0]).convert("RGB")
        variants = [base, base.filter(ImageFilter.GaussianBlur(4)), base]
        for i, im in enumerate(variants):
            name = f"PC_{i + 1:04d}"
            make_eip(cap / f"{name}.eip", f"{name}.JPG", jpg_bytes(im, f"2026:11:05 10:00:{10 + 3 * i:02d}"))
        expected.update({"PC_0001.eip": "notpick", "PC_0002.eip": "reject", "PC_0003.eip": "pick"})
        # Einzelbilder
        for j, s in enumerate(src[1:4]):
            name = f"PC_{j + 10:04d}"
            make_eip(cap / f"{name}.eip", f"{name}.JPG",
                     jpg_bytes(Image.open(s).convert("RGB"), f"2026:11:05 10:{5 + 3 * j:02d}:00"))
            expected[f"{name}.eip"] = "pick"
        n_photos = 6
        if a.raw:
            make_eip(cap / "PC_0100.eip", "PC_0100.NEF", Path(a.raw).read_bytes())
            expected["PC_0100.eip"] = "any"
            n_photos += 1
        # Weitere Dateien wie in einem echten Projektordner
        Image.open(src[4]).convert("RGB").save(cap / "Freisteller.jpg", quality=90)   # eigenständiges JPG
        expected["Freisteller.jpg"] = "any"
        n_photos += 1
        Image.open(src[1]).convert("RGB").save(cap / "PC_0010.jpg", quality=90)       # Begleit-JPG zu PC_0010.eip
        for ext in ("cos", "cop", "cof", "cot"):
            (cap / f"PC_0001.{ext}").write_text("capture one hilfsdatei")
        (proj / "CaptureOne" / "Cache").mkdir(parents=True)
        Image.open(src[0]).convert("RGB").save(proj / "CaptureOne" / "Cache" / "PC_0001.jpg")  # Cache -> ignorieren
        (proj / "Output").mkdir()
        Image.open(src[0]).convert("RGB").save(proj / "Output" / "PC_0001_export.jpg")       # Export -> ignorieren

        before = snapshot(proj)
        work = Path(tmp) / "work"
        work.mkdir()
        rep = work / "bericht.html"
        cmd = [sys.executable, "-m", "colada_cull", "--folder", str(proj), "--recursive", "--no-cache",
               "--report", str(rep)]
        if a.models:
            cmd += ["--models", a.models]
        r = subprocess.run(cmd, cwd=ENGINE, capture_output=True, text=True)
        print(r.stdout.strip())
        assert r.returncode == 0, r.stderr[-2000:]
        after = snapshot(proj)

        errors = []
        # 1 + 2: erkannt und richtig gezählt
        if f"{n_photos} Fotos analysiert" not in r.stdout:
            errors.append(f"Anzahl falsch: erwartet {n_photos} Fotos analysiert")
        if "EIP" not in r.stdout:
            errors.append("EIP nicht in der Typ-Aufstellung")
        # 3: Zuordnung
        rows = list(csv.DictReader(open(rep.with_suffix(".csv"), encoding="utf-8-sig"), delimiter=";"))
        got = {Path(row["Originaldatei"]).name: row for row in rows}
        if set(got) != set(expected):
            errors.append(f"Dateien im Ergebnis: {sorted(got)} statt {sorted(expected)}")
        for name, exp in expected.items():
            row = got.get(name)
            if not row:
                continue
            cat = row["Kategorie"]
            ok = (exp == "any" and cat != "Nicht lesbar") or (exp == "pick" and cat == "Top-Auswahl") or \
                 (exp == "reject" and cat == "Aussortiert") or (exp == "notpick" and cat not in ("Top-Auswahl", "Nicht lesbar"))
            if name.endswith(".eip") and row["Aufnahme im EIP"] != name.replace(".eip", "") + Path(row["Aufnahme im EIP"]).suffix:
                ok = False
            print(f"{'OK' if ok else 'XX'}  {name:<16} {cat:<20} Aufnahme im EIP: {row['Aufnahme im EIP'] or '-':<14} {row['Begründung']}")
            if not ok:
                errors.append(f"{name}: {cat} (erwartet {exp})")
        # 4: nichts verändert
        if before != after:
            changed = sorted(set(before) ^ set(after) | {k for k in before if k in after and before[k] != after[k]})
            errors.append(f"Projektordner verändert: {changed}")
        else:
            print(f"OK  Projektordner unverändert ({len(before)} Dateien, Prüfsummen und Zeitstempel identisch)")
        # 5: Bericht
        html = rep.read_text(encoding="utf-8")
        if not all(n in html for n in expected) or "data:image/jpeg;base64" not in html:
            errors.append("Bericht unvollständig")
        else:
            print(f"OK  Bericht erstellt ({rep.stat().st_size // 1024} KB, alle Dateien und Vorschauen enthalten)")
        if errors:
            print("\nFEHLER:\n  " + "\n  ".join(errors))
            return 1
        print("\nEIP-Test bestanden.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
