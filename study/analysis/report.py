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
}
RUNG_ORDER = ["a", "b", "c", "d1", "d4", "d8", "d16", "e8"]

NUMBERS = {}
EXCLUDE = {}


def load(path):
    """load_jsonl with the documented exclusions of study/data/EXCLUDE.json applied."""
    rows = load_jsonl(path)
    ex = EXCLUDE.get(os.path.basename(path))
    if ex and "ts_before" in ex:
        rows = [r for r in rows if r.get("ts") is None or r["ts"] >= ex["ts_before"]]
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
    lines = ["| workload | L (complete) | L as shipped (lost) | files in trace | of them on /mnt | "
             "read by workload | O_DIRECT share | max pos | runtime plain / traced (s) | parse.sh (s) |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for w, r in full.items():
        s = shipped.get(w)
        lost = r["L"] - s["L"] if s else None
        lines.append("| %s | %d | %s | %d | %d | %d | %.0f%% | %d | %.2f / %.2f | %.2f |" % (
            w, r["L"], ("%d (%d)" % (s["L"], lost)) if s else "-", r["F_unique"],
            r["F_resolving_on_mnt"], r["F_truth_seen"], 100 * r["direct_frac"], r["max_pos"],
            r["t_plain_s"], r["t_traced_s"], r["t_parse_s"]))
        num("e0.%s.L" % w, r["L"], "e0_traces.jsonl (unbuffered)")
        num("e0.%s.F" % w, r["F_unique"], "e0_traces.jsonl (unbuffered)")
        num("e0.%s.F_on_mnt" % w, r["F_resolving_on_mnt"], "e0_traces.jsonl (unbuffered)")
        num("e0.%s.max_pos" % w, r["max_pos"], "e0_traces.jsonl (unbuffered)")
        num("e0.%s.trace_overhead" % w, r["t_traced_s"] / r["t_plain_s"], "e0_traces.jsonl (unbuffered)")
        if s:
            num("e0.%s.lines_lost_as_shipped" % w, lost, "e0_traces.jsonl (both variants)")
            num("e0.%s.fatal_as_shipped" % w, s.get("bcc_fatal_errors"), "e0_traces.jsonl")
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
    lines = ["| fs | T | F | cache | delay | " + " | ".join(RUNG_LABEL.get(x, x) for x in RUNG_ORDER) + " |",
             "|---|---|---|---|---|" + "---|" * len(RUNG_ORDER)]
    for k in keys:
        vals = []
        for rg in RUNG_ORDER:
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
    # figure: wall time vs F for each (fs, T, cache, delay) group
    groups = sorted({(k[0], k[1], k[3], k[4]) for k in keys}, key=str)
    for g in groups:
        Fs = sorted({k[2] for k in keys if (k[0], k[1], k[3], k[4]) == g})
        if len(Fs) < 2:
            continue
        fig, ax = plt.subplots(figsize=(4.6, 3.2))
        for i, rg in enumerate(RUNG_ORDER):
            xs, ms, los, his = [], [], [], []
            for F in Fs:
                x = cells.get((g[0], g[1], F, g[2], g[3], rg))
                if x:
                    m, lo, hi = median_ci(x)
                    xs.append(F); ms.append(m)
                    los.append(m - (lo if not math.isnan(lo) else m))
                    his.append((hi if not math.isnan(hi) else m) - m)
            if xs:
                ax.errorbar(xs, ms, yerr=[los, his], color=C[i % 8], marker=MARK[i % 8], ms=5,
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
    for r in rows:
        k = (r["layout"], r["model"], r["delay_ms"], r["cache"], r["workers"])
        cells[k].append(r["wall_s"])
        if r.get("io"):
            io[k].append(r["io"].get("read_ios", 0))
    lines = ["| layout | model | delay (ms) | cache | sequential loop (s) | 1 thread | 4 | 8 | 16 | "
             "speedup 16 vs sequential | device reads (seq) |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    groups = sorted({k[:4] for k in cells}, key=str)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "..", "data"))
    ap.add_argument("--out", default=os.path.join(HERE, ".."))
    a = ap.parse_args()
    exf = os.path.join(a.data, "EXCLUDE.json")
    if os.path.exists(exf):
        EXCLUDE.update(json.load(open(exf)))
    for f in (e1, e0, e2, e2real, e3, e4, e5):
        f(a.data, a.out)
    e2(a.data, a.out, "e2_delay.jsonl", "e2delay")
    os.makedirs(os.path.join(a.out, "results"), exist_ok=True)
    with open(os.path.join(a.out, "results", "numbers.json"), "w") as f:
        json.dump(NUMBERS, f, indent=1, sort_keys=True)
    print("wrote", len(NUMBERS), "numbers")


if __name__ == "__main__":
    main()
