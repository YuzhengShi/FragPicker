#!/usr/bin/env python3
"""E13 (exploratory): the GIL's request-size threshold as a dose-response curve, with
the device's side of the story.

Same setup as E8 (ext4, N files of 16 extents, cold leaf blocks, dm-delay), but the
FIEMAP request holds n extents for n from 1 to 64: 32 + 56n bytes, so n <= 17 fits the
1,024-byte buffer below which CPython 3.12 and 3.13 release the GIL and n >= 18 does not.
Every n reads the same extent-tree leaf (FIEMAP fills at most n extents). While each pass
runs, a separate process samples the dm device's in-flight read count
(inflight_sampler.py), so we see how many reads the device was actually given at once.
Run inside study/bin/run_in_ns.sh; the interpreter is whatever runs this script.
"""

import argparse
import concurrent.futures as cf
import ctypes
import fcntl
import json
import os
import random
import signal
import subprocess
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
MNT = "/mnt"
FS_IOC_FIEMAP = 0xC020660B
_REQ = {}


def req_type(n):
    if n not in _REQ:
        class Req(ctypes.Structure):
            _fields_ = [("fiemap", Fiemap), ("extents", FiemapExtent * n)]
        _REQ[n] = Req
    return _REQ[n]


def fiemap(path, n):
    req = req_type(n)()
    req.fiemap.fm_start = 0
    req.fiemap.fm_length = ctypes.c_uint64(-1).value
    req.fiemap.fm_extent_count = n
    fd = os.open(path, os.O_RDONLY)
    try:
        fcntl.ioctl(fd, FS_IOC_FIEMAP, req)
    finally:
        os.close(fd)
    return req.fiemap.fm_mapped_extents


def timed_pass(paths, n, workers):
    chunks = [paths[i::workers] for i in range(workers)]
    work = lambda i: [fiemap(p, n) for p in chunks[i]]
    t0 = time.perf_counter()
    if workers == 1:
        work(0)
    else:
        with cf.ThreadPoolExecutor(workers) as ex:
            list(ex.map(work, range(workers)))
    return time.perf_counter() - t0


def inflight_path(dev):
    st = os.stat(dev)
    sysdir = os.path.realpath("/sys/dev/block/%d:%d" % (os.major(st.st_rdev), os.minor(st.st_rdev)))
    return os.path.join(sysdir, "inflight")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--N", type=int, default=200)
    ap.add_argument("--blocks", type=int, default=16)
    ap.add_argument("--delay-ms", type=int, default=5)
    ap.add_argument("--sizes", default="1,4,8,12,16,17,18,19,24,32,64")
    ap.add_argument("--workers", default="1,16")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--out", default="e13_boundary.jsonl")
    a = ap.parse_args()
    out = os.path.join(DATA, a.out)
    versions = rungs.code_versions()
    gil = getattr(sys, "_is_gil_enabled", lambda: True)()
    py = sys.version.split()[0]
    img = os.path.join(IMG, "e13.img")
    fs = fsimg.TestFS(img, 1024, "ext4", MNT)
    data = os.urandom(4096)
    paths = [os.path.join(MNT, "f%04d" % i) for i in range(a.N)]
    for p in paths:
        make_file(p, a.blocks, "ext4", data)
    os.sync()
    ext = sorted(fiemap(p, 64) for p in paths)
    rungs.append_jsonl(out, {"exp": "e13", "kind": "layout", "N": a.N, "extents_median": ext[len(ext) // 2],
                             "extents_min": ext[0], "extents_max": ext[-1], "python": py,
                             "gil_enabled": gil, "versions": versions})
    fs.close(delete=False)
    fs = fsimg.TestFS(img, 1024, "ext4", MNT, fresh=False, delay_ms=a.delay_ms)
    dev = fs.dev
    infl = inflight_path(dev)
    sampler = os.path.join(HERE, "inflight_sampler.py")
    rnd = random.Random(13)
    sizes = [int(x) for x in a.sizes.split(",")]
    workers = [int(x) for x in a.workers.split(",")]
    try:
        for rep in range(a.reps):
            cells = [(n, w) for n in sizes for w in workers]
            rnd.shuffle(cells)
            for n, w in cells:
                fsimg.umount(MNT)
                fsimg.drop_caches()
                fsimg.mount(dev, MNT, "ext4")
                for p in paths:  # inodes in, leaf blocks still cold
                    os.stat(p)
                # the sampler is a separate process run by the system's python3
                sp = subprocess.Popen(["python3", sampler, infl], stdout=subprocess.PIPE, text=True)
                if sp.stdout.readline().strip() != "ready":  # handler installed, sampling
                    raise RuntimeError("in-flight sampler did not start")
                s0 = fsimg.blk_stat(dev)
                wall = timed_pass(paths, n, w)
                io = fsimg.blk_delta(s0, fsimg.blk_stat(dev))
                sp.send_signal(signal.SIGTERM)
                samp = json.loads(sp.communicate(timeout=10)[0].strip())
                rec = {"exp": "e13", "kind": "time", "n_extents": n, "req_bytes": ctypes.sizeof(req_type(n)),
                       "workers": w, "rep": rep, "wall_s": wall, "reads_per_file": io["read_ios"] / a.N,
                       "inflight": samp, "delay_ms": a.delay_ms, "python": py, "gil_enabled": gil,
                       "versions": versions, "ts": time.time()}
                rungs.append_jsonl(out, rec)
                print("py%s gil=%s n=%-2d %4dB W=%-2d rep=%d %.3fs reads/file=%.2f inflight max=%d mean=%.2f >=2:%.0f%%" % (
                    py, gil, n, rec["req_bytes"], w, rep, wall, rec["reads_per_file"], samp["max"],
                    samp["mean_busy"], 100 * samp["share_ge2"]), flush=True)
    finally:
        fs.close()


if __name__ == "__main__":
    main()
