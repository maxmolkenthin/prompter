# Colada Vorauswahl – automatisches Culling für Capture One

Ein Klick in Capture One, und die Vorauswahl eines Shootingtags ist gemacht:

| Ergebnis | Capture One | Bedeutung |
|---|---|---|
| **Auswahl** | ★★★ + Grün | bestes bzw. letztes scharfes Bild jeder Serie |
| **Alternative** | ★ | gleiche Einstellung, technisch ok, aber nicht das gewählte Bild |
| **Aussortiert** | 0 Sterne + Rot | unscharf, verwackelt, Augen zu, Fehlauslösung |

Es wird **nichts gelöscht oder verschoben**. Danach in Capture One nach Farbe Grün filtern.

## Was die Vorauswahl prüft

1. **Serien erkennen:** Bilder vom selben Motiv aus demselben Winkel werden zu einer Serie zusammengefasst. Grundlage sind Bildinhalt (KI-Fingerabdruck), Bildaufbau und Aufnahmezeit. Ein anderer Winkel, eine Totale gegenüber einem Detail oder Hoch- gegenüber Querformat ergeben jeweils eine eigene Serie. Kommt der Fotograf später zum gleichen Motiv zurück (A–B–A), wird das erkannt.
2. **Unschärfe/Verwackeln:** Die Kantenschärfe wird im schärfsten Bildbereich gemessen. Freisteller mit unscharfem Hintergrund fallen deshalb nicht raus. Die Messung läuft in vier Richtungen, so dass auch Verwacklung in nur einer Richtung auffällt. Bildrauschen (hohe ISO) wird vorher herausgerechnet. Ein Bild fällt raus, wenn es absolut unscharf ist oder deutlich unschärfer als das beste Bild seiner Serie.
3. **Personen:** Gesichter werden auch klein im Bild gefunden. Gemessen werden Augen offen/zu, Kopfhaltung und Blickrichtung.
   - Blinzeln wird aussortiert, solange die Serie ein besseres Bild hat.
   - Blick nach unten aufs Werkstück und Lachen gelten nicht als „Augen zu".
   - Haben alle Bilder einer Serie das Problem, bleibt das beste mit Hinweis drin, damit der Moment nicht verloren geht.
4. **Auswahl pro Serie:** Es gewinnt der **letzte Schuss**, sofern er voll scharf ist. Bei Personen muss er außerdem bei Augen und Blick mithalten können. Ab 12 Bildern in einer Serie werden zwei Bilder ausgewählt.
5. **Fehlauslösungen:** Fast schwarze Bilder (Blitz nicht ausgelöst) und fast weiße Bilder werden aussortiert. Low-Key-Aufnahmen und Freisteller auf Weiß gelten dabei ausdrücklich nicht als Fehler.

### Modus und Strenge (wird bei jedem Start abgefragt)

- **Automatisch:** für gemischte Shootings, Gesichter werden berücksichtigt, wenn vorhanden.
- **Produkt / Detail** und **Architektur:** Gesichter werden ignoriert, es gilt nur Schärfe und „letzter Schuss".
- **Prozess / Reportage:** Augen-Regel lockerer, Blick in die Kamera egal.
- **Menschen / Porträt:** Blick in die Kamera zählt stark.
- **Locker / Normal / Streng:** Locker behält im Zweifel mehr, auch mehr Duplikate. Streng fasst Serien großzügiger zusammen und sortiert Unschärfe härter aus.

## Installation (einmalig, ca. 5 Minuten, keine Admin-Rechte)

1. Den Ordner `foto-vorauswahl` auf den Mac kopieren.
2. Terminal öffnen und ausführen:
   ```
   bash ~/Downloads/foto-vorauswahl/install.sh
   ```
   Den Pfad bei Bedarf anpassen. Der Installer lädt ein eigenes Python und die Bibliotheken sowie drei kleine KI-Modelle von Google MediaPipe (ca. 16 MB). Danach macht er einen Selbsttest.
