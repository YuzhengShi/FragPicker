#!/usr/bin/env python3
"""E1: do the rungs produce the same analysis output? (PLAN.md RQ4)

Run as root inside a private mount namespace (study/bin/run_in_ns.sh), because the
code under test scans /mnt. Writes one JSON line per (case, rung) to
$FPSTUDY_DATA/e1_correctness.jsonl.
"""

import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from fpstudy import corpus, fsimg, rungs  # noqa: E402

DATA = os.environ.get("FPSTUDY_DATA", "/root/fpstudy/data")
WORK = os.environ.get("FPSTUDY_WORK", "/root/fpstudy/work")
IMG = os.environ.get("FPSTUDY_IMG", "/root/fpstudy/img")
OUT = os.path.join(DATA, "e1_correctness.jsonl")
MNT = "/mnt"


def record(case, res, extra=None):
    rec = {"exp": "e1", "case": case, "ts": time.time(), "versions": rungs.code_versions()}
    rec.update(res)
    if extra:
        rec.update(extra)
    rungs.append_jsonl(OUT, rec)
    print("%-28s %-6s %-8s digest=%s n=%-5d wall=%.2fs leaked=%d %s" % (
        case, res["rung"], res["status"], res["digest"], res["filelist_n"], res["wall_s"],
        res["leaked_tmpdirs"], res.get("out_tail", "")[:160].replace("\n", " | ")), flush=True)


def run_case(case, trace, rung_list, timeout=600, pre=None, post=None):
    out = {}
    for r in rung_list:
        wd = os.path.join(WORK, "e1", case, r)
        res = rungs.run_rung(r, trace, wd, timeout=timeout) if not pre else run_keep(r, trace, wd, timeout, pre)
        extra = post(wd) if post else None
        record(case, res, extra)
        out[r] = res
    return out


def run_keep(r, trace, wd, timeout, pre):
    # run_rung wipes the workdir, so for cases that seed the workdir we re-seed after copy
    os.makedirs(wd, exist_ok=True)
    shutil.rmtree(wd)
    os.makedirs(wd)
    pre(wd)
    shutil.copy(trace, os.path.join(wd, "trace.result"))
    cmd, pypath = rungs.rung_cmd(r)
    env = dict(os.environ, LC_ALL="C", PYTHONDONTWRITEBYTECODE="1")
    if pypath:
        env["PYTHONPATH"] = pypath
    rungs.clean_tmp()
    t0 = time.perf_counter()
    try:
        p = subprocess.run(cmd, cwd=wd, env=env, capture_output=True, timeout=timeout)
        status = "ok" if p.returncode == 0 else "rc=%d" % p.returncode
        tail = (p.stdout[-300:] + p.stderr[-300:]).decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        status, tail = "timeout", ""
    wall = time.perf_counter() - t0
    dg, n = rungs.digest(wd)
    return {"rung": r, "status": status, "wall_s": wall, "user_s": None, "sys_s": None,
            "maxrss_kb": None, "digest": dg, "filelist_n": n,
            "leaked_tmpdirs": rungs.clean_tmp(), "out_tail": tail if status != "ok" else ""}


