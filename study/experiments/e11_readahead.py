#!/usr/bin/env python3
"""E11 (exploratory, designed after E5 had been seen): how much do the cold-cache results
depend on ext4's inode-table readahead (mount option inode_readahead_blks, default 32)?

Layouts as in E5/E5b: 'together' (N files of 100 KiB created together) and 'scattered'
(N files sampled from a tree of 100*N files of 4 KiB). Under dm-delay, cold cache before
every measurement:
  walk          the fork's build_inode_map (find over the tree)
  files-only/W  the per-file lookups with the paths known (os.path.isdir + the fork's
                FiemapAnalyzer.get_extents), on W threads
The value in effect is read back from /sys/fs/ext4/<device>/inode_readahead_blks.
Run inside study/bin/run_in_ns.sh (uses /mnt).
"""

import argparse
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
from e5b_decompose import lookups  # noqa: E402

DATA = os.environ.get("FPSTUDY_DATA", "/root/fpstudy/data")
IMG = os.environ.get("FPSTUDY_IMG", "/root/fpstudy/img")
MNT = "/mnt"


def ra_in_effect(dev):
    # /dev/mapper nodes made by `dmsetup mknodes` are not symlinks, so go by device number
    st = os.stat(dev)
    name = os.path.basename(os.path.realpath("/sys/dev/block/%d:%d" % (
        os.major(st.st_rdev), os.minor(st.st_rdev))))
    try:
        with open("/sys/fs/ext4/%s/inode_readahead_blks" % name) as f:
            return int(f.read().strip())
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--N", type=int, default=1000)
    ap.add_argument("--delay-ms", type=int, default=5)
    ap.add_argument("--values", default="0,1,4,32,256")
    ap.add_argument("--threads", default="1,16")
    ap.add_argument("--layouts", default="together,scattered")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--out", default="e11_readahead.jsonl")
    a = ap.parse_args()
    out = os.path.join(DATA, a.out)
    versions = rungs.code_versions()
    rnd = random.Random(53)
    values = [int(v) for v in a.values.split(",")]
    for layout in a.layouts.split(","):
        T = 100 * a.N if layout == "scattered" else a.N
        size_kb = 4 if layout == "scattered" else 100
        img = os.path.join(IMG, "e11_%s.img" % layout)
        size_mb = max(1024, int(T * (size_kb + 8) / 1024 * 1.5) + 512)
        fs = fsimg.TestFS(img, size_mb, "ext4", MNT)
        files = corpus.make_tree(MNT, T, per_dir=100, size=size_kb * 1024, seed=4)
        traced = rnd.sample(files, a.N) if layout == "scattered" else files
        paths = [p for _, p in traced]
        fs.close(delete=False)
        fs = fsimg.TestFS(img, size_mb, "ext4", MNT, fresh=False, delay_ms=a.delay_ms)
        fsimg.umount(MNT)
        dev = fs.dev
        try:
            for rep in range(a.reps):
                cells = [(v, m) for v in values
                         for m in ["walk"] + ["files-only/%s" % w for w in a.threads.split(",")]]
                rnd.shuffle(cells)
                for v, m in cells:
                    fsimg.umount(MNT)
                    fsimg.drop_caches()
                    fsimg.mount(dev, MNT, "ext4", "inode_readahead_blks=%d" % v)
                    eff = ra_in_effect(dev)
                    s0 = fsimg.blk_stat(dev)
                    rec = {"exp": "e11", "layout": layout, "T": T, "N": a.N,
                           "delay_ms": a.delay_ms, "inode_readahead_blks": v,
                           "in_effect": eff, "measure": m, "rep": rep,
                           "versions": versions, "ts": time.time()}
                    t0 = time.perf_counter()
                    if m == "walk":
                        build_inode_map(MNT, verbose=False)
                        rec["threads"] = 1
                    else:
                        rec["threads"] = int(m.split("/")[1])
                        lookups(paths, rec["threads"])
                    rec["wall_s"] = time.perf_counter() - t0
                    rec["io"] = fsimg.blk_delta(s0, fsimg.blk_stat(dev))
                    rungs.append_jsonl(out, rec)
                    print("%-9s ra=%-3d (%s) %-14s rep=%d %.3fs reads=%d KiB=%d" % (
                        layout, v, eff, m, rep, rec["wall_s"], rec["io"]["read_ios"],
                        rec["io"]["read_sectors"] // 2), flush=True)
        finally:
            fs.close()


if __name__ == "__main__":
    main()
