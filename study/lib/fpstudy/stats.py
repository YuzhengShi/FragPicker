"""Small statistics helpers: medians with percentile-bootstrap confidence intervals,
and bootstrap intervals for ratios of medians (speedups). Pure Python + numpy."""

import json
import numpy as np

RNG_SEED = 20261123


def load_jsonl(path):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def median_ci(x, conf=0.95, n_boot=10000, seed=RNG_SEED):
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return (float("nan"),) * 3
    med = float(np.median(x))
    if len(x) < 3:
        return med, float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n_boot, len(x)))
    boots = np.median(x[idx], axis=1)
    lo, hi = np.percentile(boots, [(1 - conf) / 2 * 100, (1 + conf) / 2 * 100])
    return med, float(lo), float(hi)


def ratio_ci(num, den, conf=0.95, n_boot=10000, seed=RNG_SEED):
    """median(num) / median(den) with an independent-resampling bootstrap interval.
    For speedup of B over A use ratio_ci(times_A, times_B)."""
    a = np.asarray(num, dtype=float)
    b = np.asarray(den, dtype=float)
    r = float(np.median(a) / np.median(b))
    if len(a) < 3 or len(b) < 3:
        return r, float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    ia = rng.integers(0, len(a), size=(n_boot, len(a)))
    ib = rng.integers(0, len(b), size=(n_boot, len(b)))
    boots = np.median(a[ia], axis=1) / np.median(b[ib], axis=1)
    lo, hi = np.percentile(boots, [(1 - conf) / 2 * 100, (1 + conf) / 2 * 100])
    return r, float(lo), float(hi)


def cv(x):
    x = np.asarray(x, dtype=float)
    return float(np.std(x, ddof=1) / np.mean(x)) if len(x) > 1 and np.mean(x) else float("nan")


def fmt_ci(t):
    m, lo, hi = t
    if np.isnan(lo):
        return "%.3g" % m
    return "%.3g [%.3g, %.3g]" % (m, lo, hi)
