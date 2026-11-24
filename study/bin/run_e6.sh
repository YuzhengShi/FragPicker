#!/bin/bash
# E6 on a real block device (see study/E6_REAL_DEVICE.md). Requires root,
# FPSTUDY_DEVICE=/dev/sdX and FPSTUDY_DEVICE_CONFIRM=wipe-sdX. DESTROYS the device.
# Usage: sudo -E bash run_e6.sh /path/to/fragpicker-study
set -euo pipefail
ROOT=${1:?path to the folder holding upstream/ and fork/}
: "${FPSTUDY_DEVICE:?set FPSTUDY_DEVICE}"
[ "${FPSTUDY_DEVICE_CONFIRM:-}" = "wipe-$(basename "$FPSTUDY_DEVICE")" ] || { echo "confirm with FPSTUDY_DEVICE_CONFIRM=wipe-$(basename "$FPSTUDY_DEVICE")"; exit 2; }
if findmnt -S "$FPSTUDY_DEVICE" >/dev/null 2>&1; then echo "$FPSTUDY_DEVICE is mounted; refusing"; exit 2; fi
DEV=$(basename "$FPSTUDY_DEVICE")
echo "device $FPSTUDY_DEVICE: rotational=$(cat /sys/block/$DEV/queue/rotational 2>/dev/null) model=$(cat /sys/block/$DEV/device/model 2>/dev/null)"
export FPSTUDY_CODE=/root/fpstudy/code FPSTUDY_DATA=/root/fpstudy/data FPSTUDY_WORK=/root/fpstudy/work FPSTUDY_IMG=/root/fpstudy/img
mkdir -p $FPSTUDY_DATA $FPSTUDY_WORK $FPSTUDY_IMG
tr -d '\r' < "$ROOT/fork/study/bin/sync_code.sh" > /root/sync_code.sh
bash /root/sync_code.sh "$ROOT"
S=$FPSTUDY_CODE/study
ns() { bash $S/bin/run_in_ns.sh "$@"; }
{
  echo "e6 start $(date -u +%FT%TZ) $(uname -r) $FPSTUDY_DEVICE"
  cat /sys/block/$DEV/queue/{rotational,scheduler,nr_requests,max_sectors_kb} 2>/dev/null
} > $FPSTUDY_DATA/e6_device_info.txt
ns python3 $S/experiments/e4_fiemap.py --fs ext4,xfs --classes 1:1000,8:1000,128:300 --reps 5 --out e6_e4_fiemap.jsonl
ns python3 $S/experiments/e5_latency.py --models plain --delays 0 --reps 5 --out e6_e5_latency.jsonl
ns python3 $S/experiments/e2_ladder.py --T 10000 --F 100,1000 --cache cold --rungs a,c,d1,d8,d16 --reps 5 --out e6_e2_ladder.jsonl
mkdir -p "$ROOT/fork/study/data"
cp -r $FPSTUDY_DATA/e6_* "$ROOT/fork/study/data/"
echo "E6 done; results in $ROOT/fork/study/data/e6_*"
