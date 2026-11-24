#!/bin/bash
# E1c: process creations and system calls per traced file and per trace line, for each
# upstream analysis step, counted with strace on a small synthetic case.
# Writes $FPSTUDY_DATA/e1c_anatomy.jsonl. Run inside study/bin/run_in_ns.sh.
set -euo pipefail
CODE=${FPSTUDY_CODE:-/root/fpstudy/code}
DATA=${FPSTUDY_DATA:-/root/fpstudy/data}
W=/root/fpstudy/anat
NF=${NF:-50}; LPF=${LPF:-4}; T=${T:-200}
rm -rf $W; mkdir -p $W/tree $W/wd
cd $W/wd
python3 - <<PY
import sys
sys.path.insert(0, "$CODE/study/lib")
from fpstudy import corpus
files = corpus.make_tree("$W/tree", $T, per_dir=50, size=4096)
corpus.gen_trace("trace.result", [i for i, _ in files[:$NF]], $LPF)
PY
mount --bind $W/tree /mnt
L=$(wc -l < trace.result)
for step in processing merge hotness fastpath_full; do
  case $step in
    processing) cmd="python3 $CODE/upstream/src/analysis/processing.py";;
    merge) cmd="python3 $CODE/upstream/src/analysis/merge.py";;
    hotness) cmd="bash $CODE/upstream/src/analysis/hotness.sh 100";;
    fastpath_full) rm -f *.txt *.merged *.sorted; cmd="python3 $CODE/study/lib/fpstudy/fastpath.py --mount-point /mnt --full";;
  esac
  strace -f -qq -e trace=execve,clone,clone3,fork,vfork,openat,write,close -o st_$step.txt $cmd >/dev/null 2>&1
  ok_exec=$(grep 'execve(' st_$step.txt | grep -vc ' = -1 ' || true)
  clones=$(grep -cE 'clone3?\(|v?fork\(' st_$step.txt || true)
  opens=$(grep -c 'openat(' st_$step.txt || true)
  writes=$(grep -c 'write(' st_$step.txt || true)
  printf '{"exp":"e1c","step":"%s","traced_files":%d,"trace_lines":%d,"tree_files":%d,"processes_created":%d,"successful_execve":%d,"openat":%d,"write":%d}\n' \
    "$step" "$NF" "$L" "$T" "$clones" "$ok_exec" "$opens" "$writes" | tee -a "$DATA/e1c_anatomy.jsonl"
done
umount /mnt
