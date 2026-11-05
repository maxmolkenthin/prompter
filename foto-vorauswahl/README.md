# Colada Vorauswahl – automatisches Culling für Capture One

Ein Klick in Capture One, und die Vorauswahl eines Shootingtags ist gemacht. Unterstützt werden RAW-Dateien, **Capture-One-EIP-Pakete**, DNG, JPG und TIFF.

| Kategorie | in Capture One (wenn gewünscht) | Bedeutung |
|---|---|---|
| **Top-Auswahl** | ★★★ + Grün | bestes bzw. letztes scharfes Bild jeder Serie |
| **Reserve** | ★★ + Gelb | zweitbestes Bild der Serie |
| **Duplikat/schwächer** | ★ | weitere nahezu identische Aufnahmen bzw. etwas schwächere Varianten |
| **Aussortiert** | 0 Sterne + Rot | unscharf, verwackelt, Augen zu, Fehlauslösung |

**Originaldateien werden nie verschoben, umbenannt, gelöscht oder verändert.** EIP-Dateien werden nur gelesen. Beim Start wählt man:
- **Nur Prüfbericht (Standard):** In Capture One und im Projektordner ändert sich nichts. Ergebnis ist ein HTML-Bericht und eine CSV-Tabelle mit jeder Originaldatei, Kategorie und Begründung.
- **Sterne + Farben in Capture One setzen:** wie oben in der Tabelle. Hinweis: Capture One speichert Bewertungen bei EIP-Dateien im EIP-Paket selbst, genau wie bei einer Bewertung von Hand.

### EIP-Dateien

