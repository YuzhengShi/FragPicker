#!/bin/bash
# E7b: the delay dm-delay actually adds on this kernel (its timers run in jiffies).
# 4 KiB O_DIRECT random reads at queue depth 1 on a loop device, with and without a
# dm-delay layer of d ms; the difference of mean latencies is the effective delay.
set -euo pipefail
DATA=${FPSTUDY_DATA:-/root/fpstudy/data}
IMG=${FPSTUDY_IMG:-/root/fpstudy/img}/e7b.img
truncate -s 1G $IMG
L=$(losetup -f --show --direct-io=on $IMG)
dd if=/dev/urandom of=$L bs=1M count=1024 oflag=direct status=none
HZ=$(zcat /proc/config.gz | grep -E '^CONFIG_HZ=' | cut -d= -f2)
for d in 0 1 5 10; do
  dev=$L
  if [ $d -gt 0 ]; then
    N=$(blockdev --getsz $L)
    dmsetup create e7bdelay --noudevsync --table "0 $N delay $L 0 $d"; dmsetup mknodes e7bdelay
    dev=/dev/mapper/e7bdelay
  fi
  fio --name=lat --filename=$dev --rw=randread --bs=4k --direct=1 --ioengine=psync \
      --runtime=6 --time_based --randrepeat=1 --output-format=json > /root/fpstudy/e7b.json
  python3 - "$d" "$HZ" >> $DATA/e7b_dmdelay.jsonl <<'PY'
import json, sys
j = json.load(open("/root/fpstudy/e7b.json"))["jobs"][0]["read"]
p = j["clat_ns"]["percentile"]
print(json.dumps({"exp": "e7b", "delay_ms": int(sys.argv[1]), "config_hz": int(sys.argv[2]),
                  "lat_mean_ms": j["lat_ns"]["mean"] / 1e6, "p50_ms": p["50.000000"] / 1e6,
                  "p99_ms": p["99.000000"] / 1e6, "ios": j["total_ios"]}))
PY
  tail -1 $DATA/e7b_dmdelay.jsonl
  if [ $d -gt 0 ]; then dmsetup remove --noudevsync e7bdelay; fi
done
losetup -d $L; rm -f $IMG
