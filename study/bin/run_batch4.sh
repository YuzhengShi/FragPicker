#!/bin/bash
# Batch 4 (2026-11-24): exploratory experiments, designed after batches 1-3 had been seen
# and therefore not part of the pre-registered predictions:
#   E9   where an extent lookup's time and device reads go, call by call (stat, open,
#        FIEMAP, close), per file system, warm and cold, 1 and 16 threads
#   E9b  F2FS: how many f2fs_map_blocks calls one FIEMAP makes (BPF kprobe)
#   E10  a threaded os.scandir walk against the fork's find, per device model
#   E11  ext4 inode_readahead_blks against cold reads and thread gains
set -u
R=/root/run_exp.sh
tr -d '\r' < /mnt/d/fragpicker-study/fork/study/bin/run_exp.sh > $R
log=/root/fpstudy/batch4.log
echo "batch4 start $(date -u +%FT%TZ)" >> $log
step() { echo "=== $(date -u +%FT%TZ) $*" >> $log; bash $R "$@" >> $log 2>&1; echo "=== rc=$? $(date -u +%FT%TZ)" >> $log; }
step e9_calls.py --reps 5
step e9b_f2fs_fiemap.py --reps 5
step e10_walk.py --reps 5
step e11_readahead.py --reps 5
echo "batch4 end $(date -u +%FT%TZ)" >> $log
