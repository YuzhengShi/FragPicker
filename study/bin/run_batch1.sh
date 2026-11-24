#!/bin/bash
# Batch 1: every local (WSL) experiment after E0/E1, one after another so that no two
# measurements overlap. Run from Windows:
#   MSYS_NO_PATHCONV=1 wsl -d Ubuntu-24.04-D --exec bash /mnt/d/fragpicker-study/fork/study/bin/run_batch1.sh
set -u
R=/root/run_exp.sh
tr -d '\r' < /mnt/d/fragpicker-study/fork/study/bin/run_exp.sh > $R
log=/root/fpstudy/batch1.log
echo "batch1 start $(date -u +%FT%TZ)" >> $log
step() { echo "=== $(date -u +%FT%TZ) $*" >> $log; bash $R "$@" >> $log 2>&1; echo "=== rc=$? $(date -u +%FT%TZ)" >> $log; }
step e2_real.py --reps 10
step e2_ladder.py --T 10000 --F 1,10,100,1000,10000 --cache warm --reps 10
step e2_ladder.py --T 10000 --F 1,10,100,1000,10000 --cache cold --reps 10
step e2_ladder.py --T 1000 --F 100,1000 --cache warm --reps 10
step e2_ladder.py --T 100000 --F 100,1000 --cache warm --reps 10 --budget-s 1200
step e2_ladder.py --T 10000 --F 1000 --cache cold --delay-ms 5 --rungs a,c,d1,d8,d16,e8 --reps 5 --out e2_delay.jsonl
step e3_phase1.py --reps 10
step e4_fiemap.py --reps 5
step e5_latency.py --reps 5
step e1b_artifact_scripts.sh
echo "batch1 end $(date -u +%FT%TZ)" >> $log
