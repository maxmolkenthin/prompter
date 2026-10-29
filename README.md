# Colada Prompter

Teleprompter-Web-App von Picture Colada: Skripte mit Kapitelmarken, horizontal und vertikal spiegeln, Schrift und Tempo, Hochkontrast. Fernbedienung per Handy (Kopplungscode) oder Bluetooth-Clicker.

**App:** https://maxmolkenthin.github.io/prompter/

## Auf dem iPad installieren

1. Die Adresse oben in **Safari** öffnen.
2. Teilen-Symbol → **„Zum Home-Bildschirm“** → Hinzufügen.
3. Ab jetzt die App über das Symbol „Prompter“ starten. Sie läuft im Vollbild und nach dem ersten Start auch offline.

Fernbedienung: dieselbe Adresse auf dem Handy öffnen, „Fernbedienung“ wählen, den 4-stelligen Code vom iPad eingeben. Beide Geräte brauchen dafür Internet (WLAN oder Hotspot).

## Aufbau

| Datei | Zweck |
|---|---|
| `index.html`, `peerjs.min.js`, `pako_inflate.min.js`, `sw.js` | gebaute App, wird von GitHub Pages ausgeliefert (für Safari 12 / iOS 12 übersetzt) |
| `src/index.html` | Quelltext; dieselbe Datei läuft auch als claude.ai-Artifact |
| `build.py`, `sw.template.js` | bauen die App: `python3 build.py` (braucht Node.js, holt esbuild per npx) |
| `vendor/` | Originale der Bibliotheken: PeerJS 1.5.4 (MIT), pako_inflate 2.1.0 (MIT/Zlib) |
| `prompter-laden/SKILL.md` | Claude-Skill: Skript aus ClickUp/Drive holen, Kapitel setzen, Ein-Tipp-Link erzeugen |

## Skript aufs iPad bringen

Claude erzeugt einen Link (`…/prompter/#s=…` für ein Skript, `…/prompter/#p=…` für ein ganzes Drehpaket). Den Link auf dem Handy antippen: Die Seite „Skript empfangen“ schickt alles automatisch an das zuletzt gekoppelte iPad. Beim ersten Mal einmal den 4-stelligen Code vom iPad eingeben. Am Set wird über „Film wählen“ auf der Fernbedienung oder die Auswahl in der Prompter-Leiste gewechselt.

Skripte werden nur im Browser des jeweiligen Geräts gespeichert, nicht in diesem Repository.
