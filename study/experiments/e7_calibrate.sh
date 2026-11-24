#!/bin/bash
# E7: what does a "cold" read cost on the loop devices used here? 4 KiB random O_DIRECT
# reads at queue depth 1 and 16 on a loop device (direct I/O) backed by a file on the
# WSL2 virtual disk: first over data written long enough ago to be out of the guest
# page cache, then again over the same offsets (host-cache effect), with fio.
# Writes $FPSTUDY_DATA/e7_calibrate.jsonl (fio JSON summaries).
set -euo pipefail
DATA=${FPSTUDY_DATA:-/root/fpstudy/data}
IMG=${FPSTUDY_IMG:-/root/fpstudy/img}/e7.img
M=/root/fpstudy/e7mnt
mkdir -p $M
truncate -s 9G $IMG
L=$(losetup -f --show --direct-io=on $IMG)
mkfs.ext4 -q -F $L
blockdev --setra 256 $L
mount $L $M
# 8 GiB of data, bigger than the guest's memory, so most of it is not in the guest cache
fio --name=fill --filename=$M/data --size=8g --rw=write --bs=1m --direct=1 --ioengine=psync --output-format=terse >/dev/null
sync; echo 3 > /proc/sys/vm/drop_caches
for pass in first second; do
  for qd in 1 16; do
    fio --name=rr --filename=$M/data --size=8g --rw=randread --bs=4k --direct=1 \
        --ioengine=libaio --iodepth=$qd --runtime=20 --time_based --randrepeat=1 \
        --randseed=42 --output-format=json > /root/fpstudy/e7.json
    python3 - "$pass" "$qd" >> $DATA/e7_calibrate.jsonl <<'PY'
import json, sys
j = json.load(open("/root/fpstudy/e7.json"))["jobs"][0]["read"]
pct = j["clat_ns"].get("percentile", {})
print(json.dumps({"exp": "e7", "pass": sys.argv[1], "iodepth": int(sys.argv[2]),
                  "iops": j["iops"], "lat_mean_us": j["lat_ns"]["mean"] / 1000,
                  "clat_p50_us": pct.get("50.000000", 0) / 1000,
                  "clat_p99_us": pct.get("99.000000", 0) / 1000}))
PY
    tail -1 $DATA/e7_calibrate.jsonl
  done
  sync; echo 3 > /proc/sys/vm/drop_caches
done
umount $M; losetup -d $L; rm -f $IMG
