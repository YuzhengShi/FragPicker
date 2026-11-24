#!/usr/bin/env python3
"""E8: when can threads overlap FIEMAP calls that wait on the device?

CPython 3.12.x and 3.13.x call ioctl() WITHOUT releasing the GIL when fcntl.ioctl gets a
writable buffer larger than 1024 bytes (Modules/fcntlmodule.c, fcntl_ioctl_impl; read at
tags v3.12.3, v3.12.12, v3.13.0, v3.13.9); v3.14.0 releases it (source only, not run here).
The fork's FiemapRequest holds 32 extents: 32 + 32*56 = 1824 bytes. The largest request
that still takes the GIL-releasing path holds 17 extents: 32 + 17*56 = 984 bytes.

Setup: ext4, N files with K extents each (K > 4, so FIEMAP must read an extent-tree leaf
block from the device). Before every timed pass: cold cache, then stat every file once
(inodes come in through inode-table readahead and stat releases the GIL), so the only
device read left per file is the leaf block that FIEMAP itself reads.

Devices, all with delay d per request:
  dmdelay   dm-delay (its timers run in jiffies; see E7b for the effective delay)
  nbd_qd1   nbdkit delay filter, 1 thread: one request at a time, precise sleep
  nbd_par   nbdkit delay filter, 32 threads: many requests in flight, precise sleep
  plain     the loop device, no delay (d = 0)
Variants (W workers):
  fork      the fork's FiemapAnalyzer.get_extents on W threads (1824-byte request)
  big       open + one FIEMAP ioctl with a 1824-byte request + close, W threads
  small     the same with a 984-byte request (17 extents), W threads
  big_mp    'big' in W processes
  fork_mp   the fork's own MultiprocessParallelProcessor.process_files (W processes;
            includes its inode-map walk), which --parallel never uses
Run inside study/bin/run_in_ns.sh (uses /mnt).
"""

import argparse
import concurrent.futures as cf
import ctypes
import fcntl
import multiprocessing as mp
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from fpstudy import fsimg, rungs  # noqa: E402

CODE = os.environ.get("FPSTUDY_CODE", "/root/fpstudy/code")
sys.path.insert(0, os.path.join(CODE, "fork", "src", "analysis"))
from parallel_analyzer.fiemap import FiemapAnalyzer, Fiemap, FiemapExtent  # noqa: E402
from parallel_analyzer.multiprocess_processor import MultiprocessParallelProcessor  # noqa: E402

sys.path.insert(0, HERE)
from e4_fiemap import make_file  # noqa: E402
from e5_latency import NbdDevice  # noqa: E402

DATA = os.environ.get("FPSTUDY_DATA", "/root/fpstudy/data")
IMG = os.environ.get("FPSTUDY_IMG", "/root/fpstudy/img")
MNT = "/mnt"
FS_IOC_FIEMAP = 0xC020660B
N_EXT = {"big": 32, "small": 17}


def request_type(n_ext):
    class Req(ctypes.Structure):
        _fields_ = [("fiemap", Fiemap), ("extents", FiemapExtent * n_ext)]
    return Req


REQ = {k: request_type(n) for k, n in N_EXT.items()}


def fiemap_once(path, kind, want=False):
    req = REQ[kind]()
    req.fiemap.fm_start = 0
    req.fiemap.fm_length = ctypes.c_uint64(-1).value
    req.fiemap.fm_extent_count = N_EXT[kind]
    fd = os.open(path, os.O_RDONLY)
    try:
        fcntl.ioctl(fd, FS_IOC_FIEMAP, req)
    finally:
        os.close(fd)
    n = req.fiemap.fm_mapped_extents
    if want:
        return [(e.fe_logical, e.fe_physical, e.fe_length, e.fe_flags) for e in req.extents[:n]]
    return n


def _mp_work(args):
    paths, kind = args
    for p in paths:
        fiemap_once(p, kind)
    return len(paths)


