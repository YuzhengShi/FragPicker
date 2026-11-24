#!/bin/bash
# Batch 2 (after batch 1). Order changed on 2026-11-24 so that the steps behind the paper's
# pending tables run first: E7b effective delays, E8 GIL x device concurrency, E5b
# decomposition. Batch 1's last four steps (e2 delay, T=1000, T=100000, e1b) were moved here
# with unchanged arguments; batch 1 skipped them through a temporary guard in /root/run_exp.sh,
# which the copy below replaces with the real runner. No step's arguments were changed.
set -u
R=/root/run_exp.sh
tr -d '\r' < /mnt/d/fragpicker-study/fork/study/bin/run_exp.sh > $R
log=/root/fpstudy/batch2.log
echo "batch2 start $(date -u +%FT%TZ)" >> $log
step() { echo "=== $(date -u +%FT%TZ) $*" >> $log; bash $R "$@" >> $log 2>&1; echo "=== rc=$? $(date -u +%FT%TZ)" >> $log; }
step e7b_dmdelay_effective.sh
step e8_gil.py --reps 5
step e5b_decompose.py --reps 5
# moved from batch 1
step e2_ladder.py --T 10000 --F 1000 --cache cold --delay-ms 5 --rungs a,c,d1,d8,d16,e8 --reps 5 --budget-s 900 --out e2_delay.jsonl
step e2_ladder.py --T 1000 --F 100,1000 --cache warm --reps 10 --budget-s 600
step e1b_artifact_scripts.sh
rm -f /root/fpstudy/data/e1c_anatomy.jsonl
step e1c_anatomy.sh
rm -f /root/fpstudy/data/e3_phase1_fs.jsonl
step e3_phase1.py --fs ext4,xfs,btrfs,f2fs --L 1000,10000,100000 --F 1,1000 --reps 10 --out e3_phase1_fs.jsonl
rm -f /root/fpstudy/data/e4_fiemap_f2fs.jsonl
step e4_fiemap.py --fs f2fs --reps 5 --out e4_fiemap_f2fs.jsonl
# moved from batch 1
step e2_ladder.py --T 100000 --F 100,1000 --cache warm --reps 10 --budget-s 900
step e7_calibrate.sh
echo "batch2 end $(date -u +%FT%TZ)" >> $log
