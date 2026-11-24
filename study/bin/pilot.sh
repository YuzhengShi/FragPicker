#!/bin/bash
# Quick smoke runs of E2-E5 with tiny parameters, written to pilot_*.jsonl, to catch
# bugs before the long batch. Not used in the paper.
set -u
R=/root/run_exp.sh
tr -d '\r' < /mnt/d/fragpicker-study/fork/study/bin/run_exp.sh > $R
bash $R e2_ladder.py --T 300 --F 10,100 --cache cold --reps 1 --rungs a,c,d4,e8 --out pilot_e2.jsonl 2>&1 | tail -4
bash $R e2_real.py --workloads read_stride --reps 1 --caches cold --out pilot_e2real.jsonl 2>&1 | tail -4
bash $R e3_phase1.py --fs root,xfs --L 1000,10000 --F 1 --reps 1 --out pilot_e3.jsonl 2>&1 | tail -3
bash $R e4_fiemap.py --fs ext4,btrfs --classes 1:50,32:20 --threads 1,4 --reps 1 --out pilot_e4.jsonl 2>&1 | tail -6
bash $R e5_latency.py --N 50 --delays 2 --workers 0,4 --reps 1 --out pilot_e5.jsonl 2>&1 | tail -8
