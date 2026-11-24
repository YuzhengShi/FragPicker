#!/bin/bash
# Batch 1: every local (WSL) experiment after E0/E1, one after another so that no two
# measurements overlap. Most important first. Run from Windows:
#   MSYS_NO_PATHCONV=1 wsl -d Ubuntu-24.04-D --exec bash /mnt/d/fragpicker-study/fork/study/bin/run_batch1.sh
set -u
R=/root/run_exp.sh
tr -d '\r' < /mnt/d/fragpicker-study/fork/study/bin/run_exp.sh > $R
log=/root/fpstudy/batch1.log
echo "batch1 start $(date -u +%FT%TZ)" >> $log
step() { echo "=== $(date -u +%FT%TZ) $*" >> $log; bash $R "$@" >> $log 2>&1; echo "=== rc=$? $(date -u +%FT%TZ)" >> $log; }
step e5_latency.py --reps 5
# The original run used the defaults (E4 on all four file systems, E3 on the root file
# system and four loop file systems up to 10^6 lines). Its F2FS rows of E4 and loop rows
# of E3 are excluded (data/EXCLUDE.json) and were re-measured in batch 2, so a re-run
# only needs these:
step e4_fiemap.py --fs ext4,xfs,btrfs --reps 5
step e3_phase1.py --fs root --reps 10
step e2_ladder.py --T 10000 --F 1,10,100,1000,10000 --cache warm --reps 10 --budget-s 600
step e2_real.py --reps 7
step e2_ladder.py --T 10000 --F 1,10,100,1000,10000 --cache cold --reps 10 --budget-s 600
# The last four steps of the original batch 1 (T=1000, T=100000, e2 under dm-delay, E1b)
# moved to run_batch2.sh on 2026-11-24 with unchanged arguments; in that run batch 1
# skipped them (its log says "skipped (moved to batch 2)").
echo "batch1 end $(date -u +%FT%TZ)" >> $log
