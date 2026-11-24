# An independent measurement study of FragPicker's analysis phase

This folder holds the scripts, raw data, figures and paper draft of a study of the
analysis phase of [FragPicker](https://github.com/jonggyup/FragPicker) (SOSP '21) and of
the `--parallel` mode added on the `parallel-analysis` branch of this fork.

It lives on the local branch `storage-study`; nothing here changes the code under test.
The code under test is exported from git (`upstream` at 796df86, this fork's
`parallel-analysis` at c162012) by `bin/sync_code.sh`.

## Layout

| Path | What it is |
|---|---|
| `lib/fpstudy/fastpath.py` | rung (c): single-threaded analysis, byte-identical to upstream `processing.py` (+ `merge.py`, `hotness.sh` with `--full`) |
| `lib/fpstudy/rungs.py` | runs each rung of the ablation ladder on one trace; timing, rusage, output digest |
| `lib/fpstudy/fsimg.py` | loop devices, mkfs, dm-delay, cache dropping, block-layer counters; real-device mode for E6 |
| `lib/fpstudy/corpus.py` | synthetic trees, fragmented files, synthetic traces in `parse.sh` format |
| `lib/fpstudy/stats.py` | medians, percentile-bootstrap intervals, intervals for ratios |
| `experiments/e0_traces.py` | real traces with upstream `trace.sh` (BCC), as shipped and unbuffered |
| `experiments/e1_correctness.py` | do the rungs produce the same output? |
| `experiments/e1b_artifact_scripts.sh` | do the fork's own benchmark scripts run? |
| `experiments/e2_ladder.py` | ablation ladder on synthetic traces (F, T, cache, dm-delay) |
| `experiments/e2_real.py` | ablation ladder and whole pipeline on E0's real traces |
| `experiments/e3_phase1.py` | Phase 1 cost against trace length, by file system |
| `experiments/e4_fiemap.py` | cost and device reads of one extent lookup, by file system and extent count |
| `experiments/e5_latency.py` | `time.sleep` vs dm-delay vs a one-request-at-a-time device |
| `analysis/report.py` | every table (`results/*.md`), figure (`figs/`) and quoted number (`results/numbers.json`) |
| `data/` | raw JSON lines, one per run, with commit hashes and kernel; `EXCLUDE.json` lists dropped rows and why |
| `paper/` | LaTeX source of the paper draft (`main.tex`) |

## Reproducing

Requirements: Linux with root (we used WSL2, kernel 6.18, Ubuntu 24.04), loop devices,
dm-delay, nbd, BCC, and: `apt install bpfcc-tools xfsprogs btrfs-progs f2fs-tools fio
sqlite3 nbdkit nbd-client strace python3-numpy python3-matplotlib python3-yaml python3-psutil`.
On WSL2, `ln -s /usr/sbin/trace-bpfcc /usr/share/bcc/tools/trace` (upstream's path).

Every experiment is started the same way (from Windows; on Linux drop the `wsl` prefix):

```bash
MSYS_NO_PATHCONV=1 wsl -d Ubuntu-24.04-D --exec bash /mnt/d/fragpicker-study/fork/study/bin/run_exp.sh e1_correctness.py
```

`run_exp.sh` exports the code under test to `/root/fpstudy/code`, points BCC at
extracted kernel headers (`bin/setup_bcc_headers.sh`), runs the experiment in a private
mount namespace with the file system under test at `/mnt` (upstream hard-codes `/mnt`;
WSL keeps the Windows drives under it), and copies the raw data back into `data/`.
`bin/run_batch1.sh` runs E2-E5 and E1b in sequence; `bin/cleanup_devices.sh` removes
loop, dm and nbd devices left by an interrupted run.

Then `python3 analysis/report.py` rebuilds `results/` and `figs/` from `data/`.

Real devices (E6): set `FPSTUDY_DEVICE=/dev/sdX` and
`FPSTUDY_DEVICE_CONFIRM=wipe-sdX`. The experiments then run `mkfs` on that device
instead of a loop image. **This destroys everything on it.**
