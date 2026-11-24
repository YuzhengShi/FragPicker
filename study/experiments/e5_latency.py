#!/usr/bin/env python3
"""E5: three ways to make storage "slow", same code under test (PLAN.md RQ3, H3c).

Code under test is the fork's EnhancedParallelProcessor.process_files with
enable_sorting=False (exactly what benchmarks/speedup_slow_io_benchmark.py times),
plus the sequential FIEMAP loop that the 5 ms results file calls "sequential".

Models of a slow device, each with delay d:
  sleep    FiemapAnalyzer.get_extents monkeypatched to time.sleep(d) first (the fork's
           method), file system on the fast loop device, warm cache
  dmdelay  no sleep; the file system sits on dm-delay with read delay d; cache cold
           (umount + drop_caches + mount before every run) or warm
  qd1      no sleep; the file system sits on an nbd device served by nbdkit with the
           delay filter and one thread, so requests are served one at a time (an
           idealised single-actuator disk without reordering); cache cold
Layouts: 'together' (N files created together, all traced) and 'scattered' (N files
sampled from a tree of 100*N files). Device reads come from /sys/block stat.
Run as root inside study/bin/run_in_ns.sh (uses /mnt).
"""

import argparse
import os
import random
import shutil
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from fpstudy import corpus, fsimg, rungs  # noqa: E402

CODE = os.environ.get("FPSTUDY_CODE", "/root/fpstudy/code")
sys.path.insert(0, os.path.join(CODE, "fork", "src", "analysis"))
from parallel_analyzer import fiemap as fiemap_mod  # noqa: E402
from parallel_analyzer.parallel_processor import EnhancedParallelProcessor  # noqa: E402

DATA = os.environ.get("FPSTUDY_DATA", "/root/fpstudy/data")
IMG = os.environ.get("FPSTUDY_IMG", "/root/fpstudy/img")
MNT = "/mnt"
ORIG = fiemap_mod.FiemapAnalyzer.get_extents


def set_sleep(d_ms):
    if not d_ms:
        fiemap_mod.FiemapAnalyzer.get_extents = ORIG
        return

    def slow(self, filepath, validate=True):
        time.sleep(d_ms / 1000.0)
        return ORIG(self, filepath, validate)

    fiemap_mod.FiemapAnalyzer.get_extents = slow


def run_engine(files, workers):
    if workers == 0:  # the sequential loop of the 5 ms results file
        from parallel_analyzer.inode_mapper import build_inode_map
        t0 = time.perf_counter()
        imap = build_inode_map(MNT, verbose=False)
        fa = fiemap_mod.FiemapAnalyzer()
        for ino, _ in files:
            p = imap.get(str(ino))
            if p and not os.path.isdir(p):
                fa.get_extents(p)
        return time.perf_counter() - t0
    proc = EnhancedParallelProcessor(num_workers=workers, mount_point=MNT,
                                     enable_monitoring=False, enable_profiling=False)
    t0 = time.perf_counter()
    proc.process_files(files, enable_sorting=False)
    return time.perf_counter() - t0


