#!/usr/bin/env python3
"""E8: does the fork's thread pool overlap FIEMAP calls that wait on the device?

CPython 3.12.x/3.13.x call ioctl() WITHOUT releasing the GIL when fcntl.ioctl is given
a writable buffer larger than 1024 bytes (Modules/fcntlmodule.c, fcntl_ioctl_impl);
3.14.0 releases it. The fork's FiemapRequest holds 32 extents: 32 + 32*56 = 1824 bytes.

Setup: ext4 on dm-delay (read delay d), N files with K extents each (K > 4, so FIEMAP
must read an extent-tree leaf block from the device). Before every timed pass: remount
cold, then stat every file once (inodes come in through inode-table readahead), so the
only device read left per file is the leaf block that FIEMAP itself reads.
Timed pass, W threads (or processes) over the files:
  fork     the fork's FiemapAnalyzer.get_extents (1824-byte request)
  big      open + one FIEMAP ioctl with a 1824-byte request + close
  small    the same with a 928-byte request (16 extents): GIL released on 3.12
  big_mp   'big' in W processes instead of threads
Run inside study/bin/run_in_ns.sh (uses /mnt).
"""

import argparse
import ctypes
import fcntl
import multiprocessing as mp
import os
import random
import sys
import time
import concurrent.futures as cf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from fpstudy import fsimg, rungs  # noqa: E402

CODE = os.environ.get("FPSTUDY_CODE", "/root/fpstudy/code")
sys.path.insert(0, os.path.join(CODE, "fork", "src", "analysis"))
from parallel_analyzer.fiemap import FiemapAnalyzer, Fiemap, FiemapExtent  # noqa: E402

sys.path.insert(0, HERE)
from e4_fiemap import make_file  # noqa: E402

DATA = os.environ.get("FPSTUDY_DATA", "/root/fpstudy/data")
IMG = os.environ.get("FPSTUDY_IMG", "/root/fpstudy/img")
MNT = "/mnt"
FS_IOC_FIEMAP = 0xC020660B


def request_type(n_ext):
    class Req(ctypes.Structure):
        _fields_ = [("fiemap", Fiemap), ("extents", FiemapExtent * n_ext)]
    return Req


REQ = {"big": request_type(32), "small": request_type(16)}


def fiemap_once(path, kind):
    Req = REQ[kind]
    req = Req()
    req.fiemap.fm_start = 0
    req.fiemap.fm_length = ctypes.c_uint64(-1).value
    req.fiemap.fm_extent_count = 32 if kind == "big" else 16
    fd = os.open(path, os.O_RDONLY)
    try:
        fcntl.ioctl(fd, FS_IOC_FIEMAP, req)
    finally:
        os.close(fd)
    return req.fiemap.fm_mapped_extents


def _mp_work(args):
    paths, kind = args
    for p in paths:
        fiemap_once(p, kind)
    return len(paths)


def timed_pass(paths, variant, workers, pool=None):
    chunks = [paths[i::workers] for i in range(workers)]
    if variant == "big_mp":
        t0 = time.perf_counter()
        pool.map(_mp_work, [(c, "big") for c in chunks])
        return time.perf_counter() - t0
    if variant == "fork":
        fas = [FiemapAnalyzer() for _ in range(workers)]
        work = lambda i: [fas[i].get_extents(p) for p in chunks[i]]
    else:
        work = lambda i: [fiemap_once(p, variant) for p in chunks[i]]
    t0 = time.perf_counter()
    if workers == 1:
        work(0)
    else:
        with cf.ThreadPoolExecutor(workers) as ex:
            list(ex.map(work, range(workers)))
    return time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--N", type=int, default=200)
    ap.add_argument("--blocks", type=int, default=16, help="blocks (= extents) per file")
    ap.add_argument("--delays", default="0,5")
    ap.add_argument("--workers", default="1,4,16")
    ap.add_argument("--variants", default="fork,big,small,big_mp")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--out", default="e8_gil.jsonl")
    a = ap.parse_args()
    out = os.path.join(DATA, a.out)
    versions = rungs.code_versions()
    rnd = random.Random(8)
    img = os.path.join(IMG, "e8.img")
    fs = fsimg.TestFS(img, 1024, "ext4", MNT)
    d0 = os.path.join(MNT, "f")
    os.makedirs(d0)
    data = os.urandom(4096)
    paths = [os.path.join(d0, "x%04d" % i) for i in range(a.N)]
    for p in paths:
        make_file(p, a.blocks, "ext4", data)
    os.sync()
    ext = sorted(fiemap_once(p, "big") for p in paths)
    fs.close(delete=False)
    rungs.append_jsonl(out, {"exp": "e8", "kind": "layout", "N": a.N, "blocks": a.blocks,
                             "extents_median": ext[len(ext) // 2], "python": sys.version.split()[0],
                             "req_bytes": {k: ctypes.sizeof(v) for k, v in REQ.items()},
                             "versions": versions})
    pool = mp.Pool(max(int(w) for w in a.workers.split(",")))
    try:
        for d in [int(x) for x in a.delays.split(",")]:
            fs = fsimg.TestFS(img, 1024, "ext4", MNT, fresh=False, delay_ms=d if d else None)
            try:
                for rep in range(a.reps):
                    combos = [(v, int(w)) for v in a.variants.split(",") for w in a.workers.split(",")]
                    rnd.shuffle(combos)
                    for v, w in combos:
                        fs.remount_cold()
                        for p in paths:  # inodes in, leaf blocks still cold
                            os.stat(p)
                        s0 = fs.stat()
                        wall = timed_pass(paths, v, w, pool)
                        io = fsimg.blk_delta(s0, fs.stat())
                        rec = {"exp": "e8", "kind": "time", "delay_ms": d, "variant": v, "workers": w,
                               "rep": rep, "wall_s": wall, "per_file_ms": wall / a.N * 1000,
                               "reads_per_file": io["read_ios"] / a.N, "io": io,
                               "python": sys.version.split()[0], "versions": versions, "ts": time.time()}
                        rungs.append_jsonl(out, rec)
                        print("d=%-2d %-7s W=%-2d rep=%d %.3fs  %.2f ms/file  reads/file=%.2f" % (
                            d, v, w, rep, wall, rec["per_file_ms"], rec["reads_per_file"]), flush=True)
            finally:
                fs.close(delete=False)
    finally:
        pool.terminate()
        if os.path.exists(img):
            os.remove(img)


if __name__ == "__main__":
    main()
