"""Run the rungs of the ablation ladder on one prepared trace and collect timings and
an output digest.

Rungs (study/PLAN.md, RQ2):
  a   upstream src/analysis/processing.py, unmodified
  b   fork processing.py, sequential path (no --parallel)
  c   study fastpath.py (single thread, batch inode map, no subprocesses)
  d<W> fork processing.py --parallel --workers W
  e<W> like d<W> but FiemapAnalyzer.get_extents replaced by a stub returning []
       (isolates the cost of the FIEMAP whose result nothing downstream reads)
  m<W> like d<W> but the engine's BackgroundMonitor replaced by a no-op (isolates the
       resource-monitor thread, whose stop() waits out its 1 s sleep)

All rungs read ./trace.result in a fresh working directory and scan /mnt, so the
caller must have mounted the file system under test at /mnt (inside a private
mount namespace on WSL, where /mnt normally holds /mnt/c and /mnt/d).
"""

import glob
import hashlib
import json
import os
import resource
import shutil
import subprocess
import sys
import time

CODE = os.environ.get("FPSTUDY_CODE", "/root/fpstudy/code")
UP = os.path.join(CODE, "upstream", "src", "analysis")
FK = os.path.join(CODE, "fork", "src", "analysis")
ST = os.path.join(CODE, "study", "lib", "fpstudy")

STUB_E = r'''
import sys, runpy
sys.path.insert(0, %(fk)r)
sys.argv = ["processing.py"] + sys.argv[1:]
from parallel_analyzer import fiemap as _f
def _stub(self, filepath, validate=True):
    return []
_f.FiemapAnalyzer.get_extents = _stub
runpy.run_path(%(fk)r + "/processing.py", run_name="__main__")
'''

# parallel_processor imports BackgroundMonitor by name, so the stub replaces that name
STUB_M = r'''
import sys, runpy
sys.path.insert(0, %(fk)r)
sys.argv = ["processing.py"] + sys.argv[1:]
from parallel_analyzer import parallel_processor as _pp
class _NoMonitor:
    def __init__(self, *args, **kwargs):
        pass
    def start(self):
        pass
    def stop(self):
        return {}
_pp.BackgroundMonitor = _NoMonitor
runpy.run_path(%(fk)r + "/processing.py", run_name="__main__")
'''


def rung_cmd(rung):
    py = sys.executable
    if rung == "a":
        return [py, os.path.join(UP, "processing.py")], UP
    if rung == "b":
        return [py, os.path.join(FK, "processing.py"), "--mount-point", "/mnt", "--quiet"], FK
    if rung == "c":
        return [py, os.path.join(ST, "fastpath.py"), "--mount-point", "/mnt"], None
    if rung == "cfull":
        return [py, os.path.join(ST, "fastpath.py"), "--mount-point", "/mnt", "--full"], None
    if rung.startswith("d"):
        w = int(rung[1:])
        return [py, os.path.join(FK, "processing.py"), "--parallel", "--workers", str(w),
                "--mount-point", "/mnt"], FK
    if rung.startswith("e"):
        w = int(rung[1:])
        stub = os.path.join(os.environ.get("FPSTUDY_WORK", "/root/fpstudy/work"), "stub_e.py")
        with open(stub, "w") as f:
            f.write(STUB_E % {"fk": FK})
        return [py, stub, "--parallel", "--workers", str(w), "--mount-point", "/mnt"], FK
    if rung.startswith("m"):
        w = int(rung[1:])
        stub = os.path.join(os.environ.get("FPSTUDY_WORK", "/root/fpstudy/work"), "stub_m.py")
        with open(stub, "w") as f:
            f.write(STUB_M % {"fk": FK})
        return [py, stub, "--parallel", "--workers", str(w), "--mount-point", "/mnt"], FK
    raise ValueError(rung)


def clean_tmp():
    """The fork's parallel engine leaves mkdtemp directories behind; count and remove."""
    leaked = glob.glob("/tmp/fragpicker_sort_*") + glob.glob("/tmp/sort_*")
    for d in leaked:
        shutil.rmtree(d, ignore_errors=True)
    return len(leaked)


def digest(workdir, with_pipeline=False):
    """Hash of the analysis result: the set of filelist lines and each listed file's
    <ino>.txt (and .merged/.sorted when with_pipeline)."""
    h = hashlib.sha256()
    fl = os.path.join(workdir, "filelist.txt")
    lines = []
    if os.path.exists(fl):
        with open(fl, "rb") as f:
            lines = sorted(l for l in f.read().splitlines() if l.strip())
    for l in lines:
        h.update(l + b"\n")
    exts = [".txt"] + ([".merged", ".sorted"] if with_pipeline else [])
    for l in lines:
        ino = l.split()[0].decode()
        for ext in exts:
            p = os.path.join(workdir, ino + ext)
            h.update(ext.encode())
            if os.path.exists(p):
                with open(p, "rb") as f:
                    h.update(f.read())
            else:
                h.update(b"<missing>")
    return h.hexdigest()[:16], len(lines)


def run_rung(rung, trace_path, workdir, timeout=3600, env_extra=None):
    """Fresh workdir with a copy of trace.result; run; return a result dict."""
    if os.path.exists(workdir):
        shutil.rmtree(workdir)
    os.makedirs(workdir)
    shutil.copy(trace_path, os.path.join(workdir, "trace.result"))
    cmd, pypath = rung_cmd(rung)
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if pypath:
        env["PYTHONPATH"] = pypath
    # interpreters without a psutil build (batch 6: 3.14, 3.14t) need the stand-in in the
    # rungs' own processes too, after the code under test
    extra = os.environ.get("FPSTUDY_EXTRA_PYTHONPATH")
    if extra:
        env["PYTHONPATH"] = (env["PYTHONPATH"] + ":" + extra) if env.get("PYTHONPATH") else extra
    if env_extra:
        env.update(env_extra)
    leaked_before = clean_tmp()
    r0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    t0 = time.perf_counter()
    status = "ok"
    try:
        p = subprocess.run(cmd, cwd=workdir, env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout)
        rc = p.returncode
        out_tail = (p.stdout[-400:] + p.stderr[-400:]).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as ex:
        rc = None
        status = "timeout"
        out_tail = ((ex.stdout or b"")[-300:] + (ex.stderr or b"")[-300:]).decode("utf-8", "replace")
    t1 = time.perf_counter()
    r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    if rc not in (0, None):
        status = "rc=%d" % rc
    dg, nlist = digest(workdir)
    leaked = clean_tmp()
    return {
        "rung": rung, "status": status, "wall_s": t1 - t0,
        "user_s": r1.ru_utime - r0.ru_utime, "sys_s": r1.ru_stime - r0.ru_stime,
        "maxrss_kb": r1.ru_maxrss, "digest": dg, "filelist_n": nlist,
        "leaked_tmpdirs": leaked, "out_tail": out_tail if status != "ok" else "",
    }


def code_versions():
    v = {}
    for name in ("upstream", "fork"):
        try:  # written by study/bin/sync_code.sh (the copies are git-archive exports)
            with open(os.path.join(CODE, name + ".HEAD")) as f:
                v[name] = f.read().strip()[:12]
        except OSError:
            v[name] = "?"
    v["kernel"] = os.uname().release
    v["python"] = sys.version.split()[0]
    return v


def append_jsonl(path, rec):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")
