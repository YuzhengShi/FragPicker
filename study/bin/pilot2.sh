#!/bin/bash
set -u
R=/root/run_exp.sh
tr -d '\r' < /mnt/d/fragpicker-study/fork/study/bin/run_exp.sh > $R
bash $R e5_latency.py --N 50 --delays 2 --workers 0,4 --reps 1 --out pilot_e5.jsonl 2>&1 | tail -12
bash $R e2_ladder.py --T 300 --F 100 --cache cold --delay-ms 2 --rungs a,c,d4 --reps 1 --out pilot_e2d.jsonl 2>&1 | tail -4
