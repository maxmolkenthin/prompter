"""Vergleicht die Engine-Ausgabe (TSV) mit der Soll-Auswahl eines Test-Shootings."""
import itertools, json, sys
from pathlib import Path

def main(shoot, results_tsv, listfile):
    truth = {t["file"]: t for t in json.loads((Path(shoot) / "_truth.json").read_text())}
    paths = [l.strip() for l in Path(listfile).read_text().splitlines()]
    res = {}
    for p, line in zip(paths, Path(results_tsv).read_text().splitlines()):
        r, c, st, reason = (line.split("\t") + [""] * 4)[:4]
        res[Path(p).name] = (st, reason)
    errors = 0
    for f, t in truth.items():
        st, reason = res[f]
        e = t["expect"]
        ok = (e == "any" or (e == "pick" and st == "pick") or (e == "notpick" and st != "pick")
              or (e == "reject" and st == "reject") or (e == "alt" and st == "alt"))
        errors += not ok
        print(f"{'OK ' if ok else 'XX '} {f} [{t['series']:>3}] soll={e:<8} ist={st:<7} {reason}  ({t['note']})")
    print(f"\n{len(truth) - errors}/{len(truth)} Erwartungen erfüllt")
    return errors

if __name__ == "__main__":
    sys.exit(1 if main(*sys.argv[1:4]) else 0)
