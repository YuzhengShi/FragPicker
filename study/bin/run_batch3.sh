#!/bin/bash
# Batch 3 (after batch 2), added 2026-11-24:
#  1. rung m<W> (d<W> with the resource-monitor thread replaced by a no-op) next to d<W> and
#     c: how much of the parallel path's one-second floor the monitor thread causes;
#  2. the SQLite replay again. During batch 1 an external load on the host (16:05-16:15 UTC;
#     the study ran nothing else then) slowed every rung of that workload about 1.6x, as
#     analysis/perturb.py shows; the repeat replaces the workload's rows (data/EXCLUDE.json).
set -u
R=/root/run_exp.sh
tr -d '\r' < /mnt/d/fragpicker-study/fork/study/bin/run_exp.sh > $R
log=/root/fpstudy/batch3.log
echo "batch3 start $(date -u +%FT%TZ)" >> $log
step() { echo "=== $(date -u +%FT%TZ) $*" >> $log; bash $R "$@" >> $log 2>&1; echo "=== rc=$? $(date -u +%FT%TZ)" >> $log; }
step e2_ladder.py --T 10000 --F 1,100,1000 --cache warm --rungs c,d1,d8,m1,m8 --reps 10 --budget-s 600 --out e2_monitor.jsonl
step e2_real.py --workloads sqlite3 --reps 7 --out e2_real_sqlite3.jsonl
echo "batch3 end $(date -u +%FT%TZ)" >> $log
