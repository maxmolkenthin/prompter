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
| `index.html` (Repo-Wurzel) | gebaute App, wird von GitHub Pages ausgeliefert |
| `src/index.html` | Quelltext; dieselbe Datei läuft auch als claude.ai-Artifact |
| `build.py`, `sw.template.js` | bauen die App: `python3 build.py` |
| `peerjs.min.js` | PeerJS 1.5.4 (MIT) für die Direktverbindung |
| `prompter-laden/SKILL.md` | Claude-Skill: Skript aus ClickUp/Drive holen, Kapitel setzen, laden |

Skripte werden nur im Browser des jeweiligen Geräts gespeichert, nicht in diesem Repository.
