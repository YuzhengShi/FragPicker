#!/usr/bin/env python3
"""E12 (E6's device characterisation): latency and concurrency of 4 KiB random reads
through the same path the experiments use, a loop device with direct I/O over an image
file on the host's disk. One thread is queue depth 1; 16 threads keep 16 reads in flight
(os.preadv releases the GIL). The region read is written first, so that no read hits a
hole, and read twice, to show any cache below the guest.
Run as root (losetup).
"""

import argparse
import concurrent.futures as cf
import mmap
import os
import random
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from fpstudy import fsimg, rungs  # noqa: E402

DATA = os.environ.get("FPSTUDY_DATA", "/root/fpstudy/data")
IMG = os.environ.get("FPSTUDY_IMG", "/root/fpstudy/img")
BLK = 4096


def reader(dev, offsets):
    fd = os.open(dev, os.O_RDONLY | os.O_DIRECT)
    buf = mmap.mmap(-1, BLK)  # page-aligned, as O_DIRECT needs
    lat = []
    try:
        for off in offsets:
            t0 = time.perf_counter()
            os.preadv(fd, [buf], off)
            lat.append(time.perf_counter() - t0)
    finally:
        os.close(fd)
    return lat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size-mb", type=int, default=2048)
    ap.add_argument("--reads", type=int, default=4000, help="reads per pass and thread count")
    ap.add_argument("--threads", default="1,16")
    ap.add_argument("--out", default="e12_device.jsonl")
    a = ap.parse_args()
    out = os.path.join(DATA, a.out)
    img = os.path.join(IMG, "e12.img")
    fsimg.sh(["dd", "if=/dev/urandom", "of=" + img, "bs=1M", "count=%d" % a.size_mb,
              "oflag=direct", "status=none"])
    loop = fsimg.losetup(img, True)
    rnd = random.Random(12)
    nblk = a.size_mb * 1024 * 1024 // BLK
    try:
        for pas in ("first", "second"):
            for w in [int(x) for x in a.threads.split(",")]:
                offs = [rnd.randrange(nblk) * BLK for _ in range(a.reads)]
                chunks = [offs[i::w] for i in range(w)]
                t0 = time.perf_counter()
                with cf.ThreadPoolExecutor(w) as ex:
                    lats = [x for part in ex.map(lambda c: reader(loop, c), chunks) for x in part]
                wall = time.perf_counter() - t0
                lats.sort()
                rec = {"exp": "e12", "pass": pas, "threads": w, "reads": len(lats),
                       "iops": len(lats) / wall, "lat_mean_ms": 1000 * statistics.mean(lats),
                       "lat_p50_ms": 1000 * lats[len(lats) // 2],
                       "lat_p99_ms": 1000 * lats[int(len(lats) * 0.99)],
                       "size_mb": a.size_mb, "python": sys.version.split()[0],
                       "kernel": os.uname().release, "ts": time.time()}
                rungs.append_jsonl(out, rec)
                print("%-6s W=%-2d %.0f reads/s  mean %.3f ms  p50 %.3f  p99 %.3f" % (
                    pas, w, rec["iops"], rec["lat_mean_ms"], rec["lat_p50_ms"],
                    rec["lat_p99_ms"]), flush=True)
    finally:
        fsimg.lodetach(loop)
        os.remove(img)


if __name__ == "__main__":
    main()
