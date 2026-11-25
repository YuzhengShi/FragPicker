#!/usr/bin/env python3
"""E14 (exploratory): does the interpreter lock also limit the parallel path's main cost,
starting a `sort` process per file?

Starts N `sort -g <file>` processes exactly as the fork's ParallelSorter does
(subprocess.run with stdout to a file and stderr piped), from W threads of one
interpreter, and for comparison from W worker processes (a multiprocessing pool started
before timing), each doing N/W. If threads plateau where processes keep scaling, the
limit is in the interpreter, not in the kernel. The interpreter is whatever runs this.
"""

import argparse
import concurrent.futures as cf
import multiprocessing as mp
import os
import random
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from fpstudy import rungs  # noqa: E402

DATA = os.environ.get("FPSTUDY_DATA", "/root/fpstudy/data")
WORK = os.path.join(os.environ.get("FPSTUDY_WORK", "/root/fpstudy/work"), "e14")


def spawn_many(args):
    wid, count = args
    src = os.path.join(WORK, "in.txt")
    dst = os.path.join(WORK, "out%02d.txt" % wid)
    for _ in range(count):
        with open(dst, "w") as outf:
            r = subprocess.run(["sort", "-g", src], stdout=outf, stderr=subprocess.PIPE, timeout=60)
        if r.returncode != 0:
            raise RuntimeError(r.stderr)
    return count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--N", type=int, default=1000)
    ap.add_argument("--workers", default="1,2,4,8,16")
    ap.add_argument("--modes", default="threads,processes")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--out", default="e14_spawn.jsonl")
    a = ap.parse_args()
    os.makedirs(WORK, exist_ok=True)
    rnd = random.Random(14)
    with open(os.path.join(WORK, "in.txt"), "w") as f:  # a request file: 20 lines
        for _ in range(20):
            f.write("%d %d\n" % (rnd.randrange(1 << 20), rnd.randrange(1, 64)))
    out = os.path.join(DATA, a.out)
    versions = rungs.code_versions()
    py = sys.version.split()[0]
    gil = getattr(sys, "_is_gil_enabled", lambda: True)()
    ws = [int(x) for x in a.workers.split(",")]
    spawn_many((99, 20))  # warm-up: binaries and page cache
    pool = mp.get_context("fork").Pool(max(ws))
    try:
        pool.map(spawn_many, [(90 + i, 2) for i in range(max(ws))])  # warm the workers
        for rep in range(a.reps):
            cells = [(m, w) for m in a.modes.split(",") for w in ws]
            rnd.shuffle(cells)
            for mode, w in cells:
                parts = [(i, a.N // w + (1 if i < a.N % w else 0)) for i in range(w)]
                t0 = time.perf_counter()
                if mode == "threads":
                    if w == 1:
                        spawn_many(parts[0])
                    else:
                        with cf.ThreadPoolExecutor(w) as ex:
                            list(ex.map(spawn_many, parts))
                else:
                    pool.map(spawn_many, parts, chunksize=1)
                wall = time.perf_counter() - t0
                rec = {"exp": "e14", "mode": mode, "workers": w, "N": a.N, "rep": rep, "wall_s": wall,
                       "spawns_per_s": a.N / wall, "python": py, "gil_enabled": gil,
                       "versions": versions, "ts": time.time()}
                rungs.append_jsonl(out, rec)
                print("py%s gil=%s %-9s W=%-2d rep=%d %.3fs  %.0f spawns/s" % (
                    py, gil, mode, w, rep, wall, rec["spawns_per_s"]), flush=True)
    finally:
        pool.terminate()


if __name__ == "__main__":
    main()
