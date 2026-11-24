#!/bin/bash
# Batch 2 (after batch 1): E7b effective delays, E8 GIL x device concurrency, E5b
# decomposition, E7 calibration of cold reads, E1c anatomy.
set -u
R=/root/run_exp.sh
tr -d '\r' < /mnt/d/fragpicker-study/fork/study/bin/run_exp.sh > $R
log=/root/fpstudy/batch2.log
echo "batch2 start $(date -u +%FT%TZ)" >> $log
step() { echo "=== $(date -u +%FT%TZ) $*" >> $log; bash $R "$@" >> $log 2>&1; echo "=== rc=$? $(date -u +%FT%TZ)" >> $log; }
step e7b_dmdelay_effective.sh
step e8_gil.py --reps 5
step e5b_decompose.py --reps 5
rm -f /root/fpstudy/data/e4_fiemap_f2fs.jsonl
step e4_fiemap.py --fs f2fs --reps 5 --out e4_fiemap_f2fs.jsonl
step e7_calibrate.sh
rm -f /root/fpstudy/data/e1c_anatomy.jsonl
step e1c_anatomy.sh
echo "batch2 end $(date -u +%FT%TZ)" >> $log
