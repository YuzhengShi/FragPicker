#!/usr/bin/env python3
"""E0: capture real traces with upstream's own trace.sh (BCC) and characterise them.

Workloads (all on an ext4 loop file system mounted at /mnt, as upstream assumes):
  read_seq     upstream evaluation/read_benchmark/read_seq.c on a 1 GiB file, 128 KiB O_DIRECT
  read_stride  upstream read_stride.c on the same file
  tar          tar over a ~20k-file source tree (buffered reads, many files)
  fio          fio file-server-like job: 1000 x 1 MiB files, 4 KiB random buffered reads
  sqlite3      SQLite random point lookups on a ~200 MB database with a 1 MiB page cache
  dd_hi        dd reading 1 MiB at offset 5 GiB of a sparse 8 GiB file (checks pos = %u)

For each: trace runtime with and without tracing, raw/parsed line counts, unique inodes,
inodes that resolve to a file the workload did not read (the trace has no device id),
and parse.sh time. Raw and parsed traces are kept (gzip) for E2. The file system image
is kept at $FPSTUDY_IMG/e0.img so that inode numbers stay valid for E2.
Run inside study/bin/run_in_ns.sh.
"""

import glob
import gzip
import json
import os
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from fpstudy import fsimg, fastpath, rungs  # noqa: E402

DATA = os.environ.get("FPSTUDY_DATA", "/root/fpstudy/data")
WORK = os.environ.get("FPSTUDY_WORK", "/root/fpstudy/work")
IMG = os.environ.get("FPSTUDY_IMG", "/root/fpstudy/img")
CODE = os.environ.get("FPSTUDY_CODE", "/root/fpstudy/code")
UPA = os.path.join(CODE, "upstream", "src", "analysis")
OUT = os.path.join(DATA, "e0_traces.jsonl")
TRDIR = os.path.join(DATA, "e0_traces")
MNT = "/mnt"


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, check=True, **kw)


def build_inputs():
    """Create the workloads' files. Returns {workload: set(inodes it reads)}."""
    bindir = os.path.join(WORK, "bin")
    os.makedirs(bindir, exist_ok=True)
    rb = os.path.join(CODE, "upstream", "evaluation", "read_benchmark")
    for prog in ("read_seq", "read_stride"):
        sh("gcc -O2 -o %s/%s %s/%s.c" % (bindir, prog, rb, prog))
    # 1 GiB file for read_seq / read_stride
    sh("dd if=/dev/zero of=/mnt/2 bs=1M count=1024 oflag=direct status=none")
    # source tree for tar
    src = "/mnt/src"
    os.makedirs(src, exist_ok=True)
    for d in ("/usr/lib/python3.12", "/usr/include", "/usr/share/perl"):
        if os.path.isdir(d):
            sh("cp -a %s %s/ 2>/dev/null || true" % (d, src))
    # fio files
    os.makedirs("/mnt/fio", exist_ok=True)
    sh("fio --name=fs --directory=/mnt/fio --nrfiles=1000 --filesize=1m --size=1000m "
       "--create_only=1 --rw=randread --bs=4k >/dev/null", )
    # sqlite database
    db = "/mnt/db.sqlite"
    sql = ("PRAGMA journal_mode=OFF; CREATE TABLE t(id INTEGER PRIMARY KEY, v BLOB);"
           "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c WHERE x<2000000) "
           "INSERT INTO t SELECT x, randomblob(80) FROM c;")
    sh("sqlite3 %s '%s'" % (db, sql))
    import random
    rnd = random.Random(3)
    with open(os.path.join(WORK, "queries.sql"), "w") as f:
        f.write("PRAGMA cache_size=-1024;\n")
        for _ in range(50000):
            f.write("SELECT length(v) FROM t WHERE id=%d;\n" % rnd.randint(1, 2000000))
    # sparse 8 GiB file for the %u check
    with open("/mnt/sparse8g", "wb") as f:
        f.truncate(8 << 30)
    os.sync()

    def inodes_under(p):
        s = set()
        for root, dirs, files in os.walk(p):
            for fn in files:
                s.add(os.stat(os.path.join(root, fn)).st_ino)
        return s

    st = lambda p: {os.stat(p).st_ino}
    return {
        "read_seq": st("/mnt/2"), "read_stride": st("/mnt/2"),
        "tar": inodes_under(src), "fio": inodes_under("/mnt/fio"),
        "sqlite3": st(db), "dd_hi": st("/mnt/sparse8g"),
    }


def workloads():
    b = os.path.join(WORK, "bin")
    return [
        ("read_seq", "read_seq", "%s/read_seq /mnt/2 128 >/dev/null" % b),
        ("read_stride", "read_stride", "%s/read_stride /mnt/2 128 >/dev/null" % b),
        ("tar", "tar", "tar -cf - /mnt/src 2>/dev/null | cat >/dev/null"),
        ("fio", "fio", "fio --name=fs --directory=/mnt/fio --nrfiles=1000 --filesize=1m "
                       "--size=1000m --rw=randread --bs=4k --ioengine=psync --io_size=256m "
                       "--norandommap --randrepeat=1 >/dev/null"),
        ("sqlite3", "sqlite3", "sqlite3 /mnt/db.sqlite < %s/queries.sql >/dev/null" % WORK),
        ("dd_hi", "dd", "dd if=/mnt/sparse8g of=/dev/null bs=1M skip=5120 count=1 status=none"),
    ]


