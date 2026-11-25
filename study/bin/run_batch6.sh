#!/bin/bash
# Batch 6 (2026-11-24, exploratory, on the owner's "三项都做"): the interpreter lock in depth.
#   E13  request size from 1 to 64 extents across the 1,024-byte threshold, with the
#        device's in-flight reads sampled from a separate process; 3.12 and 3.14
#   E14  starting `sort` processes from threads against worker processes; 3.12, 3.14, 3.14t
#   E2   one ladder cell (T=10,000, F=1,000, warm) under 3.14 and 3.14t
#   E9   per-call passes (ext4, F2FS) and E10 (threaded walk) under 3.14 and 3.14t
# 3.14/3.14t (deadsnakes 3.14.10) have no psutil build: study/lib/shims/psutil.py stands
# in for the fork's import-time calls (also in the rungs' processes, through
# FPSTUDY_EXTRA_PYTHONPATH); 3.14t also gets a directory with only a link to Debian's yaml.
set -u
R=/root/run_exp.sh
tr -d '\r' < /mnt/d/fragpicker-study/fork/study/bin/run_exp.sh > $R
log=/root/fpstudy/batch6.log
mkdir -p /root/fpstudy/py314t-extra
ln -sfn /usr/lib/python3/dist-packages/yaml /root/fpstudy/py314t-extra/yaml
SHIM=/root/fpstudy/code/study/lib/shims
X314=$SHIM:/root/fpstudy/py314t-extra
echo "batch6 start $(date -u +%FT%TZ)" >> $log
step() { echo "=== $(date -u +%FT%TZ) ${FPSTUDY_PYTHON:-python3} $*" >> $log; bash $R "$@" >> $log 2>&1; echo "=== rc=$? $(date -u +%FT%TZ)" >> $log; }
use() {  # use <python>: interpreter and import paths for the following steps
  export FPSTUDY_PYTHON=$1
  if [ "$1" = python3 ]; then unset PYTHONPATH FPSTUDY_EXTRA_PYTHONPATH
  else export PYTHONPATH=$X314 FPSTUDY_EXTRA_PYTHONPATH=$X314; fi
}
use python3
step e13_gil_boundary.py --reps 3 --out e13_boundary.jsonl
step e14_spawn.py --reps 3 --out e14_spawn.jsonl
use python3.14
step e13_gil_boundary.py --reps 3 --out e13_boundary_py314.jsonl
step e14_spawn.py --reps 3 --out e14_spawn_py314.jsonl
step e2_ladder.py --T 10000 --F 1000 --cache warm --rungs a,c,d1,d8,d16,m8 --reps 5 --budget-s 600 --out e2_ladder_py314.jsonl
step e9_calls.py --fs ext4,f2fs --reps 3 --out e9_calls_py314.jsonl
step e10_walk.py --reps 3 --out e10_walk_py314.jsonl
use python3.14t
step e14_spawn.py --reps 3 --out e14_spawn_py314t.jsonl
step e2_ladder.py --T 10000 --F 1000 --cache warm --rungs a,c,d1,d8,d16,m8 --reps 5 --budget-s 600 --out e2_ladder_py314t.jsonl
step e9_calls.py --fs ext4,f2fs --reps 3 --out e9_calls_py314t.jsonl
step e10_walk.py --reps 3 --out e10_walk_py314t.jsonl
echo "batch6 end $(date -u +%FT%TZ)" >> $log