3. In Capture One: **Scripts › Update Script Menu**. Danach steht dort **Auto-Vorauswahl**.
4. Beim ersten Start fragt macOS, ob das Script Capture One steuern darf. Mit **OK** bestätigen.

## Benutzung

**In Capture One:** Bilder auswählen, oder gar nichts auswählen für die ganze Sammlung. Dann **Scripts › Auto-Vorauswahl** aufrufen, Modus und Strenge wählen und festlegen, ob vorhandene Bewertungen überschrieben werden. Am Ende kann man einen **Prüfbericht** öffnen. Er zeigt alle Serien als Kontaktbogen, mit Begründung pro Bild.

**Ohne Capture One:** `~/Applications/Colada Vorauswahl.app` öffnen oder einen Ordner auf das Symbol ziehen. Die Sterne werden als XMP-Dateien neben die RAWs geschrieben, Capture One übernimmt sie beim Import. Farbmarkierungen aus XMP liest Capture One laut Nutzerberichten nicht zuverlässig. Im Ordner-Modus zählen deshalb die Sterne: 3 = Auswahl, 1 = Alternative, 0 = aussortiert.

**Geschwindigkeit:** Ein zweiter Lauf auf denselben Bildern mit anderer Strenge ist nach Sekunden fertig, weil die Analyse zwischengespeichert wird.

## Grenzen – ehrlich

- **Bildgestaltung bewertet das Tool nicht.** Ob ein Bild für den Kunden „das Bild" ist, entscheidet weiter die Fotografin. Das Tool nimmt ihr die Fleißarbeit ab: Ausschuss raus, Duplikate zusammenfassen.
- **Gewollte Bewegungsunschärfe** (Mitzieher, laufende Maschine mit Langzeitbelichtung) wird als verwackelt eingestuft. Für solche Serien „Locker" wählen oder rot markierte Bilder kurz durchsehen.
- **Feinster Fehlfokus** ist auf den Vorschaubildern (ca. 1600 px) nicht sichtbar. Erkannt wird alles, was in der normalen Ansicht unscharf wirkt, plus Bilder, die innerhalb einer Serie schwächer sind.
- **Brandneue Kameras:** Kann die RAW-Bibliothek eine Datei nicht lesen, bleibt das Bild unverändert und wird im Bericht als „nicht lesbar" geführt.
- Getestet wurde mit generierten Test-Shootings: 61 Bilder in sechs Zufallsvarianten, mit bekannter Soll-Auswahl. Gefahren ist das in einer Linux-Umgebung und automatisch auf einem Apple-Silicon-Mac. **Mit echten Capture-One-Katalogen von Picture Colada ist es noch nicht getestet.** Der erste echte Lauf sollte deshalb an einer Kopie oder einem abgeschlossenen Shooting stattfinden.

## Technik

- `engine/colada_cull/`: Analyse in Python mit OpenCV, MediaPipe (Gesichter, Augen, Bild-Fingerabdruck) und rawpy/LibRaw (RAW-Vorschauen). Läuft komplett lokal, ohne Cloud und ohne Kosten.
- `capture-one/Auto-Vorauswahl.applescript`: Script für das Capture-One-Menü. Es liest die Pfade, startet die Analyse im Hintergrund und setzt Sterne und Farbe.
- `app/Colada-Vorauswahl.applescript`: Ordner-App.
- `tests/`: Testgenerator, Soll-Ist-Vergleich, Einzeltests. Der automatische Mac-Test steht in `.github/workflows/foto-vorauswahl-macos.yml`.

Kommandozeile (für Tests):
```
cd ~/Library/Application\ Support/ColadaCull/engine
../venv/bin/python -m colada_cull --folder /Pfad/zum/Shooting --mode auto --strictness normal --report ~/Desktop/bericht.html
```

**Deinstallation:** Diese drei Pfade löschen:
- `~/Library/Application Support/ColadaCull`
- `~/Library/Scripts/Capture One Scripts/Auto-Vorauswahl.scpt`
- `~/Applications/Colada Vorauswahl.app`
