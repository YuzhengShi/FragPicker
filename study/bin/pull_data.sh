#!/bin/bash
# Copy raw results from the WSL working area back into the repository (study/data).
set -euo pipefail
SRC=${FPSTUDY_DATA:-/root/fpstudy/data}
DST=${1:-/mnt/d/fragpicker-study/fork/study/data}
mkdir -p "$DST"
cp -r "$SRC"/. "$DST"/
find "$DST" -name '*.bak' -delete
du -sh "$DST"
