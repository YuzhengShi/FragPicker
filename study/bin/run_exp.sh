#!/bin/bash
# One entry point for every experiment, run from Windows as
#   MSYS_NO_PATHCONV=1 wsl -d Ubuntu-24.04-D --exec bash /mnt/d/fragpicker-study/fork/study/bin/run_exp.sh e2_ladder.py --T 10000 ...
# 1. copies the code under test and the study into /root/fpstudy/code (sync_code.sh)
# 2. exports BCC_KERNEL_SOURCE (setup_bcc_headers.sh)
# 3. runs the experiment inside a private mount namespace (run_in_ns.sh)
# 4. copies /root/fpstudy/data back into the repository (pull_data.sh)
set -euo pipefail
STUDY_D=/mnt/d/fragpicker-study
EXP=$1; shift
tr -d '\r' < "$STUDY_D/fork/study/bin/sync_code.sh" > /root/sync_code.sh
bash /root/sync_code.sh "$STUDY_D"
CODE=/root/fpstudy/code
source "$CODE/study/bin/setup_bcc_headers.sh"
mkdir -p /root/fpstudy/data /root/fpstudy/work /root/fpstudy/img
cd /root/fpstudy
case "$EXP" in
  *.py) bash "$CODE/study/bin/run_in_ns.sh" "${FPSTUDY_PYTHON:-python3}" "$CODE/study/experiments/$EXP" "$@" ;;
  *.sh) bash "$CODE/study/bin/run_in_ns.sh" bash "$CODE/study/experiments/$EXP" "$@" ;;
  *) echo "unknown experiment $EXP"; exit 2 ;;
esac
bash "$CODE/study/bin/pull_data.sh" "$STUDY_D/fork/study/data"
