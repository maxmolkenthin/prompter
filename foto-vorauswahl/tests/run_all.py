"""Erzeugt beide Test-Shootings mit mehreren Zufalls-Seeds und prüft die Engine dagegen.

Aufruf: python run_all.py <quellordner> <frames-ordner> <arbeitsordner> [--models DIR] [--seeds 7,11,12]
Rückgabe 0 nur, wenn alle Erwartungen in allen Durchläufen erfüllt sind.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent / "engine"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("frames")
    ap.add_argument("work")
    ap.add_argument("--models", default=None)
    ap.add_argument("--seeds", default="7,11,12,13,14,15")
    ap.add_argument("--strictness", default="normal")
    a = ap.parse_args()
    work = Path(a.work).resolve()
    a.src, a.frames = str(Path(a.src).resolve()), str(Path(a.frames).resolve())
    work.mkdir(parents=True, exist_ok=True)
    failed = 0
    total = 0
    for seed in a.seeds.split(","):
        env = dict(os.environ, SEED=seed)
        for name, cmd in (("set1", [sys.executable, HERE / "make_testshoot.py", a.src, a.frames]),
                          ("set2", [sys.executable, HERE / "make_holdout.py", a.src])):
            d = work / f"{name}_{seed}"
            shutil.rmtree(d, ignore_errors=True)
            subprocess.run([*map(str, cmd), str(d)], env=env, check=True, stdout=subprocess.DEVNULL)
            lst = work / f"{name}_{seed}.list"
            lst.write_text("\n".join(str(p) for p in sorted(d.glob("*.jpg"))) + "\n")
            res = work / f"{name}_{seed}.tsv"
            run = [sys.executable, "-m", "colada_cull", "--list", str(lst), "--results", str(res),
                   "--strictness", a.strictness, "--report", str(work / f"{name}_{seed}.html")]
            if a.models:
                run += ["--models", a.models]
            subprocess.run(run, cwd=ENGINE, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            out = subprocess.run([sys.executable, HERE / "evaluate.py", d, res, lst], capture_output=True, text=True)
            bad = [l for l in out.stdout.splitlines() if l.startswith("XX")]
            total += 1
            failed += bool(bad)
            print(f"Seed {seed} {name}: {out.stdout.strip().splitlines()[-1]}")
            for l in bad:
                print("   ", l)
    print(f"\n{total - failed}/{total} Durchläufe fehlerfrei")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