Eine EIP („Enhanced Image Package") ist ein ZIP-Paket mit der Original-RAW-Datei, den Capture-One-Einstellungen und einer manifest.xml. Das Tool öffnet die EIP nur lesend, liest die RAW-Datei darin in den Arbeitsspeicher und analysiert sie. Im Bericht steht zu jeder EIP, welche Aufnahme sie enthält. Capture-One-Hilfsdateien (COS, COP, COF, COT …) und die Ordner CaptureOne, Cache, Trash und Output werden ignoriert. Ein JPG mit gleichem Namen wie eine EIP oder ein RAW gilt als Begleitdatei und wird nicht doppelt gezählt.

## Was die Vorauswahl prüft

1. **Serien erkennen:** Bilder vom selben Motiv aus demselben Winkel werden zu einer Serie zusammengefasst. Grundlage sind Bildinhalt (KI-Fingerabdruck), Bildaufbau und Aufnahmezeit. Ein anderer Winkel, eine Totale gegenüber einem Detail oder Hoch- gegenüber Querformat ergeben jeweils eine eigene Serie. Kommt der Fotograf später zum gleichen Motiv zurück (A–B–A), wird das erkannt.
2. **Unschärfe/Verwackeln:** Die Kantenschärfe wird im schärfsten Bildbereich gemessen. Freisteller mit unscharfem Hintergrund fallen deshalb nicht raus. Die Messung läuft in vier Richtungen, so dass auch Verwacklung in nur einer Richtung auffällt. Bildrauschen (hohe ISO) wird vorher herausgerechnet. Ein Bild fällt raus, wenn es absolut unscharf ist oder deutlich unschärfer als das beste Bild seiner Serie.
3. **Personen:** Gesichter werden auch klein im Bild gefunden. Gemessen werden Augen offen/zu, Kopfhaltung und Blickrichtung.
   - Blinzeln wird aussortiert, solange die Serie ein besseres Bild hat.
   - Blick nach unten aufs Werkstück und Lachen gelten nicht als „Augen zu".
   - Haben alle Bilder einer Serie das Problem, bleibt das beste mit Hinweis drin, damit der Moment nicht verloren geht.
4. **Auswahl pro Serie:** Es gewinnt der **letzte Schuss**, sofern er voll scharf ist. Bei Personen muss er außerdem bei Augen, Blick und **Gesichtsschärfe** mithalten können; ein vom Bildrand **angeschnittenes Gesicht** zählt als schwächeres Bild. Ab 12 Bildern in einer Serie werden zwei Bilder ausgewählt. Das zweitbeste Bild wird Reserve, der Rest Duplikat/schwächer.
5. **Fehlauslösungen:** Fast schwarze Bilder (Blitz nicht ausgelöst) und fast weiße Bilder werden aussortiert. Low-Key-Aufnahmen und Freisteller auf Weiß gelten dabei ausdrücklich nicht als Fehler.

### Modus und Strenge (wird bei jedem Start abgefragt)

- **Automatisch:** für gemischte Shootings, Gesichter werden berücksichtigt, wenn vorhanden.
- **Produkt / Detail** und **Architektur:** Gesichter werden ignoriert, es gilt nur Schärfe und „letzter Schuss".
- **Prozess / Reportage:** Augen-Regel lockerer, Blick in die Kamera egal.
- **Menschen / Porträt:** Blick in die Kamera zählt stark.
- **Locker / Normal / Streng:** Locker behält im Zweifel mehr, auch mehr Duplikate. Streng fasst Serien großzügiger zusammen und sortiert Unschärfe härter aus.

## Installation (einmalig, ca. 5 Minuten, keine Admin-Rechte)

Die Installation ist eigenständig: eigenes Python im Ordner `~/Library/Application Support/ColadaCull`, keine Änderungen an Homebrew, an einem vorhandenen Python, an ExifTool, am Shell-Profil oder an anderen Programmen (z. B. pc-cull).

1. Den Ordner `foto-vorauswahl` auf den Mac kopieren.
2. Terminal öffnen und ausführen:
   ```
   bash ~/Downloads/foto-vorauswahl/install.sh
   ```
   Den Pfad bei Bedarf anpassen. Der Installer lädt ein eigenes Python und die Bibliotheken sowie drei kleine KI-Modelle von Google MediaPipe (ca. 16 MB). Danach macht er einen Selbsttest.
3. In Capture One: **Scripts › Update Script Menu**. Danach steht dort **Auto-Vorauswahl**.
4. Beim ersten Start fragt macOS, ob das Script Capture One steuern darf. Mit **OK** bestätigen.

## Benutzung

**In Capture One:** Bilder auswählen, oder gar nichts auswählen für die ganze Sammlung. Dann **Scripts › Auto-Vorauswahl** aufrufen, Modus und Strenge wählen und festlegen, ob nur ein Prüfbericht entsteht oder Sterne und Farben gesetzt werden. Der **Prüfbericht** zeigt alle Serien als Kontaktbogen, mit Originaldatei, Ordner, Kategorie und Begründung pro Bild; die Vorschauen sind eingebettet, der Bericht lässt sich also weitergeben. Daneben liegt dieselbe Liste als CSV für Numbers/Excel.

**Ohne Capture One:** `~/Applications/Colada Vorauswahl.app` öffnen oder einen Ordner (z. B. den Projektordner auf dem NAS) auf das Symbol ziehen. Unterordner werden mit durchsucht. Standard ist „Nur Bericht": im Ordner wird nichts geschrieben. Optional können Sterne als XMP-Dateien neben RAW/JPG geschrieben werden (nie neben EIP-Dateien); Capture One übernimmt sie beim Import.

**Geschwindigkeit:** Gemessen wurden 183 Bilder in 34 Sekunden auf einem virtuellen Mac mit nur 3 Kernen. Auf einem aktuellen MacBook oder Mac Studio mit 8–12 Kernen sind für 2.000 Bilder grob 3–6 Minuten zu erwarten, inklusive Eintragen in Capture One. Mit echten Katalogen ist das noch nicht gemessen. Ein zweiter Lauf auf denselben Bildern mit anderer Strenge ist nach Sekunden fertig, weil die Analyse zwischengespeichert wird.

## Grenzen – ehrlich

- **Bildgestaltung bewertet das Tool nur grob** (angeschnittene Gesichter am Bildrand). Ob ein Bild für den Kunden „das Bild" ist, entscheidet weiter die Fotografin. Das Tool nimmt ihr die Fleißarbeit ab: Ausschuss raus, Duplikate zusammenfassen.
- **Gewollte Bewegungsunschärfe** (Mitzieher, laufende Maschine mit Langzeitbelichtung) wird als verwackelt eingestuft. Für solche Serien „Locker" wählen oder rot markierte Bilder kurz durchsehen.
- **Feinster Fehlfokus** ist auf den Vorschaubildern (ca. 1600 px) nicht sichtbar. Erkannt wird alles, was in der normalen Ansicht unscharf wirkt, plus Bilder, die innerhalb einer Serie schwächer sind.
- **Brandneue Kameras:** Kann die RAW-Bibliothek eine Datei nicht lesen, bleibt das Bild unverändert und wird im Bericht als „nicht lesbar" geführt.
- **Getestet** wurde mit generierten Test-Shootings: 61 Bilder je Durchlauf, in bis zu acht Zufallsvarianten, mit bekannter Soll-Auswahl. Bausteine waren echte Fotos und Videobilder. Gefahren ist das in einer Linux-Umgebung und automatisch auf einem Apple-Silicon-Mac (Installer, App, Engine, Syntax des Capture-One-Scripts). Zusätzlich gibt es einen **EIP-Test**: Er baut ein kleines Projekt aus EIP-Paketen (inkl. echter Nikon-RAW), DNG/JPG und Capture-One-Hilfsdateien und prüft Erkennung, Anzahl, Zuordnung zur Originaldatei, unveränderte Originale (Prüfsummen und Zeitstempel) und den Bericht.
- **Nicht getestet:** das Zusammenspiel mit einem laufenden Capture One. Capture One lässt sich auf Testservern nicht installieren. Die verwendeten Capture-One-Befehle stammen aus funktionierenden Community-Scripts. Ebenfalls nicht getestet: echte Picture-Colada-Shootings und EIP-Dateien aus der aktuellen Capture-One-Version (der Testaufbau folgt der dokumentierten Struktur: ZIP mit RAW, CaptureOne-Ordner, manifest.xml). Der erste echte Lauf sollte deshalb an einem abgeschlossenen Shooting stattfinden.

## Technik

- `engine/colada_cull/`: Analyse in Python mit OpenCV, MediaPipe (Gesichter, Augen, Bild-Fingerabdruck) und rawpy/LibRaw (RAW-Vorschauen). Läuft komplett lokal, ohne Cloud und ohne Kosten.
- `capture-one/Auto-Vorauswahl.applescript`: Script für das Capture-One-Menü. Es liest die Pfade, startet die Analyse im Hintergrund und setzt Sterne und Farbe.
- `app/Colada-Vorauswahl.applescript`: Ordner-App.
- `tests/`: Testgenerator, Soll-Ist-Vergleich, Einzeltests, EIP-Test (`test_eip.py`). Der automatische Mac-Test steht in `.github/workflows/foto-vorauswahl-macos.yml`.

Kommandozeile (für Tests):
```
cd ~/Library/Application\ Support/ColadaCull/engine
../venv/bin/python -m colada_cull --folder /Pfad/zum/Shooting --mode auto --strictness normal --report ~/Desktop/bericht.html
```

**Deinstallation:** Diese drei Pfade löschen:
- `~/Library/Application Support/ColadaCull`
- `~/Library/Scripts/Capture One Scripts/Auto-Vorauswahl.scpt`
- `~/Applications/Colada Vorauswahl.app`
