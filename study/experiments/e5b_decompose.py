#!/usr/bin/env python3
"""E5b: where the cold-cache device time of E5's 'scattered' case goes.

Same layout as E5 (N traced files sampled from a tree of 100*N files of 4 KiB), cold
cache before every measurement, three device models (plain loop, dm-delay d,
one-request-at-a-time nbd d). Per repetition:
  walk          the fork's build_inode_map (one find over the tree) alone
  walk+files    the walk, then the sequential per-file lookups (os.path.isdir +
                FiemapAnalyzer.get_extents), timed separately, reads counted separately
  files-only/W  the per-file lookups with the paths already known (no walk), on W
                threads: what parallel lookups could gain if no tree walk were needed
Run inside study/bin/run_in_ns.sh (uses /mnt).
"""

import argparse
import concurrent.futures as cf
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from fpstudy import corpus, fsimg, rungs  # noqa: E402

CODE = os.environ.get("FPSTUDY_CODE", "/root/fpstudy/code")
sys.path.insert(0, os.path.join(CODE, "fork", "src", "analysis"))
from parallel_analyzer.fiemap import FiemapAnalyzer  # noqa: E402
from parallel_analyzer.inode_mapper import build_inode_map  # noqa: E402

sys.path.insert(0, HERE)
from e5_latency import NbdDevice  # noqa: E402

DATA = os.environ.get("FPSTUDY_DATA", "/root/fpstudy/data")
IMG = os.environ.get("FPSTUDY_IMG", "/root/fpstudy/img")
MNT = "/mnt"


def lookups(paths, threads):
    if threads == 1:
        fa = FiemapAnalyzer()
        t0 = time.perf_counter()
        for p in paths:
            if not os.path.isdir(p):
                fa.get_extents(p)
        return time.perf_counter() - t0
    fas = [FiemapAnalyzer() for _ in range(threads)]
    chunks = [paths[i::threads] for i in range(threads)]

    def work(i):
        for p in chunks[i]:
            if not os.path.isdir(p):
                fas[i].get_extents(p)

    t0 = time.perf_counter()
    with cf.ThreadPoolExecutor(threads) as ex:
        list(ex.map(work, range(threads)))
    return time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--N", type=int, default=1000)
    ap.add_argument("--delay-ms", type=int, default=5)
    ap.add_argument("--models", default="plain,dmdelay,qd1")
    ap.add_argument("--threads", default="1,4,16")
    ap.add_argument("--layouts", default="scattered,together")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--out", default="e5b_decompose.jsonl")
    a = ap.parse_args()
    out = os.path.join(DATA, a.out)
    versions = rungs.code_versions()
    rnd = random.Random(33)
    for layout in a.layouts.split(","):
        T = 100 * a.N if layout == "scattered" else a.N
        size_kb = 4 if layout == "scattered" else 100
        img = os.path.join(IMG, "e5b_%s.img" % layout)
        size_mb = max(1024, int(T * (size_kb + 8) / 1024 * 1.5) + 512)
        fs = fsimg.TestFS(img, size_mb, "ext4", MNT)
        files = corpus.make_tree(MNT, T, per_dir=100, size=size_kb * 1024, seed=4)
        traced = rnd.sample(files, a.N) if layout == "scattered" else files
        paths = [p for _, p in traced]
        fs.close(delete=False)
        for model in a.models.split(","):
            nbd = None
            if model == "qd1":
                nbd = NbdDevice(img, a.delay_ms, threads=1)
                dev = nbd.nbd
            else:
                fs = fsimg.TestFS(img, size_mb, "ext4", MNT, fresh=False,
                                  delay_ms=a.delay_ms if model == "dmdelay" else None)
                fsimg.umount(MNT)
                dev = fs.dev
            d = a.delay_ms if model != "plain" else 0

            def cold():
                fsimg.umount(MNT)
                fsimg.drop_caches()
                fsimg.mount(dev, MNT, "ext4")

            try:
                for rep in range(a.reps):
                    meas = ["walk", "walk+files"] + ["files-only/%s" % w for w in a.threads.split(",")]
                    rnd.shuffle(meas)
                    for m in meas:
                        cold()
                        s0 = fsimg.blk_stat(dev)
                        rec = {"exp": "e5b", "layout": layout, "T": T, "N": a.N, "model": model,
                               "delay_ms": d, "measure": m, "rep": rep, "versions": versions,
                               "ts": time.time()}
                        if m == "walk":
                            t0 = time.perf_counter()
                            build_inode_map(MNT, verbose=False)
                            rec["walk_s"] = time.perf_counter() - t0
                            rec["io_walk"] = fsimg.blk_delta(s0, fsimg.blk_stat(dev))
                        elif m == "walk+files":
                            t0 = time.perf_counter()
                            imap = build_inode_map(MNT, verbose=False)
                            rec["walk_s"] = time.perf_counter() - t0
                            s1 = fsimg.blk_stat(dev)
                            rec["io_walk"] = fsimg.blk_delta(s0, s1)
                            ps = [imap.get(str(ino)) for ino, _ in traced]
                            rec["files_s"] = lookups([p for p in ps if p], 1)
                            rec["io_files"] = fsimg.blk_delta(s1, fsimg.blk_stat(dev))
                        else:
                            w = int(m.split("/")[1])
                            rec["threads"] = w
                            rec["files_s"] = lookups(paths, w)
                            rec["io_files"] = fsimg.blk_delta(s0, fsimg.blk_stat(dev))
                        rungs.append_jsonl(out, rec)
                        print("%-9s %-7s d=%-2d %-14s rep=%d walk=%s files=%s reads(walk/files)=%s/%s" % (
                            layout, model, d, m, rep,
                            "%.3f" % rec["walk_s"] if "walk_s" in rec else "-",
                            "%.3f" % rec["files_s"] if "files_s" in rec else "-",
                            rec.get("io_walk", {}).get("read_ios", "-"),
                            rec.get("io_files", {}).get("read_ios", "-")), flush=True)
            finally:
                fsimg.umount(MNT)
                if nbd:
                    nbd.close()
                else:
                    fs.close(delete=False)
        if os.path.exists(img):
            os.remove(img)


if __name__ == "__main__":
    main()
