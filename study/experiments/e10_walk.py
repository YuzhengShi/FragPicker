#!/usr/bin/env python3
"""E10 (exploratory, designed after E5b had been seen): can threads speed up the one part
of a cold run that does wait for the device, the tree walk that builds the inode map?

Tree as in E5's scattered case: 100,000 files of 4 KiB in 1,000 directories of 100 files
directly under the mount point. Walkers, cold cache before every measurement:
  find        the fork's build_inode_map (one `find -type f -printf '%i %p\\n'`)
  scandir/W   os.scandir over the top-level directories, split over W threads (W = 1 is
              a plain loop); inode numbers come from d_ino, as in find, so no stat. Both
              opendir and readdir release the GIL.
Device models as in E5/E8: plain loop, dm-delay, nbdkit with one thread (one request at
a time) and with 32 threads (many in flight), all with the same configured delay.
Every walker's inode map is compared with find's.
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
from parallel_analyzer.inode_mapper import build_inode_map  # noqa: E402

sys.path.insert(0, HERE)
from e5_latency import NbdDevice  # noqa: E402

DATA = os.environ.get("FPSTUDY_DATA", "/root/fpstudy/data")
IMG = os.environ.get("FPSTUDY_IMG", "/root/fpstudy/img")
MNT = "/mnt"


def scan_tree(top):
    out = []
    stack = [top]
    while stack:
        cur = stack.pop()
        with os.scandir(cur) as it:
            for e in it:
                if e.is_dir(follow_symlinks=False):
                    stack.append(e.path)
                elif e.is_file(follow_symlinks=False):
                    out.append((str(e.inode()), e.path))
    return out


def walk_scandir(mnt, threads):
    res, dirs = {}, []
    with os.scandir(mnt) as it:
        for e in it:
            if e.is_dir(follow_symlinks=False):
                dirs.append(e.path)
            elif e.is_file(follow_symlinks=False):
                res[str(e.inode())] = e.path
    if threads == 1:
        for d in dirs:
            res.update(scan_tree(d))
    else:
        with cf.ThreadPoolExecutor(threads) as ex:
            for part in ex.map(scan_tree, dirs):
                res.update(part)
    return res


def walk(walker):
    if walker == "find":
        return build_inode_map(MNT, verbose=False)
    return walk_scandir(MNT, int(walker.split("/")[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--T", type=int, default=100000)
    ap.add_argument("--per-dir", type=int, default=100)
    ap.add_argument("--delay-ms", type=int, default=5)
    ap.add_argument("--models", default="plain,dmdelay,qd1,nbdpar")
    ap.add_argument("--walkers", default="find,scandir/1,scandir/4,scandir/16")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--out", default="e10_walk.jsonl")
    a = ap.parse_args()
    out = os.path.join(DATA, a.out)
    versions = rungs.code_versions()
    rnd = random.Random(41)
    img = os.path.join(IMG, "e10_T%d.img" % a.T)
    size_mb = max(1024, int(a.T * 12 / 1024 * 1.5) + 512)
    fs = fsimg.TestFS(img, size_mb, "ext4", MNT)
    corpus.make_tree(MNT, a.T, per_dir=a.per_dir, size=4096, seed=4)
    ref = build_inode_map(MNT, verbose=False)
    fs.close(delete=False)
    walkers = a.walkers.split(",")
    try:
        for model in a.models.split(","):
            nbd = None
            if model in ("qd1", "nbdpar"):
                nbd = NbdDevice(img, a.delay_ms, threads=1 if model == "qd1" else 32)
                dev = nbd.nbd
            else:
                fs = fsimg.TestFS(img, size_mb, "ext4", MNT, fresh=False,
                                  delay_ms=a.delay_ms if model == "dmdelay" else None)
                fsimg.umount(MNT)
                dev = fs.dev
            d = 0 if model == "plain" else a.delay_ms
            try:
                for rep in range(a.reps):
                    order = walkers[:]
                    rnd.shuffle(order)
                    for wk in order:
                        fsimg.umount(MNT)
                        fsimg.drop_caches()
                        fsimg.mount(dev, MNT, "ext4")
                        s0 = fsimg.blk_stat(dev)
                        t0 = time.perf_counter()
                        m = walk(wk)
                        dt = time.perf_counter() - t0
                        io = fsimg.blk_delta(s0, fsimg.blk_stat(dev))
                        rec = {"exp": "e10", "T": a.T, "per_dir": a.per_dir, "model": model,
                               "delay_ms": d, "walker": wk,
                               "threads": 1 if wk == "find" else int(wk.split("/")[1]),
                               "rep": rep, "wall_s": dt, "io": io, "n_files": len(m),
                               "equal_to_find": m == ref, "versions": versions,
                               "ts": time.time()}
                        rungs.append_jsonl(out, rec)
                        print("%-7s %-11s rep=%d %.3fs reads=%d KiB=%d files=%d equal=%s" % (
                            model, wk, rep, dt, io["read_ios"], io["read_sectors"] // 2,
                            len(m), m == ref), flush=True)
            finally:
                fsimg.umount(MNT)
                if nbd:
                    nbd.close()
                else:
                    fs.close(delete=False)
    finally:
        try:
            os.remove(img)
        except OSError:
            pass


if __name__ == "__main__":
    main()
