#!/bin/bash
# E1b: do the fork's own benchmark scripts run, and what do they print?
# Runs each script from the repository root of the code under test with a time limit
# and keeps its full output under $FPSTUDY_DATA/e1b/. Not timing-sensitive.
set -u
CODE=${FPSTUDY_CODE:-/root/fpstudy/code}
DATA=${FPSTUDY_DATA:-/root/fpstudy/data}
OUT=$DATA/e1b
mkdir -p "$OUT"
cd "$CODE/fork"
run() {  # name, timeout, command...
  local name=$1 t=$2; shift 2
  local start=$(date +%s.%N)
  timeout "$t" "$@" > "$OUT/$name.out" 2>&1
  local rc=$?
  local end=$(date +%s.%N)
  printf '{"exp":"e1b","script":"%s","rc":%d,"wall_s":%.2f,"cmd":"%s"}\n' \
    "$name" "$rc" "$(echo "$end - $start" | bc)" "$*" >> "$DATA/e1b_artifact_scripts.jsonl"
  echo "$name rc=$rc"; tail -3 "$OUT/$name.out"
}
run analyze_sh_syntax 10 bash -n src/analysis/analyze.sh
run overhead_profiling 900 python3 benchmarks/overhead_profiling_benchmark.py --files 200 --workers 8
run speedup_benchmark 900 python3 benchmarks/speedup_benchmark.py
run speedup_slow_io 1800 python3 benchmarks/speedup_slow_io_benchmark.py
ls /tmp | grep -c -E '^(fragpicker_sort_|sort_|tmp)' > "$OUT/tmp_leftovers.count" || true
