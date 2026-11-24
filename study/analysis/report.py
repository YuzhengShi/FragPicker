#!/usr/bin/env python3
"""Build every table, figure and quoted number of the paper from study/data/*.jsonl.

Usage: python3 study/analysis/report.py [--data study/data] [--out study]
Writes study/results/*.md (tables), study/results/numbers.json (every number the
paper quotes, with the records it came from) and study/figs/*.pdf|png.
"""

import argparse
import collections
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from fpstudy.stats import load_jsonl, median_ci, ratio_ci, cv  # noqa: E402

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# categorical slots in fixed order (validated: dataviz validate_palette.js, light mode)
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
MARK = ["o", "s", "^", "D", "v", "P", "X", "*"]
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"

RUNG_LABEL = {
    "a": "(a) upstream", "b": "(b) fork, sequential", "c": "(c) single-thread rewrite",
    "d1": "(d) --parallel, 1 thread", "d4": "(d) --parallel, 4 threads",
    "d8": "(d) --parallel, 8 threads", "d16": "(d) --parallel, 16 threads",
    "e8": "(e) 8 threads, no FIEMAP",
    "m1": "(d) 1 thread, no monitor thread", "m8": "(d) 8 threads, no monitor thread",
}
RUNG_ORDER = ["a", "b", "c", "d1", "d4", "d8", "d16", "e8", "m1", "m8"]
# rungs drawn in the paper's ladder figures, each with a fixed colour and marker
RUNG_FIG = ["a", "c", "d1", "d8", "e8"]
RUNG_STYLE = {"a": 0, "c": 1, "d1": 2, "d8": 3, "e8": 4, "b": 5, "d4": 6, "d16": 7}

NUMBERS = {}
EXCLUDE = {}


def load(path):
    """load_jsonl with the documented exclusions of study/data/EXCLUDE.json applied."""
    rows = load_jsonl(path)
    ex = EXCLUDE.get(os.path.basename(path))
    if ex and "ts_before" in ex:
        rows = [r for r in rows if r.get("ts") is None or r["ts"] >= ex["ts_before"]]
    if ex and "where" in ex:  # drop rows whose fields all match
        def match(r):
            return all((r.get(k) in v) if isinstance(v, list) else (r.get(k) == v)
                       for k, v in ex["where"].items())
        rows = [r for r in rows if not match(r)]
    for extra in (ex or {}).get("append", []):  # rows re-measured in another file
        p2 = os.path.join(os.path.dirname(path), extra)
        if os.path.exists(p2):
            rows += load_jsonl(p2)
    return rows


def num(key, value, src):
    NUMBERS[key] = {"value": value, "source": src}
    return value


def style(ax):
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.xaxis.label.set_color(INK)
    ax.yaxis.label.set_color(INK)


def save(fig, out, name):
    os.makedirs(os.path.join(out, "figs"), exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(out, "figs", name + "." + ext), dpi=200, bbox_inches="tight")
    plt.close(fig)


def write_md(out, name, text):
    os.makedirs(os.path.join(out, "results"), exist_ok=True)
    with open(os.path.join(out, "results", name), "w", encoding="utf-8") as f:
        f.write(text)


# ---------------------------------------------------------------- E1
def e1(data, out):
    p = os.path.join(data, "e1_correctness.jsonl")
    if not os.path.exists(p):
        return
    rows = [r for r in load(p) if "rung" in r]
    cases = []
    for r in rows:
        if r["case"] not in cases:
            cases.append(r["case"])
    lines = ["| case | rung | status | files listed | output digest | leaked temp dirs |",
             "|---|---|---|---|---|---|"]
    for c in cases:
        for r in [x for x in rows if x["case"] == c]:
            lines.append("| %s | %s | %s | %d | `%s` | %d |" % (
                c, r["rung"], r["status"], r["filelist_n"], r["digest"], r["leaked_tmpdirs"]))
    extra = [r for r in load(p) if r.get("case") == "D_stale_txt_in_cwd" and "stale_txt_after" in r]
    if extra:
        lines.append("")
        lines.append("Case D, content of an unrelated `notes.txt` (`5\\n3\\n1\\n` before the run):")
        for r in extra:
            lines.append("- %s: `%s`" % (r["rung"], r["stale_txt_after"].replace("\n", "\\n")))
    write_md(out, "e1_correctness.md", "\n".join(lines) + "\n")
    by = {(r["case"], r["rung"]): r for r in rows}
    num("e1.queue10000.d8_wall_s", by[("E_queue_10000_files", "d8")]["wall_s"], "e1_correctness.jsonl")
    num("e1.queue10000.c_wall_s", by[("E_queue_10000_files", "c")]["wall_s"], "e1_correctness.jsonl")
    num("e1.queue10001.d8_status", by[("E_queue_10001_files", "d8")]["status"], "e1_correctness.jsonl")
    num("e1.tmpfs.d8_filelist_n", by[("C_tmpfs_no_fiemap", "d8")]["filelist_n"], "e1_correctness.jsonl")
    num("e1.tmpfs.a_filelist_n", by[("C_tmpfs_no_fiemap", "a")]["filelist_n"], "e1_correctness.jsonl")


