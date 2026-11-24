#!/bin/bash
# Batch 5 (2026-11-24, exploratory): E8 again under CPython 3.14 (whose fcntl.ioctl
# releases the GIL for large buffers, by our reading of the source) and the free-threaded
# 3.14t, both 3.14.10 from the deadsnakes PPA, installed for this with the owner's OK.
# Neither has a psutil build, so study/lib/shims/psutil.py stands in for the two calls the
# fork's config makes at import; 3.14t also does not see Debian's dist-packages, so a
# directory holding only a link to its pure-Python-capable yaml package is added.
set -u
R=/root/run_exp.sh
tr -d '\r' < /mnt/d/fragpicker-study/fork/study/bin/run_exp.sh > $R
log=/root/fpstudy/batch5.log
mkdir -p /root/fpstudy/py314t-extra
ln -sfn /usr/lib/python3/dist-packages/yaml /root/fpstudy/py314t-extra/yaml
SHIM=/root/fpstudy/code/study/lib/shims
echo "batch5 start $(date -u +%FT%TZ)" >> $log
step() { echo "=== $(date -u +%FT%TZ) $FPSTUDY_PYTHON $*" >> $log; bash $R "$@" >> $log 2>&1; echo "=== rc=$? $(date -u +%FT%TZ)" >> $log; }
export FPSTUDY_PYTHON=python3.14 PYTHONPATH=$SHIM
step e8_gil.py --reps 5 --out e8_gil_py314.jsonl
export FPSTUDY_PYTHON=python3.14t PYTHONPATH=$SHIM:/root/fpstudy/py314t-extra
step e8_gil.py --reps 5 --out e8_gil_py314t.jsonl
echo "batch5 end $(date -u +%FT%TZ)" >> $log
