"""Ersetzt im Capture-One-Script alle Capture-One-Befehle durch neutrale Platzhalter, damit
osacompile den Rest (Dialoge, Fortschritt, Textverarbeitung, Handler) auch auf einem Mac ohne
Capture One auf Syntaxfehler prüfen kann.

Die Capture-One-Befehle selbst (selected variants, every variant of current collection,
path of parent image, rating, color tag, exists current document) stammen aus funktionierenden
Community-Scripts (github.com/walterrowe/capture-one-scripts).

Aufruf: python applescript_stub.py <eingabe.applescript> <ausgabe.applescript>
"""

import sys

REPLACEMENTS = [
    ('tell application "Capture One" to set docOpen to exists current document', "set docOpen to true"),
    ('tell application "Capture One" to set theVariants to selected variants', "set theVariants to {}"),
    ('tell application "Capture One" to tell current document\n\t\t\tset allVariants to every variant of current collection\n\t\tend tell',
     "set allVariants to {1, 2, 3}"),
    ('tell application "Capture One" to set p to path of parent image of (item i of theVariants)',
     "set p to (item i of theVariants) as text"),
    ('tell application "Capture One"\n\t\t\t\t\tset doIt to true', "tell me\n\t\t\t\t\tset doIt to true"),
    ("if (rating of v) > 0 or (color tag of v) > 0 then set doIt to false", "if v > 0 then set doIt to false"),
    ("set rating of v to newRating", "set _r to newRating"),
    ("set color tag of v to newColor", "set _c to newColor"),
]


def main(src, dst):
    s = open(src, encoding="utf-8").read()
    for old, new in REPLACEMENTS:
        if old not in s:
            raise SystemExit(f"Stelle nicht gefunden (Script geändert?): {old[:60]!r}")
        s = s.replace(old, new)
    if "Capture One\"" in s.replace('"Capture One Scripts', ""):
        rest = [l for l in s.splitlines() if 'application "Capture One"' in l]
        if rest:
            raise SystemExit(f"Nicht ersetzte Capture-One-Befehle: {rest}")
    open(dst, "w", encoding="utf-8").write(s)
    print("Platzhalter-Version geschrieben:", dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
