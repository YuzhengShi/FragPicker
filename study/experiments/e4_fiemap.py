#!/usr/bin/env python3
"""E4: what does one per-file extent lookup cost, and how many device reads does it
need? (PLAN.md RQ3, H3a/H3b)

For each file system (ext4, xfs, btrfs, f2fs) and extent class, create N files whose
extent count is driven up by rewriting every other block (punch + rewrite on ext4/xfs,
overwrite on btrfs/f2fs), read the real extent count back with FIEMAP, then time the
fork's own FiemapAnalyzer.get_extents (stat + open + FIEMAP ioctl(s) + close):
  warm   second pass over the files, everything cached
  cold   after umount + drop_caches + mount, files in creation order and in random order
  cold-W W threads (1,2,4,8,16) over the files in creation order, cold
Device reads come from /sys/block/<dev>/stat. Run as root; uses $FPSTUDY_ROOT/e4mnt.
"""

import argparse
import concurrent.futures as cf
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from fpstudy import fsimg, rungs  # noqa: E402

CODE = os.environ.get("FPSTUDY_CODE", "/root/fpstudy/code")
sys.path.insert(0, os.path.join(CODE, "fork", "src", "analysis"))
from parallel_analyzer.fiemap import FiemapAnalyzer  # noqa: E402

DATA = os.environ.get("FPSTUDY_DATA", "/root/fpstudy/data")
IMG = os.environ.get("FPSTUDY_IMG", "/root/fpstudy/img")
MNT = "/root/fpstudy/e4mnt"
BLK = 4096
PUNCH = 0x02 | 0x01  # FALLOC_FL_PUNCH_HOLE | FALLOC_FL_KEEP_SIZE


def fallocate(fd, mode, off, ln):
    import ctypes, ctypes.util
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    r = libc.fallocate(fd, mode, ctypes.c_long(off), ctypes.c_long(ln))
    if r != 0:
        raise OSError(ctypes.get_errno(), "fallocate")


def make_file(path, blocks, fstype, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.pwrite(fd, data * blocks, 0)
        os.fsync(fd)
        if blocks > 1:
            for b in range(1, blocks, 2):
                if fstype in ("ext4", "xfs"):
                    fallocate(fd, PUNCH, b * BLK, BLK)
                os.pwrite(fd, data, b * BLK)
                os.fsync(fd)
    finally:
        os.close(fd)


def time_pass(fa, paths, threads=1):
    if threads == 1:
        t0 = time.perf_counter()
        for p in paths:
            fa.get_extents(p)
        return time.perf_counter() - t0
    fas = [FiemapAnalyzer() for _ in range(threads)]
    chunks = [paths[i::threads] for i in range(threads)]

    def work(i):
        for p in chunks[i]:
            fas[i].get_extents(p)

    t0 = time.perf_counter()
    with cf.ThreadPoolExecutor(threads) as ex:
        list(ex.map(work, range(threads)))
    return time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fs", default="ext4,xfs,btrfs,f2fs")
    ap.add_argument("--classes", default="1:1000,4:1000,8:1000,32:500,128:300,512:100")
    ap.add_argument("--threads", default="1,2,4,8,16")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--out", default="e4_fiemap.jsonl")
    a = ap.parse_args()
    out = os.path.join(DATA, a.out)
    versions = rungs.code_versions()
    data = os.urandom(BLK)
    rnd = random.Random(9)
    classes = [tuple(int(v) for v in c.split(":")) for c in a.classes.split(",")]
    for fstype in a.fs.split(","):
        fs = fsimg.TestFS(os.path.join(IMG, "e4_%s.img" % fstype), 4096, fstype, MNT)
        try:
            groups = {}
            for blocks, n in classes:
                d = os.path.join(MNT, "b%d" % blocks)
                os.makedirs(d)
                paths = [os.path.join(d, "f%05d" % i) for i in range(n)]
                t0 = time.time()
                for p in paths:
                    make_file(p, blocks, fstype, data)
                os.sync()
                fa = FiemapAnalyzer()
                ext = sorted(len(fa.get_extents(p) or []) for p in paths)
                groups[blocks] = paths
                rec = {"exp": "e4", "kind": "layout", "fs": fstype, "blocks": blocks, "n": n,
                       "extents_median": ext[len(ext) // 2], "extents_min": ext[0],
                       "extents_max": ext[-1], "build_s": time.time() - t0, "versions": versions}
                rungs.append_jsonl(out, rec)
                print(rec, flush=True)
            for rep in range(a.reps):
                for blocks, paths in groups.items():
                    n = len(paths)
                    fa = FiemapAnalyzer()
                    # warm: one priming pass, then the timed pass
                    time_pass(fa, paths)
                    s0 = fs.stat()
                    tw = time_pass(fa, paths)
                    io_w = fsimg.blk_delta(s0, fs.stat())
                    res = [("warm", 1, "creation", tw, io_w)]
                    for order in ("creation", "random"):
                        ps = paths[:] if order == "creation" else rnd.sample(paths, n)
                        fs.remount_cold()
                        s0 = fs.stat()
                        tc = time_pass(FiemapAnalyzer(), ps)
                        res.append(("cold", 1, order, tc, fsimg.blk_delta(s0, fs.stat())))
                    for w in [int(x) for x in a.threads.split(",")]:
                        if w == 1:
                            continue
                        fs.remount_cold()
                        s0 = fs.stat()
                        tc = time_pass(None, paths, threads=w)
                        res.append(("cold", w, "creation", tc, fsimg.blk_delta(s0, fs.stat())))
                    for cache, w, order, t, io in res:
                        rec = {"exp": "e4", "kind": "time", "fs": fstype, "blocks": blocks, "n": n,
                               "cache": cache, "threads": w, "order": order, "rep": rep,
                               "wall_s": t, "per_file_us": t / n * 1e6,
                               "reads_per_file": io["read_ios"] / n, "io": io,
                               "versions": versions, "ts": time.time()}
                        rungs.append_jsonl(out, rec)
                        print("%-5s b=%-4d %-4s W=%-2d %-8s rep=%d %8.1f us/file  reads/file=%.3f" % (
                            fstype, blocks, cache, w, order, rep, rec["per_file_us"], rec["reads_per_file"]), flush=True)
        finally:
            fs.close()


if __name__ == "__main__":
    main()
