#!/usr/bin/env python3
"""E9b (exploratory, designed after E9's smoke run): why does one FIEMAP call cost about
0.3 ms on F2FS even with a warm cache and a one-block file?

Counts, with a BPF kprobe, how often the kernel calls f2fs_map_blocks per FIEMAP call
(f2fs_fiemap maps the file range by range, and steps over holes until it can mark the
last extent), for files of 1 and 32 blocks, warm, with the fork's request (whole address
space, 32 extents) and with a request up to the file's size. Times the same passes.
Run inside study/bin/run_in_ns.sh (needs BCC and its kernel headers).
"""

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from fpstudy import fsimg, rungs  # noqa: E402

sys.path.insert(0, HERE)
from e4_fiemap import make_file  # noqa: E402
from e9_calls import fiemap_fd  # noqa: E402

DATA = os.environ.get("FPSTUDY_DATA", "/root/fpstudy/data")
IMG = os.environ.get("FPSTUDY_IMG", "/root/fpstudy/img")
MNT = "/root/fpstudy/e9bmnt"
BLK = 4096

PROG = """
BPF_ARRAY(cnt, u64, 2);
int count_map(struct pt_regs *ctx) { int k = 0; u64 *v = cnt.lookup(&k); if (v) __sync_fetch_and_add(v, 1); return 0; }
int count_fiemap(struct pt_regs *ctx) { int k = 1; u64 *v = cnt.lookup(&k); if (v) __sync_fetch_and_add(v, 1); return 0; }
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--classes", default="1:200,32:200")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--out", default="e9b_f2fs_fiemap.jsonl")
    a = ap.parse_args()
    from bcc import BPF
    out = os.path.join(DATA, a.out)
    versions = rungs.code_versions()
    data = os.urandom(BLK)
    fs = fsimg.TestFS(os.path.join(IMG, "e9b_f2fs.img"), 2048, "f2fs", MNT)
    try:
        groups = {}
        for c in a.classes.split(","):
            blocks, n = (int(v) for v in c.split(":"))
            d = os.path.join(MNT, "b%d" % blocks)
            os.makedirs(d)
            paths = [os.path.join(d, "f%05d" % i) for i in range(n)]
            for p in paths:
                make_file(p, blocks, "f2fs", data)
            groups[blocks] = paths
        os.sync()
        b = BPF(text=PROG)
        b.attach_kprobe(event="f2fs_map_blocks", fn_name="count_map")
        b.attach_kprobe(event="f2fs_fiemap", fn_name="count_fiemap")
        cnt = b["cnt"]
        for rep in range(a.reps):
            for blocks, paths in groups.items():
                fds = [os.open(p, os.O_RDONLY) for p in paths]
                sizes = [os.fstat(fd).st_size for fd in fds]
                for fd in fds:  # priming: everything warm
                    fiemap_fd(fd)
                for mode in ("whole", "to_eof"):
                    cnt.clear()
                    t0 = time.perf_counter()
                    exts = [fiemap_fd(fd, None if mode == "whole" else sz) for fd, sz in zip(fds, sizes)]
                    dt = time.perf_counter() - t0
                    n_map = cnt[cnt.Key(0)].value
                    n_fm = cnt[cnt.Key(1)].value
                    rec = {"exp": "e9b", "fs": "f2fs", "blocks": blocks, "n": len(paths),
                           "mode": mode, "rep": rep, "us_per_call": 1e6 * dt / len(paths),
                           "fiemap_calls": n_fm, "map_blocks_calls": n_map,
                           "map_blocks_per_fiemap": n_map / max(n_fm, 1),
                           "extents_median": sorted(exts)[len(exts) // 2],
                           "versions": versions, "ts": time.time()}
                    rungs.append_jsonl(out, rec)
                    print("b=%-3d %-6s rep=%d %.1f us/call  f2fs_map_blocks per FIEMAP %.1f (%d calls)" % (
                        blocks, mode, rep, rec["us_per_call"], rec["map_blocks_per_fiemap"], n_fm),
                        flush=True)
                for fd in fds:
                    os.close(fd)
        try:  # BCC's own exit-time cleanup looks for tracefs, which the namespace lacks
            b.cleanup()
        except Exception:
            pass
    finally:
        fs.close()


if __name__ == "__main__":
    main()
