#!/usr/bin/env python3
"""E3: cost of Phase 1 (one open/append/close of <ino>.txt per trace line) against
trace length L, by the file system holding the working directory.

Variants, each on the same parsed trace:
  up_phase1   upstream processing.py cut after its Phase 1 loop (lines 1-61, generated
              below from the unmodified file; the cut point is asserted)
  fast_phase1 study fastpath.phase1 + writing each <ino>.txt once (same bytes)
Also records syscall counts per trace line for up_phase1 with `strace -c -f` (one run).
Run as root (mounts loop file systems for the working directory); /mnt is not used.
"""

import argparse
import os
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from fpstudy import corpus, fsimg, rungs  # noqa: E402

DATA = os.environ.get("FPSTUDY_DATA", "/root/fpstudy/data")
WORK = os.environ.get("FPSTUDY_WORK", "/root/fpstudy/work")
IMG = os.environ.get("FPSTUDY_IMG", "/root/fpstudy/img")
CODE = os.environ.get("FPSTUDY_CODE", "/root/fpstudy/code")

CUT_MARK = "    file_list.add(req_info[0])"


def make_up_phase1(dst):
    src = os.path.join(CODE, "upstream", "src", "analysis", "processing.py")
    lines = open(src).read().split("\n")
    idx = [i for i, l in enumerate(lines) if l.rstrip() == CUT_MARK]
    assert len(idx) == 1 and idx[0] == 60, idx  # line 61 in the file
    body = "\n".join(lines[:idx[0] + 1]) + "\ntrace_file.close()\n"
    with open(dst, "w") as f:
        f.write("# GENERATED from upstream src/analysis/processing.py lines 1-61 (Phase 1 only)\n" + body)
    return dst


FAST_P1 = r'''
import sys, os
sys.path.insert(0, %(lib)r)
from fpstudy import fastpath
pf = fastpath.phase1("./trace.result", "upstream")
for k, lines in pf.items():
    with open(k.decode() + ".txt", "ab") as f:
        f.writelines(lines)
'''


def run_variant(script, trace, wd):
    if os.path.exists(wd):
        subprocess.run(["rm", "-rf", wd], check=True)
    os.makedirs(wd)
    subprocess.run(["cp", trace, os.path.join(wd, "trace.result")], check=True)
    fsimg.drop_caches()
    t0 = time.perf_counter()
    subprocess.run([sys.executable, script], cwd=wd, check=True, env=dict(os.environ, LC_ALL="C"))
    return time.perf_counter() - t0


def strace_counts(script, trace, wd):
    if os.path.exists(wd):
        subprocess.run(["rm", "-rf", wd], check=True)
    os.makedirs(wd)
    subprocess.run(["cp", trace, os.path.join(wd, "trace.result")], check=True)
    r = subprocess.run(["strace", "-f", "-c", "-o", os.path.join(wd, "strace.txt"),
                        sys.executable, script], cwd=wd, check=True)
    counts = {}
    for line in open(os.path.join(wd, "strace.txt")):
        t = line.split()
        if len(t) >= 5 and t[0][0].isdigit() and t[-1].isidentifier():
            try:
                counts[t[-1]] = int(t[3])
            except ValueError:
                pass
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fs", default="root,ext4,xfs,btrfs,f2fs")
    ap.add_argument("--L", default="1000,10000,100000,1000000")
    ap.add_argument("--F", default="1,1000")
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--out", default="e3_phase1.jsonl")
    a = ap.parse_args()
    out = os.path.join(DATA, a.out)
    os.makedirs(WORK, exist_ok=True)
    os.makedirs(IMG, exist_ok=True)
    up = make_up_phase1(os.path.join(WORK, "up_phase1.py"))
    fast = os.path.join(WORK, "fast_phase1.py")
    with open(fast, "w") as f:
        f.write(FAST_P1 % {"lib": os.path.join(CODE, "study", "lib")})
    versions = rungs.code_versions()
    rnd = random.Random(5)
    for fsname in a.fs.split(","):
        fs = None
        if fsname == "root":
            base = os.path.join(WORK, "e3root")
            os.makedirs(base, exist_ok=True)
        else:
            base = "/root/fpstudy/e3mnt"
            fs = fsimg.TestFS(os.path.join(IMG, "e3_%s.img" % fsname), 3072, fsname, base)
        try:
            for F in [int(x) for x in a.F.split(",")]:
                for L in [int(x) for x in a.L.split(",")]:
                    if F > L:
                        continue
                    trace = os.path.join(base, "trace_F%d_L%d.result" % (F, L))
                    inodes = [100000 + i for i in range(F)]
                    corpus.gen_trace(trace, inodes, L // F)
                    if fsname == "root" and F == 1000 and L == 100000:
                        rec = {"exp": "e3", "kind": "strace", "fs": fsname, "F": F, "L": L,
                               "up_phase1": strace_counts(up, trace, os.path.join(base, "st")),
                               "versions": versions}
                        rungs.append_jsonl(out, rec)
                        print(rec, flush=True)
                    for rep in range(a.reps):
                        order = ["up_phase1", "fast_phase1"]
                        rnd.shuffle(order)
                        for v in order:
                            script = up if v == "up_phase1" else fast
                            wall = run_variant(script, trace, os.path.join(base, "wd"))
                            rec = {"exp": "e3", "kind": "time", "fs": fsname, "F": F, "L": L,
                                   "variant": v, "rep": rep, "wall_s": wall, "versions": versions,
                                   "ts": time.time()}
                            rungs.append_jsonl(out, rec)
                            print("%-6s F=%-5d L=%-8d %-12s rep=%d %.3fs" % (fsname, F, L, v, rep, wall), flush=True)
                    os.remove(trace)
        finally:
            subprocess.run(["rm", "-rf", os.path.join(base, "wd"), os.path.join(base, "st")])
            if fs:
                fs.close()


if __name__ == "__main__":
    main()
