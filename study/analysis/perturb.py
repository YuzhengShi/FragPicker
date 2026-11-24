#!/usr/bin/env python3
"""Detect external load after the fact: a window in which runs of every rung are slow together.

For each timed run, the ratio of its time to the median of its own cell (same experiment
parameters and rung). Runs are grouped into 5-minute windows (UTC); a window is flagged when
at least 3 runs and at least 30% of its runs take more than 1.3x their cell median.
Usage: python3 analysis/perturb.py data/e2_real.jsonl data/e2_ladder.jsonl ...
"""
import json, collections, statistics, datetime, sys
def val(r):
    if r.get("rung") == "pipe_a":
        return r["processing_s"] + r["merge_s"] + r["hotness_s"]
    for k in ("wall_s", "total_s", "phase1_s", "t_s", "elapsed_s"):
        if isinstance(r.get(k), (int, float)):
            return r[k]
    return None
for fn in sys.argv[1:]:
    rows = [json.loads(l) for l in open(fn)]
    rows = [r for r in rows if r.get("status", "ok") == "ok" and isinstance(r.get("ts"), (int, float))]
    keyf = lambda r: tuple((k, str(r.get(k))) for k in sorted(r) if k in
                           ("workload", "cache", "rung", "T", "F", "delay_ms", "fs", "L", "variant", "model", "layout", "workers", "threads", "kind", "blocks", "pass", "order", "device"))
    cells = collections.defaultdict(list)
    for r in rows:
        v = val(r)
        if v is not None:
            cells[keyf(r)].append((r["ts"], v))
    win = collections.defaultdict(list)
    for k, xs in cells.items():
        if len(xs) < 3:
            continue
        m = statistics.median(v for _, v in xs)
        if m <= 0.05:
            continue
        for ts, v in xs:
            win[int(ts // 300) * 300].append(v / m)
    print("==", fn, len(rows), "rows")
    for w in sorted(win):
        rs = win[w]
        n_hi = sum(1 for x in rs if x > 1.3)
        flag = "  <-- slow window" if n_hi >= 3 and n_hi >= 0.3 * len(rs) else ""
        print("  %s  n=%3d  median ratio %.2f  >1.3x: %3d%s" % (
            datetime.datetime.fromtimestamp(w, datetime.timezone.utc).strftime("%H:%M"), len(rs), statistics.median(rs), n_hi, flag))
