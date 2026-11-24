"""Single-threaded re-implementation of FragPicker's analysis phase.

This is rung (c) of the ablation ladder: same input (./trace.result produced by
parse.sh) and the same outputs as upstream processing.py (<ino>.txt, filelist.txt)
and, with full=True, also merge.py (<ino>.merged) and hotness.sh (<ino>.sorted),
but without per-line open/append/close, without one `find -inum` per file and
without any subprocess.

Output fidelity: lines are produced with upstream's exact arithmetic (including its
end-alignment formula) and ordered the way GNU `sort -g` orders them in the C
locale (numeric value of the line prefix, ties broken by a byte-wise comparison of
the whole line). E1 checks byte equality against the unmodified upstream scripts.
"""

import os
import sys
import time

BLOCK = 4096
RA = 131072


def align_upstream(start, end):
    # upstream src/analysis/processing.py lines 32-35
    if start % BLOCK != 0:
        start -= start % BLOCK
    if (end + 1) % BLOCK != 0:
        end += end % BLOCK - 1
    return start, end


def align_fork(start, end):
    # fork src/analysis/processing.py lines 113-116 (and 291-294)
    if start % BLOCK != 0:
        start -= start % BLOCK
    if (end + 1) % BLOCK != 0:
        end += BLOCK - ((end + 1) % BLOCK) - 1
    return start, end


def align_correct(start, end):
    if start % BLOCK != 0:
        start -= start % BLOCK
    if (end + 1) % BLOCK != 0:
        end = (end // BLOCK + 1) * BLOCK - 1
    return start, end


ALIGN = {"upstream": align_upstream, "fork": align_fork, "correct": align_correct}


def phase1(trace_path, align="upstream"):
    """Return {inode_bytes: [line_bytes, ...]} in trace order, like upstream Phase 1.

    Mirrors upstream exactly: lines whose first token is b'=' are skipped; the
    readahead window logic is applied per inode number (int); the per-file key is
    the inode token as written in the trace (bytes).
    """
    fn = ALIGN[align]
    per_file = {}
    req_end = {}
    ra_window = {}
    with open(trace_path, "rb") as f:
        data = f.read()
    for line in data.splitlines():
        req = line.split()
        if req[0] == b"=":
            continue
        ino = int(req[0])
        size = int(req[1])
        start = int(req[2])
        end = start + size - 1
        direct = int(req[3])
        rw = int(req[4])
        start, end = fn(start, end)
        if ino in req_end and start == req_end[ino] + 1 and direct == 0 and rw == 0:
            req_end[ino] = end
            if ra_window[ino] >= end:
                continue
            if size <= RA:
                end = start + RA - 1
            ra_window[ino] = end
        else:
            req_end[ino] = end
            ra_window[ino] = 0
        key = req[0]
        out = b"%d %d 1\n" % (start, end)
        lst = per_file.get(key)
        if lst is None:
            per_file[key] = [out]
        else:
            lst.append(out)
    return per_file


def _sort_g_key(line):
    """Key that reproduces GNU `sort -g` in the C locale for our integer lines."""
    sp = line.find(b" ")
    head = line if sp < 0 else line[:sp]
    try:
        num = float(head)
    except ValueError:
        num = float("-inf")
    return (num, line)


def build_inode_map(mount_point):
    """One walk of the tree: {inode_str: [path, ...]} (directories included, like find)."""
    imap = {}
    stack = [mount_point]
    # find prints the start point itself as well
    try:
        st = os.lstat(mount_point)
        imap.setdefault(str(st.st_ino), []).append(mount_point)
    except OSError:
        return imap
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    imap.setdefault(str(e.inode()), []).append(e.path)
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
        except OSError:
            pass
    return imap


def merge_lines(lines):
    """upstream merge.py on already sorted '<start> <end> <n>' lines."""
    out = []
    ws = we = -1
    nums = 0
    begin = False
    for ln in lines:
        sp = ln.split()
        start = int(sp[0]); end = int(sp[1]); n = int(sp[2])
        if we < start:
            if begin:
                out.append(b"%d %d %d\n" % (ws, we, nums))
            ws, we, nums = start, end, n
            begin = True
            continue
        if we >= end:
            nums += 1
            continue
        if we <= end:
            nums += 1
            we = end
    out.append(b"%d %d %d\n" % (ws, we, nums))
    return out


def _hot_key(line):
    sp = line.split()
    return (-float(sp[2]), line)


def hotness_lines(merged, pct):
    """hotness.sh: sort -g -k3,3gr | head -n | sort -g, integer bash arithmetic."""
    n = len(merged) * pct // 100
    hot = sorted(merged, key=_hot_key)[:n]
    return sorted(hot, key=_sort_g_key)


def analyze(trace_path="./trace.result", mount_point="/mnt", outdir=".",
            align="upstream", full=False, pct=100, timings=None):
    t0 = time.perf_counter()
    per_file = phase1(trace_path, align)
    t1 = time.perf_counter()
    imap = build_inode_map(mount_point)
    t2 = time.perf_counter()
    kept = []
    for key, lines in per_file.items():
        ino = key.decode("utf-8")
        paths = imap.get(ino)
        if not paths:
            continue
        joined = "\n".join(paths)
        if os.path.isdir(joined):
            continue
        lines.sort(key=_sort_g_key)
        with open(os.path.join(outdir, ino + ".txt"), "wb") as f:
            f.writelines(lines)
        kept.append((ino, len(lines), lines))
    with open(os.path.join(outdir, "filelist.txt"), "w") as fl:
        for ino, n, _ in kept:
            fl.write("%s %d\n" % (ino, n))
    t3 = time.perf_counter()
    if full:
        for ino, _, lines in kept:
            merged = merge_lines(lines)
            with open(os.path.join(outdir, ino + ".merged"), "wb") as f:
                f.writelines(merged)
            with open(os.path.join(outdir, ino + ".sorted"), "wb") as f:
                f.writelines(hotness_lines(merged, pct))
    t4 = time.perf_counter()
    if timings is not None:
        timings.update(phase1=t1 - t0, inode_map=t2 - t1, per_file=t3 - t2,
                       merge_hotness=t4 - t3, total=t4 - t0,
                       files=len(kept), map_entries=len(imap))
    return kept


def main(argv):
    import argparse, json
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--trace", default="./trace.result")
    ap.add_argument("--mount-point", default="/mnt")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--align", default="upstream", choices=sorted(ALIGN))
    ap.add_argument("--full", action="store_true", help="also do merge.py and hotness.sh")
    ap.add_argument("--pct", type=int, default=100)
    ap.add_argument("--timings-json", default=None)
    a = ap.parse_args(argv)
    t = {}
    analyze(a.trace, a.mount_point, a.outdir, a.align, a.full, a.pct, t)
    if a.timings_json:
        with open(a.timings_json, "w") as f:
            json.dump(t, f)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
