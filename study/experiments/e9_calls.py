#!/usr/bin/env python3
"""E9 (exploratory, designed after E4 had been seen): where the time and the device reads
of one extent lookup go.

The fork's lookup does stat, open, FIEMAP and close for each file. Here each call runs as
its own pass over all files (stat all, open all, FIEMAP all on the open descriptors,
close all), with the device's read counters taken around every pass, warm and cold, on
one thread and on 16. Files as in E4 (punch-and-rewrite), 1 and 32 blocks, on ext4, XFS,
Btrfs and F2FS. FIEMAP uses the fork's request size (32 extents, 1,824 bytes), with which
CPython 3.12 holds the GIL during the ioctl (E8), and the fork's range (the whole
address space); a further pass asks only up to each file's size (fiemap_eof).
Run inside study/bin/run_in_ns.sh.
"""

import argparse
import concurrent.futures as cf
import ctypes
import fcntl
import os
import random
import resource
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from fpstudy import fsimg, rungs  # noqa: E402

CODE = os.environ.get("FPSTUDY_CODE", "/root/fpstudy/code")
sys.path.insert(0, os.path.join(CODE, "fork", "src", "analysis"))
from parallel_analyzer.fiemap import Fiemap, FiemapExtent  # noqa: E402

sys.path.insert(0, HERE)
from e4_fiemap import make_file  # noqa: E402

DATA = os.environ.get("FPSTUDY_DATA", "/root/fpstudy/data")
IMG = os.environ.get("FPSTUDY_IMG", "/root/fpstudy/img")
MNT = "/root/fpstudy/e9mnt"
BLK = 4096
FS_IOC_FIEMAP = 0xC020660B
N_EXT = 32
CALLS = ("stat", "open", "fiemap", "close")


class Req(ctypes.Structure):
    _fields_ = [("fiemap", Fiemap), ("extents", FiemapExtent * N_EXT)]


def fiemap_fd(fd, length=None):
    """FIEMAP over [0, length); length None = the whole address space, as the fork asks."""
    req = Req()
    req.fiemap.fm_start = 0
    req.fiemap.fm_length = ctypes.c_uint64(-1).value if length is None else length
    req.fiemap.fm_extent_count = N_EXT
    fcntl.ioctl(fd, FS_IOC_FIEMAP, req)
    return req.fiemap.fm_mapped_extents


def fiemap_to_eof(fd_size):
    return fiemap_fd(fd_size[0], fd_size[1])


def open_ro(p):
    return os.open(p, os.O_RDONLY)


def run_pass(items, fn, threads):
    """Apply fn to every item, split over `threads` threads; (seconds, results in order)."""
    if threads == 1:
        t0 = time.perf_counter()
        res = [fn(x) for x in items]
        return time.perf_counter() - t0, res
    chunks = [items[i::threads] for i in range(threads)]
    out = [None] * threads

    def work(i):
        out[i] = [fn(x) for x in chunks[i]]

    t0 = time.perf_counter()
    with cf.ThreadPoolExecutor(threads) as ex:
        list(ex.map(work, range(threads)))
    dt = time.perf_counter() - t0
    res = [None] * len(items)
    for i in range(threads):
        res[i::threads] = out[i]
    return dt, res


def sequence(fs, paths, threads):
    """stat, open, FIEMAP, close as passes; per pass: seconds and read delta. A last
    FIEMAP pass asks only up to the file's size (fiemap_eof), to see whether a file
    system's cost depends on the requested range rather than on the file."""
    fns = {"stat": os.stat, "open": open_ro, "fiemap": fiemap_fd,
           "fiemap_eof": fiemap_to_eof, "close": os.close}
    rec = {}
    fds = sizes = None
    n_ext = {}
    for c in CALLS[:3] + ("fiemap_eof", "close"):
        if c == "fiemap_eof":
            sizes = [os.fstat(fd).st_size for fd in fds]  # untimed
            items = list(zip(fds, sizes))
        elif c in ("fiemap", "close"):
            items = fds
        else:
            items = paths
        s0 = fs.stat()
        dt, res = run_pass(items, fns[c], threads)
        io = fsimg.blk_delta(s0, fs.stat())
        if c == "open":
            fds = res
        if c in ("fiemap", "fiemap_eof"):
            n_ext[c] = res
        rec[c] = {"s": dt, "us_per_file": 1e6 * dt / len(paths), "read_ios": io["read_ios"],
                  "read_sectors": io["read_sectors"]}
    rec["eof_same_extents"] = n_ext["fiemap"] == n_ext["fiemap_eof"]
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fs", default="ext4,xfs,btrfs,f2fs")
    ap.add_argument("--classes", default="1:500,32:500")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--out", default="e9_calls.jsonl")
    a = ap.parse_args()
    resource.setrlimit(resource.RLIMIT_NOFILE, (8192, 8192))
    out = os.path.join(DATA, a.out)
    versions = rungs.code_versions()
    data = os.urandom(BLK)
    rnd = random.Random(19)
    classes = [tuple(int(v) for v in c.split(":")) for c in a.classes.split(",")]
    for fstype in a.fs.split(","):
        fs = fsimg.TestFS(os.path.join(IMG, "e9_%s.img" % fstype), 4096, fstype, MNT)
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
                fds = [os.open(p, os.O_RDONLY) for p in paths]
                ext = sorted(fiemap_fd(fd) for fd in fds)
                for fd in fds:
                    os.close(fd)
                groups[blocks] = paths
                rec = {"exp": "e9", "kind": "layout", "fs": fstype, "blocks": blocks, "n": n,
                       "extents_median": ext[len(ext) // 2], "extents_min": ext[0],
                       "extents_max": ext[-1], "build_s": time.time() - t0, "versions": versions}
                rungs.append_jsonl(out, rec)
                print(rec, flush=True)
            for rep in range(a.reps):
                cells = [(b, cache, w) for b in groups for cache in ("cold", "warm") for w in (1, 16)]
                rnd.shuffle(cells)
                for blocks, cache, w in cells:
                    paths = groups[blocks]
                    fs.remount_cold()
                    if cache == "warm":
                        sequence(fs, paths, 1)  # priming pass, not recorded
                    res = sequence(fs, paths, w)
                    rec = {"exp": "e9", "kind": "time", "fs": fstype, "blocks": blocks,
                           "n": len(paths), "cache": cache, "threads": w, "rep": rep,
                           "calls": res, "versions": versions, "ts": time.time()}
                    rungs.append_jsonl(out, rec)
                    print("%-5s b=%-3d %-4s W=%-2d rep=%d  " % (fstype, blocks, cache, w, rep) +
                          "  ".join("%s %.1fus/%dr" % (c, res[c]["us_per_file"], res[c]["read_ios"])
                                    for c in CALLS + ("fiemap_eof",)) +
                          "  same=%s" % res["eof_same_extents"], flush=True)
        finally:
            fs.close()


if __name__ == "__main__":
    main()
