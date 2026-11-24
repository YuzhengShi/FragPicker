#!/usr/bin/env python3
"""E2: the ablation ladder (PLAN.md RQ1/RQ2) on synthetic traces.

For each cell (fs, T files in the tree, F traced files, cache state, optional dm-delay)
every rung runs `--reps` times, rung order shuffled in every repetition. A rung whose
runs exceed `--budget-s` in total stops after at least 3 repetitions (recorded).
Run inside study/bin/run_in_ns.sh. One JSON line per run in $FPSTUDY_DATA/<out>.

Example:
  e2_ladder.py --T 10000 --F 1,10,100,1000,10000 --cache warm --reps 10
"""

import argparse
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from fpstudy import corpus, fsimg, rungs  # noqa: E402

DATA = os.environ.get("FPSTUDY_DATA", "/root/fpstudy/data")
WORK = os.environ.get("FPSTUDY_WORK", "/root/fpstudy/work")
IMG = os.environ.get("FPSTUDY_IMG", "/root/fpstudy/img")
MNT = "/mnt"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fs", default="ext4")
    ap.add_argument("--T", type=int, required=True, help="files in the tree")
    ap.add_argument("--F", default="1,10,100,1000", help="traced files (comma list)")
    ap.add_argument("--lines-per-file", type=int, default=20)
    ap.add_argument("--file-kb", type=int, default=16)
    ap.add_argument("--per-dir", type=int, default=100)
    ap.add_argument("--rungs", default="a,b,c,d1,d4,d8,d16,e8")
    ap.add_argument("--cache", default="warm", choices=["warm", "cold"])
    ap.add_argument("--delay-ms", type=int, default=None, help="dm-delay on reads")
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--budget-s", type=float, default=900.0)
    ap.add_argument("--timeout-s", type=float, default=3600.0)
    ap.add_argument("--out", default="e2_ladder.jsonl")
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()

    out = os.path.join(DATA, a.out)
    rnd = random.Random(a.seed)
    rung_list = a.rungs.split(",")
    Fs = [int(x) for x in a.F.split(",")]
    size_mb = max(1024, int(a.T * (a.file_kb + 8) / 1024 * 1.6) + 512)
    img = os.path.join(IMG, "e2_%s_T%d.img" % (a.fs, a.T))
    # build the tree without delay, then (optionally) put dm-delay underneath for the runs
    fs = fsimg.TestFS(img, size_mb, a.fs, MNT)
    try:
        t0 = time.time()
        files = corpus.make_tree(MNT, a.T, per_dir=a.per_dir, size=a.file_kb * 1024, seed=a.seed)
        build_s = time.time() - t0
        print("tree: T=%d built in %.1fs" % (a.T, build_s), flush=True)
        if a.delay_ms is not None:
            fs.set_delay(a.delay_ms)
        versions = rungs.code_versions()
        for F in Fs:
            if F > a.T:
                continue
            traced = [ino for ino, _ in rnd.sample(files, F)]
            trace = os.path.join(WORK, "e2_trace_T%d_F%d.result" % (a.T, F))
            L = corpus.gen_trace(trace, traced, a.lines_per_file)
            cell = {"fs": a.fs, "T": a.T, "F": F, "L": L, "cache": a.cache,
                    "delay_ms": a.delay_ms, "file_kb": a.file_kb, "per_dir": a.per_dir}
            spent = {r: 0.0 for r in rung_list}
            done = {r: 0 for r in rung_list}
            if a.cache == "warm":  # one discarded warm-up run per rung
                for r in rung_list:
                    rungs.run_rung(r, trace, os.path.join(WORK, "e2", "warm", r), timeout=a.timeout_s)
            for rep in range(a.reps):
                order = rung_list[:]
                rnd.shuffle(order)
                for r in order:
                    if done[r] >= 3 and spent[r] > a.budget_s:
                        continue
                    if a.cache == "cold":
                        fs.remount_cold()
                    before = fs.stat()
                    res = rungs.run_rung(r, trace, os.path.join(WORK, "e2", "run", r), timeout=a.timeout_s)
                    io = fsimg.blk_delta(before, fs.stat())
                    spent[r] += res["wall_s"]
                    done[r] += 1
                    rec = {"exp": "e2", "rep": rep, "order": order.index(r), "ts": time.time(),
                           "versions": versions, "tree_build_s": build_s, "io": io}
                    rec.update(cell)
                    rec.update(res)
                    rungs.append_jsonl(out, rec)
                    print("T=%-6d F=%-5d %-5s rep=%d %-7s wall=%8.3fs user=%.2f sys=%.2f reads=%d dg=%s" % (
                        a.T, F, r, rep, res["status"], res["wall_s"], res["user_s"], res["sys_s"],
                        io["read_ios"], res["digest"]), flush=True)
    finally:
        fs.close()


if __name__ == "__main__":
    main()
