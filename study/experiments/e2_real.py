#!/usr/bin/env python3
"""E2 (real traces): replay the complete (unbuffered) traces captured by E0 against
the same file system image, through every rung, and time the whole upstream analysis
pipeline step by step (processing.py, merge.py, hotness.sh) against the single-thread
rewrite of the same three steps (fastpath --full).

Needs $FPSTUDY_IMG/e0.img and $FPSTUDY_DATA/e0_traces/*.unbuffered.parsed.gz from E0.
Run inside study/bin/run_in_ns.sh. One JSON line per run in e2_real.jsonl.
"""

import argparse
import gzip
import os
import random
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from fpstudy import fsimg, rungs  # noqa: E402

DATA = os.environ.get("FPSTUDY_DATA", "/root/fpstudy/data")
WORK = os.environ.get("FPSTUDY_WORK", "/root/fpstudy/work")
IMG = os.environ.get("FPSTUDY_IMG", "/root/fpstudy/img")
CODE = os.environ.get("FPSTUDY_CODE", "/root/fpstudy/code")
UPA = os.path.join(CODE, "upstream", "src", "analysis")
MNT = "/mnt"


def run_upstream_pipeline(trace, wd, pct=100, timeout=7200):
    """upstream processing.py, then merge.py, then hotness.sh <pct>, each timed."""
    if os.path.exists(wd):
        shutil.rmtree(wd)
    os.makedirs(wd)
    shutil.copy(trace, os.path.join(wd, "trace.result"))
    env = dict(os.environ, LC_ALL="C", PYTHONDONTWRITEBYTECODE="1")
    steps = [("processing", [sys.executable, os.path.join(UPA, "processing.py")]),
             ("merge", [sys.executable, os.path.join(UPA, "merge.py")]),
             ("hotness", ["bash", os.path.join(UPA, "hotness.sh"), str(pct)])]
    out = {}
    for name, cmd in steps:
        t0 = time.perf_counter()
        p = subprocess.run(cmd, cwd=wd, env=env, capture_output=True, timeout=timeout)
        out[name + "_s"] = time.perf_counter() - t0
        if p.returncode != 0:
            out["status"] = "%s rc=%d" % (name, p.returncode)
            return out
    out["status"] = "ok"
    out["digest_full"] = rungs.digest(wd, with_pipeline=True)[0]
    return out


def run_fast_pipeline(trace, wd, pct=100):
    if os.path.exists(wd):
        shutil.rmtree(wd)
    os.makedirs(wd)
    shutil.copy(trace, os.path.join(wd, "trace.result"))
    t0 = time.perf_counter()
    subprocess.run([sys.executable, os.path.join(CODE, "study", "lib", "fpstudy", "fastpath.py"),
                    "--mount-point", MNT, "--full", "--pct", str(pct)], cwd=wd, check=True,
                   env=dict(os.environ, LC_ALL="C"))
    return {"total_s": time.perf_counter() - t0, "status": "ok",
            "digest_full": rungs.digest(wd, with_pipeline=True)[0]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workloads", default="read_seq,read_stride,tar,fio,sqlite3")
    ap.add_argument("--rungs", default="a,b,c,d1,d8,d16,e8")
    ap.add_argument("--caches", default="warm,cold")
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--pct", type=int, default=100)
    ap.add_argument("--out", default="e2_real.jsonl")
    a = ap.parse_args()
    out = os.path.join(DATA, a.out)
    rnd = random.Random(17)
    versions = rungs.code_versions()
    fs = fsimg.TestFS(os.path.join(IMG, "e0.img"), 8192, "ext4", MNT, fresh=False)
    try:
        for w in a.workloads.split(","):
            gz = os.path.join(DATA, "e0_traces", w + ".unbuffered.parsed.gz")
            if not os.path.exists(gz):
                print("missing", gz); continue
            trace = os.path.join(WORK, "e2real_%s.result" % w)
            with gzip.open(gz, "rb") as fi, open(trace, "wb") as fo:
                shutil.copyfileobj(fi, fo)
            L = sum(1 for _ in open(trace, "rb"))
            for cache in a.caches.split(","):
                items = a.rungs.split(",") + ["pipe_a", "pipe_c"]
                if cache == "warm":
                    for r in a.rungs.split(","):
                        rungs.run_rung(r, trace, os.path.join(WORK, "e2r", "warm", r))
                for rep in range(a.reps):
                    rnd.shuffle(items)
                    for r in items:
                        if cache == "cold":
                            fs.remount_cold()
                        s0 = fs.stat()
                        if r == "pipe_a":
                            res = run_upstream_pipeline(trace, os.path.join(WORK, "e2r", r), a.pct)
                            res["rung"] = r
                        elif r == "pipe_c":
                            res = run_fast_pipeline(trace, os.path.join(WORK, "e2r", r), a.pct)
                            res["rung"] = r
                        else:
                            res = rungs.run_rung(r, trace, os.path.join(WORK, "e2r", r))
                        res["io"] = fsimg.blk_delta(s0, fs.stat())
                        rec = {"exp": "e2real", "workload": w, "L": L, "cache": cache, "rep": rep,
                               "fs": "ext4", "T": None, "F": None, "delay_ms": None,
                               "versions": versions, "ts": time.time()}
                        rec.update(res)
                        rungs.append_jsonl(out, rec)
                        print("%-11s %-5s rep=%d %-7s %s %s" % (
                            w, cache, rep, r, res.get("status"),
                            " ".join("%s=%.3f" % (k, v) for k, v in res.items() if k.endswith("_s"))),
                            flush=True)
            os.remove(trace)
    finally:
        fs.close(delete=False)


if __name__ == "__main__":
    main()
