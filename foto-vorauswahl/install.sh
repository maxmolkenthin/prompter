#!/bin/bash
# Colada Vorauswahl – Installation auf dem Mac (einmalig, ohne Admin-Rechte, ca. 3–5 Minuten)
#
#   1. Terminal öffnen
#   2. bash /Pfad/zu/foto-vorauswahl/install.sh
#
# Installiert:
#   ~/Library/Application Support/ColadaCull/   Analyse-Engine, eigenes Python, KI-Modelle
#   ~/Library/Scripts/Capture One Scripts/Auto-Vorauswahl.scpt   (Menü "Scripts" in Capture One)
#   ~/Applications/Colada Vorauswahl.app        (Ordner-Variante ohne Capture One)
#
# Deinstallation: die drei Pfade oben löschen.

set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
BASE="$HOME/Library/Application Support/ColadaCull"
C1_SCRIPTS="$HOME/Library/Scripts/Capture One Scripts"
APP_DIR="$HOME/Applications"

say() { printf "\n\033[1m%s\033[0m\n" "$*"; }

if [[ "$(uname)" != "Darwin" ]]; then
  echo "Dieses Skript ist für macOS gedacht." >&2
  exit 1
fi

say "1/6  uv (Python-Verwaltung) prüfen"
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv --version

say "2/6  Eigenes Python 3.12 + Bibliotheken installieren"
mkdir -p "$BASE"
if [[ ! -x "$BASE/venv/bin/python" ]]; then
  uv venv --python 3.12 "$BASE/venv"
fi
uv pip install --python "$BASE/venv/bin/python" -r "$SRC/engine/requirements.txt"

say "3/6  Analyse-Engine kopieren"
mkdir -p "$BASE/engine"
rm -rf "$BASE/engine/colada_cull"
cp -R "$SRC/engine/colada_cull" "$BASE/engine/colada_cull"
find "$BASE/engine" -name "__pycache__" -type d -prune -exec rm -rf {} +

say "4/6  KI-Modelle laden (ca. 16 MB)"
(cd "$BASE/engine" && "$BASE/venv/bin/python" -m colada_cull.setup_models "$BASE/engine/models")

say "5/6  Selbsttest"
TEST_DIR="$(mktemp -d)"
"$BASE/venv/bin/python" - "$TEST_DIR" <<'PY'
import sys, numpy as np
from PIL import Image
d = sys.argv[1]
rng = np.random.default_rng(0)
img = (rng.random((800, 1200, 3)) * 255).astype(np.uint8)
for i in range(3):
    Image.fromarray(img).save(f"{d}/TEST_{i}.jpg", quality=90)
PY
(cd "$BASE/engine" && "$BASE/venv/bin/python" -m colada_cull --folder "$TEST_DIR" --no-cache)
rm -rf "$TEST_DIR"

say "6/6  Capture-One-Script und Mac-App einrichten"
C1_APP="$(ls -d /Applications/Capture\ One*.app 2>/dev/null | sort | tail -n 1 || true)"
if [[ -n "$C1_APP" ]]; then
  C1_NAME="$(basename "$C1_APP" .app)"
  mkdir -p "$C1_SCRIPTS"
  TMP_SCRIPT="$(mktemp).applescript"
  sed "s/application \"Capture One\"/application \"$C1_NAME\"/g" "$SRC/capture-one/Auto-Vorauswahl.applescript" > "$TMP_SCRIPT"
  osacompile -o "$C1_SCRIPTS/Auto-Vorauswahl.scpt" "$TMP_SCRIPT"
  rm -f "$TMP_SCRIPT"
  echo "Capture-One-Script installiert für: $C1_NAME"
else
  echo "Capture One nicht in /Applications gefunden – Capture-One-Script übersprungen."
fi
mkdir -p "$APP_DIR"
rm -rf "$APP_DIR/Colada Vorauswahl.app"
osacompile -o "$APP_DIR/Colada Vorauswahl.app" "$SRC/app/Colada-Vorauswahl.applescript"
echo "App installiert: $APP_DIR/Colada Vorauswahl.app"

say "Fertig."
cat <<TXT
In Capture One:  Menü Scripts > Update Script Menu, danach Scripts > Auto-Vorauswahl
                 (beim ersten Start fragt macOS einmal nach der Erlaubnis – mit OK bestätigen)
Ohne Capture One: ~/Applications/Colada Vorauswahl.app öffnen oder einen Ordner daraufziehen
TXT