def main():
    os.makedirs(WORK, exist_ok=True)
    os.makedirs(IMG, exist_ok=True)
    if os.path.exists(OUT):
        os.rename(OUT, OUT + ".%d.bak" % int(time.time()))
    RUNGS = ["a", "b", "c", "d1", "d8", "e8"]

    # ---------- ext4 test file system ----------
    fs = fsimg.TestFS(os.path.join(IMG, "e1.img"), 2048, "ext4", MNT)
    try:
        files = corpus.make_tree(MNT, 300, per_dir=50, size=65536)
        traced = [ino for ino, _ in files[:60]]

        # A: aligned O_DIRECT sequential reads, like upstream's read benchmark
        tA = os.path.join(WORK, "traceA.result")
        corpus.gen_trace(tA, traced, 20, req_size=131072, direct=16384, pattern="seq")
        run_case("A_aligned_direct", tA, RUNGS)

        # B: unaligned buffered reads (size and offset not multiples of 4096)
        tB = os.path.join(WORK, "traceB.result")
        corpus.gen_trace(tB, traced, 20, req_size=10000, direct=0, pattern="rand",
                         unaligned=True, seed=7)
        run_case("B_unaligned_buffered", tB, RUNGS)

        # D: a stale *.txt in the working directory (Phase 3 of --parallel globs *.txt)
        stale = b"5\n3\n1\n"

        def seed_stale(wd):
            with open(os.path.join(wd, "notes.txt"), "wb") as f:
                f.write(stale)

        def check_stale(wd):
            with open(os.path.join(wd, "notes.txt"), "rb") as f:
                return {"stale_txt_after": f.read().decode()}

        run_case("D_stale_txt_in_cwd", tA, ["a", "c", "d8"], pre=seed_stale, post=check_stale)

        # F: inode numbers in the trace that do not belong to /mnt (e.g. libc read by the
        # traced process). Trace lines carry no device id, so a number that also exists
        # on /mnt is attributed to the wrong file. Here: inodes of root-FS files.
        foreign = []
        for p in ("/usr/bin/python3", "/usr/lib/x86_64-linux-gnu/libc.so.6", "/etc/passwd"):
            try:
                foreign.append(os.stat(os.path.realpath(p)).st_ino)
            except OSError:
                pass
        mnt_inodes = {ino for ino, _ in files}
        rec = {"exp": "e1", "case": "F_foreign_inodes", "foreign_inodes": foreign,
               "collide_with_mnt": [i for i in foreign if i in mnt_inodes],
               "mnt_inode_range": [min(mnt_inodes), max(mnt_inodes)]}
        rungs.append_jsonl(OUT, rec)
        print(json.dumps(rec), flush=True)
    finally:
        fs.close()

    # ---------- E: more traced files than the parallel engine's task queue holds ----------
    fs = fsimg.TestFS(os.path.join(IMG, "e1q.img"), 2048, "ext4", MNT)
    try:
        files = corpus.make_tree(MNT, 10001, per_dir=500, size=4096)
        for n in (10000, 10001):
            tE = os.path.join(WORK, "traceE%d.result" % n)
            corpus.gen_trace(tE, [ino for ino, _ in files[:n]], 1)
            run_case("E_queue_%d_files" % n, tE, ["c", "d8"], timeout=180)
    finally:
        fs.close()

    # ---------- C: file systems without FIEMAP ----------
    # tmpfs
    os.makedirs(MNT, exist_ok=True)
    subprocess.run(["mount", "-t", "tmpfs", "-o", "size=512m", "tmpfs", MNT], check=True)
    try:
        files = corpus.make_tree(MNT, 100, per_dir=50, size=65536)
        tC = os.path.join(WORK, "traceC.result")
        corpus.gen_trace(tC, [ino for ino, _ in files[:40]], 10)
        run_case("C_tmpfs_no_fiemap", tC, ["a", "b", "c", "d8"])
    finally:
        subprocess.run(["umount", MNT])
    # 9p (WSL drvfs view of a Windows NTFS directory), bind-mounted at /mnt before the
    # namespace hid /mnt/d: see run_in_ns.sh, which binds it at /root/fpstudy/ns9p
    ns9p = "/root/fpstudy/ns9p"
    if os.path.ismount(ns9p):
        subprocess.run(["mount", "--bind", ns9p, MNT], check=True)
        try:
            root9 = os.path.join(MNT, "e1tree")
            shutil.rmtree(root9, ignore_errors=True)
            files = corpus.make_tree(root9, 60, per_dir=30, size=65536)
            t9 = os.path.join(WORK, "trace9p.result")
            corpus.gen_trace(t9, [ino for ino, _ in files[:30]], 10)
            run_case("C_9p_drvfs_no_fiemap", t9, ["a", "b", "c", "d8"])
            shutil.rmtree(root9, ignore_errors=True)
        finally:
            subprocess.run(["umount", MNT])
    print("E1 done ->", OUT)


if __name__ == "__main__":
    main()