# ---------------------------------------------------------------- E0
def e0(data, out):
    p = os.path.join(data, "e0_traces.jsonl")
    if not os.path.exists(p):
        return
    rows = load(p)
    full = {r["workload"]: r for r in rows if r.get("variant") == "unbuffered"}
    shipped = {r["workload"]: r for r in rows if r.get("variant") == "as_shipped"}
    # only these workloads issue the same reads on every run, so the difference between
    # the two captures is the tail lost by the shipped stop procedure
    deterministic = {"read_seq", "read_stride", "dd_hi"}

    def bcc_lost(r):
        n = 0
        for m in r.get("lost_msgs") or []:
            n += sum(int(t) for t in m.split() if t.isdigit())
        return n

    lines = ["| workload | L, unbuffered capture | L, as shipped | lines lost as shipped | "
             "samples BCC reports lost (unbuffered) | inodes in trace | of them on /mnt | "
             "O_DIRECT share | largest position recorded | runtime plain / traced (s) | parse.sh (s) |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for w, r in full.items():
        s = shipped.get(w)
        lost = (r["L"] - s["L"]) if (s and w in deterministic) else None
        lines.append("| %s | %d | %s | %s | %d | %d | %d | %.0f%% | %d | %.2f / %.2f | %.2f |" % (
            w, r["L"], s["L"] if s else "-",
            lost if lost is not None else "n/a (runs differ)", bcc_lost(r), r["F_unique"],
            r["F_resolving_on_mnt"], 100 * r["direct_frac"], r["max_pos"],
            r["t_plain_s"], r["t_traced_s"], r["t_parse_s"]))
        num("e0.%s.L" % w, r["L"], "e0_traces.jsonl (unbuffered)")
        num("e0.%s.F" % w, r["F_unique"], "e0_traces.jsonl (unbuffered)")
        num("e0.%s.F_on_mnt" % w, r["F_resolving_on_mnt"], "e0_traces.jsonl (unbuffered)")
        num("e0.%s.foreign_inodes" % w, r["F_unique"] - r["F_resolving_on_mnt"], "e0_traces.jsonl (unbuffered)")
        num("e0.%s.max_pos" % w, r["max_pos"], "e0_traces.jsonl (unbuffered)")
        num("e0.%s.trace_overhead_single_run" % w, r["t_traced_s"] / r["t_plain_s"], "e0_traces.jsonl (unbuffered)")
        num("e0.%s.bcc_lost_samples" % w, bcc_lost(r), "e0_traces.jsonl (unbuffered)")
        if lost is not None:
            num("e0.%s.lines_lost_as_shipped" % w, lost, "e0_traces.jsonl (both variants)")
        if s:
            num("e0.%s.fatal_as_shipped" % w, s.get("bcc_fatal_errors"), "e0_traces.jsonl")
    lines.append("")
    lines.append("One run of each capture per workload; the runtimes are single measurements.")
    write_md(out, "e0_traces.md", "\n".join(lines) + "\n")


# ---------------------------------------------------------------- E2
def e2(data, out, fname="e2_ladder.jsonl", tag="e2"):
    p = os.path.join(data, fname)
    if not os.path.exists(p):
        return
    rows = [r for r in load(p) if r.get("status") == "ok"]
    cells = collections.defaultdict(list)
    for r in rows:
        cells[(r["fs"], r["T"], r["F"], r["cache"], r.get("delay_ms"), r["rung"])].append(r["wall_s"])
    # table
    keys = sorted({k[:5] for k in cells}, key=lambda k: (k[0], str(k[3]), str(k[4]), k[1], k[2]))
    order = [rg for rg in RUNG_ORDER if any(k[5] == rg for k in cells)]  # columns with data
    lines = ["| fs | T | F | cache | delay | " + " | ".join(RUNG_LABEL.get(x, x) for x in order) + " |",
             "|---|---|---|---|---|" + "---|" * len(order)]
    for k in keys:
        vals = []
        for rg in order:
            x = cells.get(k + (rg,))
            vals.append("%.3g" % median_ci(x)[0] if x else "")
        lines.append("| %s | %d | %d | %s | %s | " % (k[0], k[1], k[2], k[3], k[4]) + " | ".join(vals) + " |")
    lines.append("")
    lines.append("Median wall time in seconds; 95% bootstrap intervals in numbers.json.")
    write_md(out, tag + "_ladder.md", "\n".join(lines) + "\n")
    for k in keys:
        base = cells.get(k + ("a",))
        for rg in RUNG_ORDER:
            x = cells.get(k + (rg,))
            if not x:
                continue
            key = "%s.%s.T%d.F%d.%s.%s.%s" % (tag, k[0], k[1], k[2], k[3], k[4], rg)
            m, lo, hi = median_ci(x)
            num(key + ".median_s", [m, lo, hi, len(x)], fname)
            if base and rg != "a":
                num(key + ".speedup_vs_a", list(ratio_ci(base, x)), fname)
            c = cells.get(k + ("c",))
            if c and rg.startswith("d"):
                num(key + ".slowdown_vs_c", list(ratio_ci(x, c)), fname)
            d = cells.get(k + ("d" + rg[1:],))
            if d and rg.startswith("m"):  # what the monitor thread costs: d<W> against m<W>
                num(key + ".d_over_m", list(ratio_ci(d, x)), fname)
                num(key + ".d_minus_m_s", median_ci(d)[0] - m, fname)
    for k in keys:  # a cold cell against the same warm cell
        kw = (k[0], k[1], k[2], "warm", k[4])
        if k[3] != "cold" or kw not in keys:
            continue
        for rg in order:
            xc, xw = cells.get(k + (rg,)), cells.get(kw + (rg,))
            if xc and xw:
                num("%s.%s.T%d.F%d.%s.cold_over_warm.%s" % (tag, k[0], k[1], k[2], k[4], rg),
                    list(ratio_ci(xc, xw)), fname)
    # upstream's cost per traced file against the tree size (warm, no delay, F = 1000),
    # with a least-squares fit cost = fixed + per_entry * T
    pts = []
    for k in keys:
        if k[2] == 1000 and k[3] == "warm" and k[4] is None and cells.get(k + ("a",)):
            ms = 1000.0 * median_ci(cells[k + ("a",)])[0] / k[2]
            pts.append((k[1], ms))
            num("%s.%s.T%d.upstream_ms_per_traced_file" % (tag, k[0], k[1]), ms, fname)
    if len(pts) >= 2:
        mt = sum(t for t, _ in pts) / len(pts)
        my = sum(y for _, y in pts) / len(pts)
        beta = sum((t - mt) * (y - my) for t, y in pts) / sum((t - mt) ** 2 for t, _ in pts)
        num("%s.upstream_fit.fixed_ms" % tag, my - beta * mt, fname)
        num("%s.upstream_fit.us_per_tree_entry" % tag, 1000.0 * beta, fname)
    # figure: wall time vs F for each (fs, T, cache, delay) group
    groups = sorted({(k[0], k[1], k[3], k[4]) for k in keys}, key=str)
    for g in groups:
        Fs = sorted({k[2] for k in keys if (k[0], k[1], k[3], k[4]) == g})
        if len(Fs) < 2:
            continue
        fig, ax = plt.subplots(figsize=(4.6, 3.2))
        for rg in RUNG_FIG:
            i = RUNG_STYLE[rg]
            xs, ms, los, his = [], [], [], []
            for F in Fs:
                x = cells.get((g[0], g[1], F, g[2], g[3], rg))
                if x:
                    m, lo, hi = median_ci(x)
                    xs.append(F); ms.append(m)
                    los.append(m - (lo if not math.isnan(lo) else m))
                    his.append((hi if not math.isnan(hi) else m) - m)
            if xs:
                ax.errorbar(xs, ms, yerr=[los, his], color=C[i], marker=MARK[i], ms=5,
                            lw=1.6, capsize=2, label=RUNG_LABEL.get(rg, rg))
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_xlabel("traced files F")
        ax.set_ylabel("analysis wall time (s)")
        style(ax)
        ax.legend(fontsize=6.5, frameon=False, loc="upper left")
        ax.set_title("%s, T = %d files, %s cache%s" % (g[0], g[1], g[2],
                     "" if g[3] is None else ", dm-delay %d ms" % g[3]), fontsize=8, color=INK)
        save(fig, out, "%s_vsF_%s_T%d_%s_%s" % (tag, g[0], g[1], g[2], g[3]))


# ---------------------------------------------------------------- E3
def e3(data, out):
    p = os.path.join(data, "e3_phase1.jsonl")
    if not os.path.exists(p):
        return
    rows = load(p)
    t = [r for r in rows if r.get("kind") == "time"]
    st = [r for r in rows if r.get("kind") == "strace"]
    cells = collections.defaultdict(list)
    for r in t:
        cells[(r["fs"], r["F"], r["L"], r["variant"])].append(r["wall_s"])
    fss = sorted({k[0] for k in cells}, key=lambda s: ["root", "ext4", "xfs", "btrfs", "f2fs"].index(s)
                 if s in ["root", "ext4", "xfs", "btrfs", "f2fs"] else 9)
    lines = ["| fs | F | L | upstream Phase 1 (s) | rewrite (s) | per line, upstream (us) | ratio |",
             "|---|---|---|---|---|---|---|"]
    for k in sorted({k[:3] for k in cells}, key=lambda k: (fss.index(k[0]), k[1], k[2])):
        up = cells.get(k + ("up_phase1",)); fa = cells.get(k + ("fast_phase1",))
        if not up or not fa:
            continue
        mu = median_ci(up); mf = median_ci(fa)
        lines.append("| %s | %d | %d | %.3g | %.3g | %.1f | %.1fx |" % (
            k[0], k[1], k[2], mu[0], mf[0], mu[0] / k[2] * 1e6, mu[0] / mf[0]))
        num("e3.%s.F%d.L%d.up" % k, list(mu), "e3_phase1.jsonl")
        num("e3.%s.F%d.L%d.fast" % k, list(mf), "e3_phase1.jsonl")
    for r in st:
        lines.append("")
        lines.append("strace -c -f of upstream Phase 1, F=%d, L=%d (%s): %s" % (
            r["F"], r["L"], r["fs"], ", ".join("%s=%d" % kv for kv in sorted(r["up_phase1"].items(), key=lambda kv: -kv[1])[:8])))
        num("e3.strace", r["up_phase1"], "e3_phase1.jsonl")
    write_md(out, "e3_phase1.md", "\n".join(lines) + "\n")
    for F in sorted({k[1] for k in cells}):
        fig, ax = plt.subplots(figsize=(4.6, 3.2))
        i = 0
        for fsn in fss:
            for v, ls in (("up_phase1", "-"), ("fast_phase1", ":")):
                Ls = sorted({k[2] for k in cells if k[0] == fsn and k[1] == F and k[3] == v})
                if not Ls:
                    continue
                ms = [median_ci(cells[(fsn, F, L, v)])[0] for L in Ls]
                ax.plot(Ls, ms, ls, color=C[i % 8], marker=MARK[i % 8], ms=4, lw=1.4,
                        label="%s, %s" % (fsn, "upstream" if v == "up_phase1" else "rewrite"))
            i += 1
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_xlabel("trace lines L"); ax.set_ylabel("Phase 1 wall time (s)")
        style(ax)
        ax.legend(fontsize=6, frameon=False, ncol=2)
        ax.set_title("Phase 1, F = %d traced files" % F, fontsize=8, color=INK)
        save(fig, out, "e3_phase1_F%d" % F)


# ---------------------------------------------------------------- E4
def e4(data, out):
    p = os.path.join(data, "e4_fiemap.jsonl")
    if not os.path.exists(p):
        return
    rows = load(p)
    lay = {(r["fs"], r["blocks"]): r for r in rows if r.get("kind") == "layout"}
    t = [r for r in rows if r.get("kind") == "time"]
    cells = collections.defaultdict(list)
    reads = collections.defaultdict(list)
    for r in t:
        k = (r["fs"], r["blocks"], r["cache"], r["threads"], r["order"])
        cells[k].append(r["per_file_us"])
        reads[k].append(r["reads_per_file"])
    lines = ["| fs | blocks/file | extents (median) | warm us/file | cold us/file | cold reads/file | "
             "cold random-order us/file | cold 16 threads us/file |", "|---|---|---|---|---|---|---|---|"]
    for (fsn, b), L in sorted(lay.items()):
        def g(cache, w, order):
            x = cells.get((fsn, b, cache, w, order))
            return median_ci(x)[0] if x else float("nan")
        rr = reads.get((fsn, b, "cold", 1, "creation"), [float("nan")])
        lines.append("| %s | %d | %d | %.1f | %.1f | %.3f | %.1f | %.1f |" % (
            fsn, b, L["extents_median"], g("warm", 1, "creation"), g("cold", 1, "creation"),
            sorted(rr)[len(rr) // 2], g("cold", 1, "random"), g("cold", 16, "creation")))
        num("e4.%s.b%d.warm_us" % (fsn, b), g("warm", 1, "creation"), "e4_fiemap.jsonl")
        num("e4.%s.b%d.cold_us" % (fsn, b), g("cold", 1, "creation"), "e4_fiemap.jsonl")
        num("e4.%s.b%d.cold_reads_per_file" % (fsn, b), sorted(rr)[len(rr) // 2], "e4_fiemap.jsonl")
        num("e4.%s.b%d.extents" % (fsn, b), L["extents_median"], "e4_fiemap.jsonl")
        num("e4.%s.b%d.cold16_us" % (fsn, b), g("cold", 16, "creation"), "e4_fiemap.jsonl")
        num("e4.%s.b%d.cold4_us" % (fsn, b), g("cold", 4, "creation"), "e4_fiemap.jsonl")
    write_md(out, "e4_fiemap.md", "\n".join(lines) + "\n")
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 3.0))
    for i, fsn in enumerate(sorted({k[0] for k in lay})):
        bs = sorted(b for (f, b) in lay if f == fsn)
        ex = [lay[(fsn, b)]["extents_median"] for b in bs]
        for ax, cache, ls in ((axs[0], "warm", "-"), (axs[1], "cold", "-")):
            ys = [median_ci(cells[(fsn, b, cache, 1, "creation")])[0] for b in bs]
            ax.plot(ex, ys, ls, color=C[i], marker=MARK[i], ms=4, lw=1.4, label=fsn)
    for ax, ttl in ((axs[0], "warm cache"), (axs[1], "cold cache (after remount)")):
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_xlabel("extents per file"); ax.set_ylabel("us per file (stat+open+FIEMAP+close)")
        ax.set_title(ttl, fontsize=8, color=INK)
        style(ax)
    axs[0].legend(fontsize=7, frameon=False)
    save(fig, out, "e4_fiemap")


# ---------------------------------------------------------------- E5
def e5(data, out):
    p = os.path.join(data, "e5_latency.jsonl")
    if not os.path.exists(p):
        return
    rows = load(p)
    cells = collections.defaultdict(list)
    io = collections.defaultdict(list)
    iokb = collections.defaultdict(list)
    for r in rows:
        k = (r["layout"], r["model"], r["delay_ms"], r["cache"], r["workers"])
        cells[k].append(r["wall_s"])
        if r.get("io"):
            io[k].append(r["io"].get("read_ios", 0))
            iokb[k].append(r["io"].get("read_sectors", 0) // 2)
    lines = ["| layout | model | delay (ms) | cache | sequential loop (s) | 1 thread | 4 | 8 | 16 | "
             "speedup 16 vs sequential | device reads (seq) |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    groups = sorted({k[:4] for k in cells}, key=lambda g: (g[0], g[1], g[2], g[3]))
    for g in groups:
        def m(w):
            x = cells.get(g + (w,))
            return median_ci(x)[0] if x else float("nan")
        s0 = cells.get(g + (0,)); s16 = cells.get(g + (16,))
        sp = ratio_ci(s0, s16) if s0 and s16 else (float("nan"),) * 3
        rd = io.get(g + (0,))
        lines.append("| %s | %s | %d | %s | %.3g | %.3g | %.3g | %.3g | %.3g | %.2f [%.2f, %.2f] | %s |" % (
            g[0], g[1], g[2], g[3], m(0), m(1), m(4), m(8), m(16), sp[0], sp[1], sp[2],
            ("%d" % sorted(rd)[len(rd) // 2]) if rd else "-"))
        num("e5.%s.%s.d%d.%s.speedup16" % g, list(sp), "e5_latency.jsonl")
        num("e5.%s.%s.d%d.%s.seq_s" % g, m(0), "e5_latency.jsonl")
    write_md(out, "e5_latency.md", "\n".join(lines) + "\n")
    # paper figure: absolute time against threads for one delay, both layouts
    series = [("sleep", "warm", "user-space sleep (fork's method)"),
              ("dmdelay", "cold", "dm-delay, cold cache"),
              ("qd1", "cold", "one request at a time, cold cache"),
              ("dmdelay", "warm", "dm-delay, warm cache")]
    xs_lab = ["seq", "1", "2", "4", "8", "16"]
    for d in sorted({g[2] for g in groups}):
        fig, axs = plt.subplots(1, 2, figsize=(7.2, 2.9), sharey=True)
        for ax, layout, ttl in ((axs[0], "together", "1,000 files created together"),
                                (axs[1], "scattered", "1,000 of 100,000 files")):
            for si, (model, cache, lab) in enumerate(series):
                g = (layout, model, d, cache)
                ys, lo, hi, xs = [], [], [], []
                for xi, w in enumerate((0, 1, 2, 4, 8, 16)):
                    x = cells.get(g + (w,))
                    if not x:
                        continue
                    mm, l_, h_ = median_ci(x)
                    xs.append(xi); ys.append(mm)
                    lo.append(mm - (l_ if not math.isnan(l_) else mm))
                    hi.append((h_ if not math.isnan(h_) else mm) - mm)
                if xs:
                    ax.errorbar(xs, ys, yerr=[lo, hi], color=C[si], marker=MARK[si], ms=5, lw=1.6,
                                capsize=2, label=lab)
                    kb = iokb.get(g + (0,))
                    if kb and model == "dmdelay" and cache == "cold":
                        v = sorted(kb)[len(kb) // 2]
                        ax.annotate("device read %s" % ("%d KiB" % v if v < 4096 else "%.1f MiB" % (v / 1024.0)),
                                    (xs[0], ys[0]), textcoords="offset points", xytext=(0, 8),
                                    fontsize=6.5, color=INK2)
            ax.set_xticks(range(6))
            ax.set_xticklabels(xs_lab)
            ax.set_yscale("log")
            ax.set_xlabel("threads", fontsize=8)
            ax.set_title(ttl, fontsize=8, color=INK)
            style(ax)
        axs[0].set_ylabel("wall time (s), median, 95% CI")
        h, l_ = axs[0].get_legend_handles_labels()
        fig.legend(h, l_, fontsize=7, frameon=False, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 0.0))
        fig.suptitle("Extent lookups of 1,000 traced files, delay %d ms" % d, fontsize=8.5, color=INK, y=1.02)
        save(fig, out, "e5_models_d%d" % d)
    for layout in sorted({g[0] for g in groups}):
        for d in sorted({g[2] for g in groups if g[0] == layout}):
            fig, ax = plt.subplots(figsize=(4.6, 3.2))
            i = 0
            for g in [g for g in groups if g[0] == layout and g[2] == d]:
                ws = sorted(w for (l, mo, dd, ca, w) in cells if (l, mo, dd, ca) == g and w > 0)
                s0 = cells.get(g + (0,))
                if not s0 or not ws:
                    continue
                ys = [ratio_ci(s0, cells[g + (w,)])[0] for w in ws]
                ax.plot(ws, ys, color=C[i % 8], marker=MARK[i % 8], ms=5, lw=1.6,
                        label="%s, %s cache" % (g[1], g[3]))
                i += 1
            ax.axhline(1.0, color=INK2, lw=0.8, ls="--")
            ax.set_xscale("log", base=2)
            ax.set_xlabel("threads"); ax.set_ylabel("speedup over the sequential loop")
            style(ax)
            ax.legend(fontsize=7, frameon=False)
            ax.set_title("%s files, delay %d ms" % (layout, d), fontsize=8, color=INK)
            save(fig, out, "e5_%s_d%d" % (layout, d))


def e2real(data, out):
    p = os.path.join(data, "e2_real.jsonl")
    if not os.path.exists(p):
        return
    rows = [r for r in load(p) if r.get("status") == "ok"]
    cells = collections.defaultdict(list)
    steps = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        k = (r["workload"], r["cache"], r["rung"])
        if r["rung"] == "pipe_a":
            tot = r["processing_s"] + r["merge_s"] + r["hotness_s"]
            cells[k].append(tot)
            for s in ("processing_s", "merge_s", "hotness_s"):
                steps[k[:2]][s].append(r[s])
        elif r["rung"] == "pipe_c":
            cells[k].append(r["total_s"])
        elif r["rung"] == "p1_a":
            cells[k].append(r["phase1_s"])
        else:
            cells[k].append(r["wall_s"])
    order = ["a", "p1_a", "b", "c", "d1", "d8", "d16", "e8", "pipe_a", "pipe_c"]
    wl = []
    for r in rows:
        if r["workload"] not in wl:
            wl.append(r["workload"])
    Ls = {r["workload"]: r["L"] for r in rows}
    lines = ["| workload | L | cache | " + " | ".join(RUNG_LABEL.get(x, {"pipe_a": "upstream pipeline",
             "pipe_c": "rewrite pipeline", "p1_a": "upstream Phase 1 only"}.get(x, x)) for x in order) + " |",
             "|---|---|---|" + "---|" * len(order)]
    for w in wl:
        for cache in ("warm", "cold"):
            vals = []
            for rg in order:
                x = cells.get((w, cache, rg))
                vals.append("%.3g" % median_ci(x)[0] if x else "")
            if any(vals):
                lines.append("| %s | %d | %s | " % (w, Ls[w], cache) + " | ".join(vals) + " |")
            for rg in order:
                x = cells.get((w, cache, rg))
                if not x:
                    continue
                num("e2real.%s.%s.%s.median_s" % (w, cache, rg), list(median_ci(x)) + [len(x)], "e2_real.jsonl")
                if rg != "a" and cells.get((w, cache, "a")) and not rg.startswith("pipe"):
                    num("e2real.%s.%s.%s.speedup_vs_a" % (w, cache, rg),
                        list(ratio_ci(cells[(w, cache, "a")], x)), "e2_real.jsonl")
            if cells.get((w, cache, "pipe_a")) and cells.get((w, cache, "pipe_c")):
                num("e2real.%s.%s.pipeline_speedup" % (w, cache),
                    list(ratio_ci(cells[(w, cache, "pipe_a")], cells[(w, cache, "pipe_c")])), "e2_real.jsonl")
            st = steps.get((w, cache))
            if st:
                for s, v in st.items():
                    num("e2real.%s.%s.pipe_a.%s" % (w, cache, s), median_ci(v)[0], "e2_real.jsonl")
    lines.append("")
    lines.append("Median wall time in seconds over the repetitions; upstream pipeline = processing.py + merge.py + hotness.sh 100.")
    write_md(out, "e2_real.md", "\n".join(lines) + "\n")
    # figure: where the upstream pipeline's time goes, per workload (warm cache)
    for cache in ("warm", "cold"):
        ws = [w for w in wl if steps.get((w, cache)) and cells.get((w, cache, "p1_a"))]
        if not ws:
            continue
        # left: share of the upstream pipeline's time by step (linear, sums to 100%);
        # right: total time, upstream pipeline vs rewrite (log scale, dots, no stacking)
        fig, (axl, axr) = plt.subplots(1, 2, figsize=(7.2, 0.5 + 0.42 * len(ws)),
                                       gridspec_kw={"width_ratios": [1.3, 1]}, sharey=True)
        parts = [("Phase 1: per-line append", C[0]), ("Phase 2: per-file find, sort, mv", C[1]),
                 ("merge.py", C[2]), ("hotness.sh", C[3])]
        y = list(range(len(ws)))
        for yi, w in zip(y, ws):
            st = steps[(w, cache)]
            proc = median_ci(st["processing_s"])[0]
            p1 = min(median_ci(cells[(w, cache, "p1_a")])[0], proc)
            vals = [p1, proc - p1, median_ci(st["merge_s"])[0], median_ci(st["hotness_s"])[0]]
            tot = sum(vals)
            left = 0.0
            for (lab, col), v in zip(parts, vals):
                axl.barh(yi, 100 * v / tot, left=left, height=0.6, color=col, edgecolor="white",
                         linewidth=1.5, label=lab if yi == 0 else None)
                left += 100 * v / tot
            num("e2real.%s.%s.breakdown" % (w, cache),
                dict(zip(["phase1", "phase2", "merge", "hotness"], vals)), "e2_real.jsonl")
            fast = median_ci(cells[(w, cache, "pipe_c")])[0] if cells.get((w, cache, "pipe_c")) else None
            axr.plot([tot], [yi], marker=MARK[0], color=C[0], ms=6, ls="none",
                     label="upstream pipeline" if yi == 0 else None)
            if fast is not None:
                axr.plot([fast], [yi], marker=MARK[1], color=C[1], ms=6, ls="none",
                         label="rewrite (one process)" if yi == 0 else None)
                axr.plot([fast, tot], [yi, yi], color=GRID, lw=1, zorder=0)
                axr.text(tot * 1.25, yi, "%.0fx" % (tot / fast), va="center", fontsize=7, color=INK2)
        axl.set_yticks(y)
        axl.set_yticklabels(["%s\n(L=%d)" % (w, Ls[w]) for w in ws], fontsize=7)
        axl.set_xlim(0, 100)
        axl.set_xlabel("share of upstream pipeline time (%)")
        axr.set_xscale("log")
        axr.set_xlabel("total time (s), median")
        for ax in (axl, axr):
            style(ax)
        axl.legend(fontsize=6, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.35), ncol=2)
        axr.legend(fontsize=6, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.35), ncol=2)
        save(fig, out, "e2real_breakdown_%s" % cache)


def e5b(data, out):
    p = os.path.join(data, "e5b_decompose.jsonl")
    if not os.path.exists(p):
        return
    rows = load(p)
    cells = collections.defaultdict(list)
    for r in rows:
        k = (r["layout"], r["model"], r["delay_ms"], r["measure"])
        cells[k + ("walk_s",)].append(r.get("walk_s"))
        cells[k + ("files_s",)].append(r.get("files_s"))
        cells[k + ("walk_reads",)].append((r.get("io_walk") or {}).get("read_ios"))
        cells[k + ("files_reads",)].append((r.get("io_files") or {}).get("read_ios"))

    def med(k):
        x = [v for v in cells.get(k, []) if v is not None]
        return median_ci(x) if x else (float("nan"),) * 3

    groups = sorted({k[:3] for k in cells})
    lines = ["| layout | model | delay (ms) | walk alone (s) | walk reads | after walk: lookups (s) | lookup reads | "
             "paths known, 1 thread (s) | 4 threads | 16 threads | reads, paths known | speedup 16 vs 1 |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for g in groups:
        w = med(g + ("walk", "walk_s")); wr = med(g + ("walk", "walk_reads"))
        f = med(g + ("walk+files", "files_s")); fr = med(g + ("walk+files", "files_reads"))
        t1 = cells.get(g + ("files-only/1", "files_s"), [])
        t4 = med(g + ("files-only/4", "files_s"))
        t16 = cells.get(g + ("files-only/16", "files_s"), [])
        rr = med(g + ("files-only/1", "files_reads"))
        sp = ratio_ci(t1, t16) if t1 and t16 else (float("nan"),) * 3
        lines.append("| %s | %s | %d | %.3f | %.0f | %.3f | %.0f | %.3f | %.3f | %.3f | %.0f | %.2f [%.2f, %.2f] |" % (
            g[0], g[1], g[2], w[0], wr[0], f[0], fr[0], median_ci(t1)[0] if t1 else float("nan"),
            t4[0], median_ci(t16)[0] if t16 else float("nan"), rr[0], sp[0], sp[1], sp[2]))
        key = "e5b.%s.%s.d%d" % g
        num(key + ".walk_s", list(w), "e5b_decompose.jsonl")
        num(key + ".walk_reads", wr[0], "e5b_decompose.jsonl")
        num(key + ".lookups_after_walk_s", list(f), "e5b_decompose.jsonl")
        num(key + ".lookup_reads_after_walk", fr[0], "e5b_decompose.jsonl")
        num(key + ".paths_known_reads", rr[0], "e5b_decompose.jsonl")
        num(key + ".paths_known_speedup16", list(sp), "e5b_decompose.jsonl")
    write_md(out, "e5b_decompose.md", "\n".join(lines) + "\n")


def e7(data, out):
    p = os.path.join(data, "e7_calibrate.jsonl")
    if not os.path.exists(p):
        return
    rows = load(p)
    lines = ["| pass | iodepth | IOPS | mean latency (us) | p50 (us) | p99 (us) |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %d | %.0f | %.1f | %.1f | %.1f |" % (
            r["pass"], r["iodepth"], r["iops"], r["lat_mean_us"], r["clat_p50_us"], r["clat_p99_us"]))
        num("e7.%s.qd%d.p50_us" % (r["pass"], r["iodepth"]), r["clat_p50_us"], "e7_calibrate.jsonl")
        num("e7.%s.qd%d.iops" % (r["pass"], r["iodepth"]), r["iops"], "e7_calibrate.jsonl")
    write_md(out, "e7_calibrate.md", "\n".join(lines) + "\n")


def e7b(data, out):
    p = os.path.join(data, "e7b_delay.jsonl")
    if not os.path.exists(p):
        return
    rows = load(p)
    base = {r["iodepth"]: r["lat_mean_ms"] for r in rows if r["model"] == "loop"}
    lines = ["| model | configured delay (ms) | QD1 mean latency (ms) | effective delay (ms) | "
             "QD16 IOPS | requests in flight at QD16 |", "|---|---|---|---|---|---|"]
    by = {}
    for r in rows:
        by[(r["model"], r["delay_ms"], r["iodepth"])] = r
    for (m, d, qd), r in sorted(by.items()):
        if qd != 1:
            continue
        r16 = by.get((m, d, 16))
        eff = r["lat_mean_ms"] - base.get(1, 0)
        inflight = r16["iops"] * r16["lat_mean_ms"] / 1000 if r16 else float("nan")
        lines.append("| %s | %d | %.3f | %.2f | %.0f | %.1f |" % (
            m, d, r["lat_mean_ms"], eff, r16["iops"] if r16 else float("nan"), inflight))
        num("e7b.%s.d%d.effective_ms" % (m, d), eff, "e7b_delay.jsonl")
        num("e7b.%s.d%d.inflight_qd16" % (m, d), inflight, "e7b_delay.jsonl")
    if rows:
        num("e7b.config_hz", rows[0]["config_hz"], "e7b_delay.jsonl")
    write_md(out, "e7b_delay.md", "\n".join(lines) + "\n")


def e8(data, out, fname="e8_gil.jsonl", tag="e8"):
    p = os.path.join(data, fname)
    if not os.path.exists(p):
        return
    rows = load(p)
    lay = [r for r in rows if r.get("kind") == "layout"]
    t = [r for r in rows if r.get("kind") == "time"]
    cells = collections.defaultdict(list)
    for r in t:
        cells[(r["device"], r["variant"], r["workers"])].append(r["wall_s"])
    devs = [d for d in ("plain", "dmdelay", "nbd_qd1", "nbd_par") if any(k[0] == d for k in cells)]
    variants = [v for v in ("fork", "big", "small", "big_mp", "fork_mp") if any(k[1] == v for k in cells)]
    vlab = {"fork": "fork engine's lookup, threads", "big": "1,824-byte request, threads",
            "small": "984-byte request, threads", "big_mp": "1,824-byte request, processes",
            "fork_mp": "fork's process engine"}
    lines = ["| device | variant | 1 worker (s) | 4 | 16 | speedup 16 vs 1 |", "|---|---|---|---|---|---|"]
    for dv in devs:
        for v in variants:
            x1 = cells.get((dv, v, 1)); x4 = cells.get((dv, v, 4)); x16 = cells.get((dv, v, 16))
            if not x1:
                continue
            sp = ratio_ci(x1, x16) if x16 else (float("nan"),) * 3
            lines.append("| %s | %s | %.3f | %.3f | %.3f | %.2f [%.2f, %.2f] |" % (
                dv, vlab[v], median_ci(x1)[0], median_ci(x4)[0] if x4 else float("nan"),
                median_ci(x16)[0] if x16 else float("nan"), sp[0], sp[1], sp[2]))
            num("%s.%s.%s.speedup16" % (tag, dv, v), list(sp), fname)
            num("%s.%s.%s.w1_s" % (tag, dv, v), median_ci(x1)[0], fname)
    if lay:
        L0 = lay[-1]
        lines.append("")
        lines.append("%d files, %d extents each (min %d, max %d); request sizes %s bytes; "
                     "1,824- and 984-byte requests returned identical extents: %s; Python %s." % (
                         L0["N"], L0["extents_median"], L0["extents_min"], L0["extents_max"],
                         L0["req_bytes"], L0["big_small_identical"], L0["python"]))
        num(tag + ".layout", {k: L0[k] for k in ("N", "extents_median", "big_small_identical", "req_bytes", "python")},
            fname)
    write_md(out, tag + "_gil.md", "\n".join(lines) + "\n")
    if not devs:
        return
    fig, axs = plt.subplots(1, len(devs), figsize=(1.9 * len(devs) + 0.6, 2.8), sharey=True)
    if len(devs) == 1:
        axs = [axs]
    dlab = {"plain": "loop device, no delay", "dmdelay": "dm-delay", "nbd_qd1": "one request at a time",
            "nbd_par": "32 requests in flight"}
    for ax, dv in zip(axs, devs):
        for i, v in enumerate(variants):
            ws = sorted(w for (d_, v_, w) in cells if d_ == dv and v_ == v)
            x1 = cells.get((dv, v, 1))
            if not x1 or not ws:
                continue
            ys = [ratio_ci(x1, cells[(dv, v, w)])[0] for w in ws]
            ax.plot(ws, ys, color=C[i], marker=MARK[i], ms=5, lw=1.6, label=vlab[v])
        ax.axhline(1.0, color=INK2, lw=0.8, ls="--")
        ax.set_xscale("log", base=2)
        ax.set_xticks([1, 4, 16]); ax.set_xticklabels(["1", "4", "16"])
        ax.set_title(dlab.get(dv, dv), fontsize=7.5, color=INK)
        ax.set_xlabel("workers", fontsize=8)
        style(ax)
    axs[0].set_ylabel("speedup over 1 worker")
    h, l_ = axs[0].get_legend_handles_labels()
    fig.legend(h, l_, fontsize=6.5, frameon=False, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 0.0))
    save(fig, out, tag + "_gil")


# ---------------------------------------------------------------- exploratory (batch 4-5, E6)
def e9(data, out, fname="e9_calls.jsonl", tag="e9"):
    p = os.path.join(data, fname)
    if not os.path.exists(p):
        return
    rows = load(p)
    calls = ("stat", "open", "fiemap", "fiemap_eof", "close")
    cell = collections.defaultdict(lambda: collections.defaultdict(list))
    ext = {}
    for r in rows:
        if r.get("kind") == "layout":
            ext[(r["fs"], r["blocks"])] = r["extents_median"]
            continue
        k = (r["fs"], r["blocks"], r["cache"], r["threads"])
        for c in calls:
            v = r["calls"].get(c)
            if v:
                cell[k][c + ".us"].append(v["us_per_file"])
                cell[k][c + ".r"].append(v["read_ios"] / r["n"])
    lines = ["| fs | extents | cache | threads | " + " | ".join("%s us (reads/file)" % c for c in calls) + " |",
             "|---|---|---|---|" + "---|" * len(calls)]
    for k in sorted(cell):
        d = cell[k]
        lines.append("| %s | %s | %s | %d | " % (k[0], ext.get(k[:2], k[1]), k[2], k[3]) + " | ".join(
            "%.1f (%.2f)" % (median_ci(d[c + ".us"])[0], median_ci(d[c + ".r"])[0]) if d[c + ".us"] else ""
            for c in calls) + " |")
        for c in calls:
            if d[c + ".us"]:
                key = "%s.%s.b%d.%s.W%d.%s" % (tag, k[0], k[1], k[2], k[3], c)
                num(key + ".us_per_file", list(median_ci(d[c + ".us"])) + [len(d[c + ".us"])], fname)
                num(key + ".reads_per_file", median_ci(d[c + ".r"])[0], fname)
    for k in sorted(cell):
        if k[3] == 1:
            k16 = k[:3] + (16,)
            for c in ("stat", "fiemap"):
                if cell[k][c + ".us"] and cell.get(k16, {}).get(c + ".us"):
                    num("%s.%s.b%d.%s.%s.speedup16" % ((tag,) + k[:3] + (c,)),
                        list(ratio_ci(cell[k][c + ".us"], cell[k16][c + ".us"])), fname)
    lines.append("")
    lines.append("Per-call passes over all files (stat all, open all, FIEMAP all, close all); median of the "
                 "repetitions; fiemap_eof asks only up to the file size.")
    write_md(out, tag + "_calls.md", "\n".join(lines) + "\n")


def e9b(data, out):
    p = os.path.join(data, "e9b_f2fs_fiemap.jsonl")
    if not os.path.exists(p):
        return
    rows = load(p)
    cell = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        k = (r["blocks"], r["mode"])
        cell[k]["us"].append(r["us_per_call"])
        cell[k]["mb"].append(r["map_blocks_per_fiemap"])
    lines = ["| blocks | request | us per FIEMAP (with probes) | f2fs_map_blocks calls per FIEMAP |", "|---|---|---|---|"]
    for k in sorted(cell):
        m = median_ci(cell[k]["mb"])[0]
        lines.append("| %d | %s | %.0f | %.0f (min %.0f, max %.0f) |" % (
            k[0], k[1], median_ci(cell[k]["us"])[0], m, min(cell[k]["mb"]), max(cell[k]["mb"])))
        num("e9b.b%d.%s.map_blocks_per_fiemap" % k, [m, min(cell[k]["mb"]), max(cell[k]["mb"])], "e9b_f2fs_fiemap.jsonl")
    write_md(out, "e9b_f2fs.md", "\n".join(lines) + "\n")


def e10(data, out, fname="e10_walk.jsonl", tag="e10"):
    p = os.path.join(data, fname)
    if not os.path.exists(p):
        return
    rows = load(p)
    cell = collections.defaultdict(list)
    reads = collections.defaultdict(list)
    equal = collections.defaultdict(set)
    for r in rows:
        k = (r["model"], r["walker"])
        cell[k].append(r["wall_s"])
        reads[k].append(r["io"]["read_ios"])
        equal[k].add(bool(r["equal_to_find"]))
    walkers = [w for w in ("find", "scandir/1", "scandir/4", "scandir/16") if any(k[1] == w for k in cell)]
    models = [m for m in ("plain", "dmdelay", "qd1", "nbdpar") if any(k[0] == m for k in cell)]
    lines = ["| device | " + " | ".join(walkers) + " | reads | same map as find |", "|---|" + "---|" * (len(walkers) + 2)]
    for m in models:
        vals = []
        for w in walkers:
            x = cell.get((m, w))
            vals.append("%.3f" % median_ci(x)[0] if x else "")
            if x:
                num("%s.%s.%s.median_s" % (tag, m, w), list(median_ci(x)) + [len(x)], fname)
                num("%s.%s.%s.reads" % (tag, m, w), median_ci(reads[(m, w)])[0], fname)
                if w.startswith("scandir/") and w != "scandir/1" and cell.get((m, "scandir/1")):
                    num("%s.%s.%s.speedup_vs_1" % (tag, m, w), list(ratio_ci(cell[(m, "scandir/1")], x)), fname)
        rd = median_ci(reads[(m, walkers[0])])[0]
        eq = all(all(equal[(m, w)]) for w in walkers if (m, w) in equal)
        lines.append("| %s | " % m + " | ".join(vals) + " | %d | %s |" % (rd, eq))
    lines.append("")
    lines.append("Cold walk of the tree, wall time in seconds (median).")
    write_md(out, tag + "_walk.md", "\n".join(lines) + "\n")


def e11(data, out):
    p = os.path.join(data, "e11_readahead.jsonl")
    if not os.path.exists(p):
        return
    rows = load(p)
    cell = collections.defaultdict(list)
    reads = collections.defaultdict(list)
    kib = collections.defaultdict(list)
    for r in rows:
        k = (r["layout"], r["inode_readahead_blks"], r["measure"])
        cell[k].append(r["wall_s"])
        reads[k].append(r["io"]["read_ios"])
        kib[k].append(r["io"]["read_sectors"] / 2)
        if r.get("in_effect") != r["inode_readahead_blks"]:
            print("WARNING e11: requested %s, in effect %s" % (r["inode_readahead_blks"], r.get("in_effect")))
    lines = ["| layout | inode_readahead_blks | walk s (reads) | lookups, 1 thread s (reads, KiB) | 16 threads s | speedup |",
             "|---|---|---|---|---|---|"]
    for lay in ("together", "scattered"):
        for v in sorted({k[1] for k in cell if k[0] == lay}):
            w, f1, f16 = (cell.get((lay, v, m)) for m in ("walk", "files-only/1", "files-only/16"))
            if not (w and f1 and f16):
                continue
            sp = ratio_ci(f1, f16)
            lines.append("| %s | %d | %.3f (%d) | %.3f (%d, %.0f) | %.3f | %.2f |" % (
                lay, v, median_ci(w)[0], median_ci(reads[(lay, v, "walk")])[0], median_ci(f1)[0],
                median_ci(reads[(lay, v, "files-only/1")])[0], median_ci(kib[(lay, v, "files-only/1")])[0],
                median_ci(f16)[0], sp[0]))
            base = "e11.%s.ra%d" % (lay, v)
            num(base + ".walk_s", list(median_ci(w)), "e11_readahead.jsonl")
            num(base + ".walk_reads", median_ci(reads[(lay, v, "walk")])[0], "e11_readahead.jsonl")
            num(base + ".files1_s", list(median_ci(f1)), "e11_readahead.jsonl")
            num(base + ".files1_reads", median_ci(reads[(lay, v, "files-only/1")])[0], "e11_readahead.jsonl")
            num(base + ".files_speedup16", list(sp), "e11_readahead.jsonl")
    lines.append("")
    lines.append("dm-delay, 5 ms configured; cold before every measurement; medians.")
    write_md(out, "e11_readahead.md", "\n".join(lines) + "\n")


def e12(data, out, fname, tag):
    p = os.path.join(data, fname)
    if not os.path.exists(p):
        return
    rows = load(p)
    lines = ["| pass | threads | reads/s | mean ms | p50 ms | p99 ms |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %d | %.0f | %.1f | %.1f | %.1f |" % (
            r["pass"], r["threads"], r["iops"], r["lat_mean_ms"], r["lat_p50_ms"], r["lat_p99_ms"]))
        num("%s.%s.W%d" % (tag, r["pass"], r["threads"]),
            {k: r[k] for k in ("iops", "lat_mean_ms", "lat_p50_ms", "lat_p99_ms", "reads")}, fname)
    write_md(out, tag + ".md", "\n".join(lines) + "\n")


def e6_latency(data, out):
    """E5's engine on the E6 disk: sequential loop (workers 0) against 16 threads."""
    p = os.path.join(data, "e6_latency.jsonl")
    if not os.path.exists(p):
        return
    rows = [r for r in load(p) if r.get("model") == "plain"]
    cell = collections.defaultdict(list)
    reads = collections.defaultdict(list)
    for r in rows:
        k = (r["layout"], r["cache"], r["workers"])
        cell[k].append(r["wall_s"])
        reads[k].append((r.get("io") or {}).get("read_ios", 0))
    lines = ["| layout | cache | sequential s (reads) | 16 threads s | speedup |", "|---|---|---|---|---|"]
    for lay in ("together", "scattered"):
        for cache in ("cold", "warm"):
            s, t = cell.get((lay, cache, 0)), cell.get((lay, cache, 16))
            if not (s and t):
                continue
            sp = ratio_ci(s, t)
            lines.append("| %s | %s | %.3f (%d) | %.3f | %.2f [%.2f, %.2f] |" % (
                lay, cache, median_ci(s)[0], median_ci(reads[(lay, cache, 0)])[0], median_ci(t)[0], *sp))
            num("e6lat.%s.%s.seq_s" % (lay, cache), list(median_ci(s)) + [len(s)], "e6_latency.jsonl")
            num("e6lat.%s.%s.speedup16" % (lay, cache), list(sp), "e6_latency.jsonl")
            num("e6lat.%s.%s.seq_reads" % (lay, cache), median_ci(reads[(lay, cache, 0)])[0], "e6_latency.jsonl")
    write_md(out, "e6_latency.md", "\n".join(lines) + "\n")


def gil_by_python(out):
    """The 16-worker speedups of E8 for each interpreter and device (from NUMBERS)."""
    tags = [("e8", "3.12"), ("e8py314", "3.14"), ("e8py314t", "3.14t (no GIL)"), ("e6gil", "3.14, real disk")]
    devs = [("plain", "loop, no delay"), ("dmdelay", "dm-delay"), ("nbd_qd1", "one at a time"),
            ("nbd_par", "32 in flight")]
    vars_ = [("fork", "fork lookup, thr."), ("big", "1,824\\,B, thr."), ("small", "984\\,B, thr."),
             ("big_mp", "1,824\\,B, proc.")]
    rows = []
    for tag, tlab in tags:
        for dv, dlab in devs:
            vals = [NUMBERS.get("%s.%s.%s.speedup16" % (tag, dv, v), {}).get("value") for v, _ in vars_]
            if any(vals):
                rows.append((tlab, "real disk" if tag == "e6gil" else dlab, vals))
    if not rows:
        return
    L = ["\\begin{tabular}{@{}ll" + "r" * len(vars_) + "@{}}", "\\toprule",
         "Python & device & " + " & ".join(l for _, l in vars_) + " \\\\", "\\midrule"]
    last = None
    for tlab, dlab, vals in rows:
        if last is not None and tlab != last:
            L.append("\\midrule")
        L.append("%s & %s & " % (tlab if tlab != last else "", dlab) +
                 " & ".join(("%.2f$\\times$" % v[0]) if v else "--" for v in vals) + " \\\\")
        last = tlab
    L += ["\\bottomrule", "\\end{tabular}"]
    os.makedirs(os.path.join(out, "results"), exist_ok=True)
    with open(os.path.join(out, "results", "tab_gilpy.tex"), "w") as f:
        f.write("\n".join(L) + "\n")


def tex_tables(out):
    """LaTeX tables for the paper, filled from NUMBERS only (so every cell traces back
    to numbers.json and from there to a raw file)."""
    def g(k, i=0):
        v = NUMBERS.get(k, {}).get("value")
        if v is None:
            return None
        return v[i] if isinstance(v, list) else v

    def fmt(x, prec=2):
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return "--"
        if x >= 100:
            return "%.0f" % x
        if x >= 10:
            return "%.1f" % x
        return ("%." + str(prec) + "f") % x

    # Table: real traces, warm cache
    wl = ["read_seq", "read_stride", "tar", "fio", "sqlite3"]
    rows = []
    for w in wl:
        a = g("e2real.%s.warm.a.median_s" % w)
        if a is None:
            continue
        c = g("e2real.%s.warm.c.median_s" % w)
        best_d = None
        for d in ("d1", "d8", "d16"):
            x = g("e2real.%s.warm.%s.median_s" % (w, d))
            if x is not None and (best_d is None or x < best_d[1]):
                best_d = (d, x)
        pa = g("e2real.%s.warm.pipe_a.median_s" % w)
        pc = g("e2real.%s.warm.pipe_c.median_s" % w)
        rows.append("%s & %s & %s & %s & %s (%s) & %s & %s \\\\" % (
            w.replace("_", "\\_"), "{:,}".format(int(g("e0.%s.L" % w) or 0)),
            "{:,}".format(int(g("e0.%s.F_on_mnt" % w) or 0)), fmt(a), fmt(best_d[1]) if best_d else "--",
            best_d[0][1:] if best_d else "", fmt(c), "%s / %s" % (fmt(pa), fmt(pc))))
    if rows:
        tex = ["\\begin{tabular}{@{}lrrrrrr@{}}", "\\toprule",
               "trace & $L$ & $F$ & (a) & best (d) (thr.) & (c) & pipeline (a)/(c) \\\\", "\\midrule"]
        tex += rows + ["\\bottomrule", "\\end{tabular}"]
        write_md(out, "tab_real.tex", "\n".join(tex) + "\n")

    # Table: decomposition of cold runs (E5b)
    rows = []
    for layout in ("together", "scattered"):
        for model, ml in (("plain", "loop"), ("dmdelay", "dm-delay"), ("qd1", "one at a time")):
            for d in (0, 5):
                k = "e5b.%s.%s.d%d" % (layout, model, d)
                w = g(k + ".walk_s")
                if w is None:
                    continue
                sp = g(k + ".paths_known_speedup16")
                rows.append("%s & %s & %s (%s) & %s (%s) & %s \\\\" % (
                    layout, ml, fmt(w, 3), "%.0f" % (g(k + ".walk_reads") or 0),
                    fmt(g(k + ".lookups_after_walk_s"), 3),
                    "%.0f" % (g(k + ".lookup_reads_after_walk") or 0),
                    ("%s$\\times$" % fmt(sp)) if sp else "--"))
    if rows:
        tex = ["\\begin{tabular}{@{}llrrr@{}}", "\\toprule",
               "files & device & walk, s (reads) & lookups after walk, s (reads) & paths known: 16 vs 1 thr. \\\\",
               "\\midrule"] + rows + ["\\bottomrule", "\\end{tabular}"]
        write_md(out, "tab_decompose.tex", "\n".join(tex) + "\n")

    # Table: GIL x device (E8)
    devs = [("plain", "loop, no delay"), ("dmdelay", "dm-delay"), ("nbd_qd1", "one request at a time"),
            ("nbd_par", "32 in flight")]
    vars_ = [("fork", "fork lookup, threads"), ("big", "1,824\\,B, threads"), ("small", "984\\,B, threads"),
             ("big_mp", "1,824\\,B, processes"), ("fork_mp", "fork process engine")]
    rows = []
    for dv, dl in devs:
        cells_ = []
        for v, _ in vars_:
            sp = NUMBERS.get("e8.%s.%s.speedup16" % (dv, v), {}).get("value")
            cells_.append("--" if sp is None else "%s$\\times$" % fmt(sp[0]))
        if any(c != "--" for c in cells_):
            w1 = g("e8.%s.fork.w1_s" % dv)
            rows.append("%s & %s & %s \\\\" % (dl, fmt(w1, 3), " & ".join(cells_)))
    if rows:
        tex = ["\\begin{tabular}{@{}lrrrrrr@{}}", "\\toprule",
               "device & 1 thr. (s) & " + " & ".join(l for _, l in vars_) + " \\\\", "\\midrule"]
        tex += rows + ["\\bottomrule", "\\end{tabular}"]
        write_md(out, "tab_gil.tex", "\n".join(tex) + "\n")

    # Table: extent lookup cost (E4)
    rows = []
    for fsn in ("ext4", "xfs", "btrfs", "f2fs"):
        lab = fsn
        for b in (1, 4, 8, 32, 128, 512):
            ext = g("e4.%s.b%d.extents" % (fsn, b))
            if ext is None:
                continue
            w = g("e4.%s.b%d.warm_us" % (fsn, b)); c_ = g("e4.%s.b%d.cold_us" % (fsn, b))
            r = g("e4.%s.b%d.cold_reads_per_file" % (fsn, b)); t16 = g("e4.%s.b%d.cold16_us" % (fsn, b))
            rows.append("%s & %d & %s & %s & %s & %s \\\\" % (lab, ext, fmt(w, 1), fmt(c_, 1),
                        "%.2f" % r if r is not None else "--", fmt(t16, 1)))
            lab = ""
        rows.append("\\midrule")
    if rows:
        rows = rows[:-1]
        tex = ["\\begin{tabular}{@{}lrrrrr@{}}", "\\toprule",
               "fs & extents & warm (\\textmu s) & cold (\\textmu s) & cold reads & cold, 16 thr. (\\textmu s) \\\\",
               "\\midrule"] + rows + ["\\bottomrule", "\\end{tabular}"]
        write_md(out, "tab_fiemap.tex", "\n".join(tex) + "\n")

    # Table: delay models (E5): speedup of 16 threads (sequential loop time)
    models = [("sleep", "warm", "sleep (user space)"), ("dmdelay", "cold", "dm-delay, cold"),
              ("qd1", "cold", "one at a time, cold"), ("dmdelay", "warm", "dm-delay, warm")]
    rows = []
    for layout in ("together", "scattered"):
        lab = layout
        for model, cache, mlab in models:
            cells_ = []
            for d in (1, 5, 10):
                spv = NUMBERS.get("e5.%s.%s.d%d.%s.speedup16" % (layout, model, d, cache), {}).get("value")
                sq = g("e5.%s.%s.d%d.%s.seq_s" % (layout, model, d, cache))
                cells_.append("--" if spv is None else "%s$\\times$ (%s\\,s)" % (fmt(spv[0]), fmt(sq, 3)))
            rows.append("%s & %s & %s \\\\" % (lab, mlab, " & ".join(cells_)))
            lab = ""
    if any("$" in r for r in rows):
        tex = ["\\begin{tabular}{@{}llrrr@{}}", "\\toprule",
               "files & model & 1\\,ms & 5\\,ms & 10\\,ms \\\\", "\\midrule"]
        tex += rows[:4] + ["\\midrule"] + rows[4:] + ["\\bottomrule", "\\end{tabular}"]
        write_md(out, "tab_models.tex", "\n".join(tex) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "..", "data"))
    ap.add_argument("--out", default=os.path.join(HERE, ".."))
    a = ap.parse_args()
    exf = os.path.join(a.data, "EXCLUDE.json")
    if os.path.exists(exf):
        EXCLUDE.update(json.load(open(exf)))
    for f in (e1, e0, e2, e2real, e3, e4, e5, e5b, e7, e7b, e8):
        f(a.data, a.out)
    e2(a.data, a.out, "e2_delay.jsonl", "e2delay")
    e2(a.data, a.out, "e2_monitor.jsonl", "e2monitor")
    # exploratory (batch 4 and 5, and E6 on the shared host)
    for f in (e9, e9b, e10, e11):
        f(a.data, a.out)
    e8(a.data, a.out, "e8_gil_py314.jsonl", "e8py314")
    e8(a.data, a.out, "e8_gil_py314t.jsonl", "e8py314t")
    e8(a.data, a.out, "e6_gil.jsonl", "e6gil")
    e9(a.data, a.out, "e6_calls.jsonl", "e6calls")
    e10(a.data, a.out, "e6_walk.jsonl", "e6walk")
    e12(a.data, a.out, "e6_device.jsonl", "e6dev")
    e12(a.data, a.out, "e6_device_after.jsonl", "e6dev_after")
    e6_latency(a.data, a.out)
    e2(a.data, a.out, "e6_ladder.jsonl", "e6ladder")
    gil_by_python(a.out)
    tex_tables(a.out)
    os.makedirs(os.path.join(a.out, "results"), exist_ok=True)
    with open(os.path.join(a.out, "results", "numbers.json"), "w") as f:
        json.dump(NUMBERS, f, indent=1, sort_keys=True)
    print("wrote", len(NUMBERS), "numbers")


if __name__ == "__main__":
    main()