def timed(cmd):
    t0 = time.perf_counter()
    subprocess.run(cmd, shell=True, check=True)
    return time.perf_counter() - t0


def trace_one(name, comm, cmd, wd):
    os.makedirs(wd, exist_ok=True)
    for f in glob.glob(os.path.join(wd, "*")):
        os.remove(f)
    fsimg.drop_caches()
    t_plain = timed(cmd)
    fsimg.drop_caches()
    err = open(os.path.join(wd, "tracer.stderr"), "w")
    # upstream trace.sh starts two BCC `trace` processes in the background, appending
    # to ./trace.result; run it in its own session so we can signal the whole group
    p = subprocess.Popen(["bash", os.path.join(UPA, "trace.sh"), comm], cwd=wd,
                         stdout=subprocess.DEVNULL, stderr=err, start_new_session=True)
    tr = os.path.join(wd, "trace.result")
    t_wait = time.time()
    while time.time() - t_wait < 120:  # both tracers print a header line when attached
        if os.path.exists(tr):
            with open(tr) as f:
                if sum(1 for l in f if l.startswith("PID")) >= 2:
                    break
        time.sleep(0.5)
    attach_s = time.time() - t_wait
    t_traced = timed(cmd)
    time.sleep(3)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            for pid in subprocess.run(["pgrep", "-f", "bcc/tools/trace"], capture_output=True,
                                      text=True).stdout.split():
                os.kill(int(pid), sig)
        except Exception:
            pass
        time.sleep(2)
    p.wait(timeout=30)
    err.close()
    with open(os.path.join(wd, "tracer.stderr")) as f:
        lost = [l.strip() for l in f if "lost" in l.lower()]
    raw_lines = sum(1 for _ in open(tr))
    os.makedirs(TRDIR, exist_ok=True)
    with open(tr, "rb") as fi, gzip.open(os.path.join(TRDIR, name + ".raw.gz"), "wb") as fo:
        shutil.copyfileobj(fi, fo)
    t0 = time.perf_counter()
    subprocess.run(["bash", os.path.join(UPA, "parse.sh")], cwd=wd, check=True)
    t_parse = time.perf_counter() - t0
    with open(tr, "rb") as fi, gzip.open(os.path.join(TRDIR, name + ".parsed.gz"), "wb") as fo:
        shutil.copyfileobj(fi, fo)
    return {"t_plain_s": t_plain, "t_traced_s": t_traced, "attach_s": attach_s,
            "lost_msgs": lost[:5], "raw_lines": raw_lines, "t_parse_s": t_parse}


def characterise(parsed, truth, imap):
    L = 0
    inos = {}
    maxpos = 0
    direct = 0
    with open(parsed, "rb") as f:
        for line in f:
            t = line.split()
            if not t or t[0] == b"=":
                continue
            L += 1
            ino = int(t[0])
            inos[ino] = inos.get(ino, 0) + 1
            maxpos = max(maxpos, int(t[2]))
            direct += int(t[3]) != 0
    on_mnt = [i for i in inos if str(i) in imap]
    wrong = [i for i in on_mnt if i not in truth]
    return {"L": L, "F_unique": len(inos), "F_resolving_on_mnt": len(on_mnt),
            "F_truth": len(truth), "F_truth_seen": len(set(inos) & truth),
            "aliased_inodes": len(wrong), "aliased_lines": sum(inos[i] for i in wrong),
            "max_pos": maxpos, "direct_frac": direct / L if L else 0}


def main():
    for d in (DATA, WORK, IMG, TRDIR):
        os.makedirs(d, exist_ok=True)
    img = os.path.join(IMG, "e0.img")
    fs = fsimg.TestFS(img, 8192, "ext4", MNT)
    try:
        truth = build_inputs()
        imap = fastpath.build_inode_map(MNT)
        for name, comm, cmd in workloads():
            wd = os.path.join(WORK, "e0", name)
            r = trace_one(name, comm, cmd, wd)
            r.update(characterise(os.path.join(wd, "trace.result"), truth[name], imap))
            r.update({"exp": "e0", "workload": name, "comm": comm, "cmd": cmd,
                      "versions": rungs.code_versions(), "ts": time.time()})
            rungs.append_jsonl(OUT, r)
            print(json.dumps(r, sort_keys=True), flush=True)
        with open(os.path.join(TRDIR, "truth_inodes.json"), "w") as f:
            json.dump({k: sorted(v) for k, v in truth.items()}, f)
    finally:
        fs.close(delete=False)  # keep the image: E2 replays these traces against it
    print("E0 done ->", OUT)


if __name__ == "__main__":
    main()
