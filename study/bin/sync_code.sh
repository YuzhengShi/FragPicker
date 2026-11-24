#!/bin/bash
# Copy the code under test into a WSL-native directory (experiments mount the test
# file system over /mnt inside a private mount namespace, which hides /mnt/d).
# upstream and fork are exported with `git archive` from their committed HEADs, so
# the bytes are exactly the committed ones (no CRLF from a Windows checkout).
# Usage: sync_code.sh [STUDY_ROOT_ON_D]   (default /mnt/d/fragpicker-study)
set -euo pipefail
SRC=${1:-/mnt/d/fragpicker-study}
DST=${FPSTUDY_CODE:-/root/fpstudy/code}
mkdir -p "$DST"
git config --global --add safe.directory '*' >/dev/null 2>&1 || true
for r in upstream fork; do
  rm -rf "$DST/$r"
  mkdir -p "$DST/$r"
  rev=$(git -C "$SRC/$r" rev-parse HEAD)
  # code under test: the fork at the tip of parallel-analysis, not storage-study
  if [ "$r" = fork ]; then rev=$(git -C "$SRC/$r" rev-parse parallel-analysis); fi
  git -C "$SRC/$r" -c core.autocrlf=false archive "$rev" | tar -x -C "$DST/$r"
  echo "$rev" > "$DST/$r.HEAD"
done
rm -rf "$DST/study"
mkdir -p "$DST/study"
(cd "$SRC/fork/study" && tar --exclude=./data --exclude=./figs --exclude='__pycache__' -cf - .) | tar -x -C "$DST/study"
find "$DST/study" -type f \( -name '*.sh' -o -name '*.py' \) -exec sed -i 's/\r$//' {} +
chmod +x "$DST"/upstream/src/analysis/*.sh "$DST"/fork/src/analysis/*.sh "$DST"/study/bin/*.sh 2>/dev/null || true
echo "synced: upstream $(cut -c1-7 "$DST/upstream.HEAD"), fork $(cut -c1-7 "$DST/fork.HEAD")"