def timed_pass(paths, inodes, variant, workers, pool):
    chunks = [paths[i::workers] for i in range(workers)]
    if variant == "big_mp":
        t0 = time.perf_counter()
        pool.map(_mp_work, [(c, "big") for c in chunks])
        return time.perf_counter() - t0
    if variant == "fork_mp":
        proc = MultiprocessParallelProcessor(num_workers=workers, mount_point=MNT)
        t0 = time.perf_counter()
        proc.process_files([(str(i), 1) for i in inodes], enable_sorting=False)
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
    ap.add_argument("--blocks", type=int, default=16, help="blocks (= extents) per file, <= 17")
    ap.add_argument("--delay-ms", type=int, default=5)
    ap.add_argument("--devices", default="plain,dmdelay,nbd_qd1,nbd_par")
    ap.add_argument("--workers", default="1,4,16")
    ap.add_argument("--variants", default="fork,big,small,big_mp,fork_mp")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--out", default="e8_gil.jsonl")
    a = ap.parse_args()
    assert a.blocks <= 17
    out = os.path.join(DATA, a.out)
    versions = rungs.code_versions()
    rnd = random.Random(8)
    img = os.path.join(IMG, "e8.img")
    fs = fsimg.TestFS(img, 1024, "ext4", MNT)
    d0 = os.path.join(MNT, "f")
    os.makedirs(d0)
    data = os.urandom(4096)
    rel = ["f/x%04d" % i for i in range(a.N)]
    for r_ in rel:
        make_file(os.path.join(MNT, r_), a.blocks, "ext4", data)
    os.sync()
    paths = [os.path.join(MNT, r_) for r_ in rel]
    inodes = [os.stat(p).st_ino for p in paths]
    # both request sizes must return the same extents for every file
    same = all(fiemap_once(p, "big", True) == fiemap_once(p, "small", True) for p in paths)
    ext = sorted(fiemap_once(p, "big") for p in paths)
    fs.close(delete=False)
    rungs.append_jsonl(out, {"exp": "e8", "kind": "layout", "N": a.N, "blocks": a.blocks,
                             "extents_median": ext[len(ext) // 2], "extents_min": ext[0],
                             "extents_max": ext[-1], "big_small_identical": same,
                             "python": sys.version.split()[0],
                             "req_bytes": {k: ctypes.sizeof(v) for k, v in REQ.items()},
                             "versions": versions})
    print("layout: extents %d..%d, identical=%s, request bytes %s" % (
        ext[0], ext[-1], same, {k: ctypes.sizeof(v) for k, v in REQ.items()}), flush=True)
    assert same
    pool = mp.Pool(max(int(w) for w in a.workers.split(",")))
    try:
        for devname in a.devices.split(","):
            d = 0 if devname == "plain" else a.delay_ms
            nbd = fs = None
            if devname.startswith("nbd"):
                nbd = NbdDevice(img, d, threads=1 if devname == "nbd_qd1" else 32)
                dev = nbd.nbd
            else:
                fs = fsimg.TestFS(img, 1024, "ext4", MNT, fresh=False,
                                  delay_ms=d if devname == "dmdelay" else None)
                fsimg.umount(MNT)
                dev = fs.dev
            try:
                for rep in range(a.reps):
                    combos = [(v, int(w)) for v in a.variants.split(",") for w in a.workers.split(",")]
                    rnd.shuffle(combos)
                    for v, w in combos:
                        fsimg.umount(MNT)
                        fsimg.drop_caches()
                        fsimg.mount(dev, MNT, "ext4")
                        for p in paths:  # inodes in, leaf blocks still cold
                            os.stat(p)
                        s0 = fsimg.blk_stat(dev)
                        wall = timed_pass(paths, inodes, v, w, pool)
                        io = fsimg.blk_delta(s0, fsimg.blk_stat(dev))
                        rec = {"exp": "e8", "kind": "time", "device": devname, "delay_ms": d,
                               "variant": v, "workers": w, "rep": rep, "wall_s": wall,
                               "per_file_ms": wall / a.N * 1000,
                               "reads_per_file": io["read_ios"] / a.N, "io": io,
                               "python": sys.version.split()[0], "versions": versions,
                               "ts": time.time()}
                        rungs.append_jsonl(out, rec)
                        print("%-8s d=%-2d %-7s W=%-2d rep=%d %.3fs  %.2f ms/file  reads/file=%.2f" % (
                            devname, d, v, w, rep, wall, rec["per_file_ms"], rec["reads_per_file"]),
                            flush=True)
            finally:
                fsimg.umount(MNT)
                if nbd:
                    nbd.close()
                if fs:
                    fs.close(delete=False)
    finally:
        pool.terminate()
        if os.path.exists(img):
            os.remove(img)


if __name__ == "__main__":
    main()
