#!/bin/bash
# Batch 2 (after batch 1): E5b decomposition, E7 calibration of cold reads, E1c anatomy.
set -u
R=/root/run_exp.sh
tr -d '\r' < /mnt/d/fragpicker-study/fork/study/bin/run_exp.sh > $R
log=/root/fpstudy/batch2.log
echo "batch2 start $(date -u +%FT%TZ)" >> $log
step() { echo "=== $(date -u +%FT%TZ) $*" >> $log; bash $R "$@" >> $log 2>&1; echo "=== rc=$? $(date -u +%FT%TZ)" >> $log; }
step e5b_decompose.py --reps 5
step e7_calibrate.sh
rm -f /root/fpstudy/data/e1c_anatomy.jsonl
step e1c_anatomy.sh
echo "batch2 end $(date -u +%FT%TZ)" >> $log