class NbdDevice:
    """nbdkit file plugin + delay filter, served over a unix socket to /dev/nbdN."""

    def __init__(self, backing, delay_ms, threads=1, nbd="/dev/nbd0"):
        self.sock = "/root/fpstudy/nbd.sock"
        if os.path.exists(self.sock):
            os.remove(self.sock)
        self.nbd = nbd
        args = ["nbdkit", "-f", "-U", self.sock, "--filter=delay", "-t", str(threads),
                "file", backing, "rdelay=%dms" % delay_ms, "wdelay=0"]
        self.p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  start_new_session=True)
        for _ in range(100):
            if os.path.exists(self.sock):
                break
            time.sleep(0.1)
        subprocess.run(["nbd-client", "-unix", self.sock, self.nbd, "-connections", "1",
                        "-block-size", "4096"], check=True, capture_output=True)

    def close(self):
        subprocess.run(["nbd-client", "-d", self.nbd], capture_output=True)
        try:
            os.killpg(self.p.pid, signal.SIGTERM)
        except Exception:
            pass
        self.p.wait(timeout=20)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--N", type=int, default=1000)
    ap.add_argument("--file-kb", type=int, default=100)
    ap.add_argument("--delays", default="1,5,10")
    ap.add_argument("--workers", default="0,1,2,4,8,16")
    ap.add_argument("--models", default="sleep,dmdelay,qd1")
    ap.add_argument("--layouts", default="together,scattered")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--out", default="e5_latency.jsonl")
    a = ap.parse_args()
    out = os.path.join(DATA, a.out)
    versions = rungs.code_versions()
    rnd = random.Random(21)
    delays = [int(x) for x in a.delays.split(",")]
    workers = [int(x) for x in a.workers.split(",")]
    for layout in a.layouts.split(","):
        T = a.N if layout == "together" else 100 * a.N
        size_kb = a.file_kb if layout == "together" else 4
        img = os.path.join(IMG, "e5_%s.img" % layout)
        size_mb = max(1024, int(T * (size_kb + 8) / 1024 * 1.5) + 512)
        fs = fsimg.TestFS(img, size_mb, "ext4", MNT)
        files = corpus.make_tree(MNT, T, per_dir=100, size=size_kb * 1024, seed=4)
        traced = files if layout == "together" else rnd.sample(files, a.N)
        tasks = [(str(ino), 1) for ino, _ in traced]
        fs.close(delete=False)

        def record(model, d, cache, w, rep, wall, io):
            rec = {"exp": "e5", "layout": layout, "T": T, "N": a.N, "model": model,
                   "delay_ms": d, "cache": cache, "workers": w, "rep": rep, "wall_s": wall,
                   "io": io, "versions": versions, "ts": time.time()}
            rungs.append_jsonl(out, rec)
            print("%-9s %-7s d=%-3d %-4s W=%-2d rep=%d wall=%.3fs reads=%s" % (
                layout, model, d, cache, w, rep, wall, io.get("read_ios") if io else "-"), flush=True)

        for model in a.models.split(","):
            for d in delays:
                if model == "sleep":
                    fs = fsimg.TestFS(img, size_mb, "ext4", MNT, fresh=False)
                    set_sleep(d)
                    run_engine(tasks[:50], 4)  # warm-up
                    for rep in range(a.reps):
                        for w in rnd.sample(workers, len(workers)):
                            record(model, d, "warm", w, rep, run_engine(tasks, w), {})
                    set_sleep(0)
                    fs.close(delete=False)
                elif model == "dmdelay":
                    fs = fsimg.TestFS(img, size_mb, "ext4", MNT, delay_ms=d, fresh=False)
                    for cache in ("cold", "warm"):
                        for rep in range(a.reps):
                            for w in rnd.sample(workers, len(workers)):
                                if cache == "cold":
                                    fs.remount_cold()
                                else:
                                    run_engine(tasks, 4)
                                s0 = fs.stat()
                                wall = run_engine(tasks, w)
                                record(model, d, cache, w, rep, wall, fsimg.blk_delta(s0, fs.stat()))
                    fs.close(delete=False)
                elif model == "qd1":
                    nbd = NbdDevice(img, d, threads=1)
                    try:
                        for rep in range(a.reps):
                            for w in rnd.sample(workers, len(workers)):
                                fsimg.drop_caches()
                                fsimg.mount(nbd.nbd, MNT, "ext4")
                                s0 = fsimg.blk_stat(nbd.nbd)
                                wall = run_engine(tasks, w)
                                io = fsimg.blk_delta(s0, fsimg.blk_stat(nbd.nbd))
                                fsimg.umount(MNT)
                                record(model, d, "cold", w, rep, wall, io)
                    finally:
                        fsimg.umount(MNT)
                        nbd.close()
        os.remove(img)


if __name__ == "__main__":
    main()
