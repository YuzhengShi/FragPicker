#!/bin/bash
# E7b: the delay and concurrency each slow-device model actually provides on this kernel.
# 4 KiB O_DIRECT random reads with fio at queue depth 1 and 16, on:
#   loop      the loop device (direct I/O) itself
#   dmdelay   dm-delay over the loop device (timers in jiffies; CONFIG_HZ recorded)
#   nbd_qd1   nbdkit file plugin + delay filter, 1 thread
#   nbd_par   nbdkit file plugin + delay filter, 32 threads
# Effective delay = mean latency at QD1 minus that of the loop device; requests in flight
# at QD16 = IOPS x mean latency.
set -euo pipefail
DATA=${FPSTUDY_DATA:-/root/fpstudy/data}
IMG=${FPSTUDY_IMG:-/root/fpstudy/img}/e7b.img
SOCK=/root/fpstudy/e7b.sock
truncate -s 1G $IMG
L=$(losetup -f --show --direct-io=on $IMG)
dd if=/dev/urandom of=$L bs=1M count=1024 oflag=direct status=none
HZ=$(zcat /proc/config.gz | grep -E '^CONFIG_HZ=' | cut -d= -f2)
measure() {  # model delay device
  for qd in 1 16; do
    fio --name=lat --filename=$3 --rw=randread --bs=4k --direct=1 --ioengine=libaio --iodepth=$qd \
        --runtime=6 --time_based --randrepeat=1 --output-format=json > /root/fpstudy/e7b.json
    python3 - "$1" "$2" "$qd" "$HZ" >> $DATA/e7b_delay.jsonl <<'PY'
import json, sys
j = json.load(open("/root/fpstudy/e7b.json"))["jobs"][0]["read"]
p = j["clat_ns"]["percentile"]
print(json.dumps({"exp": "e7b", "model": sys.argv[1], "delay_ms": int(sys.argv[2]),
                  "iodepth": int(sys.argv[3]), "config_hz": int(sys.argv[4]),
                  "lat_mean_ms": j["lat_ns"]["mean"] / 1e6, "p50_ms": p["50.000000"] / 1e6,
                  "p99_ms": p["99.000000"] / 1e6, "iops": j["iops"], "ios": j["total_ios"]}))
PY
    tail -1 $DATA/e7b_delay.jsonl
  done
}
measure loop 0 $L
N=$(blockdev --getsz $L)
for d in 1 5 10; do
  dmsetup create e7bdelay --noudevsync --table "0 $N delay $L 0 $d"; dmsetup mknodes e7bdelay
  measure dmdelay $d /dev/mapper/e7bdelay
  dmsetup remove --noudevsync e7bdelay
done
losetup -d $L
for t in 1 32; do
  for d in 1 5 10; do
    rm -f $SOCK
    nbdkit -f -U $SOCK --filter=delay -t $t file $IMG rdelay=${d}ms wdelay=0 & pid=$!
    for i in $(seq 50); do [ -S $SOCK ] && break; sleep 0.1; done
    nbd-client -unix $SOCK /dev/nbd7 -connections 1 -block-size 4096 >/dev/null 2>&1
    blockdev --setra 256 /dev/nbd7
    if [ $t -eq 1 ]; then m=nbd_qd1; else m=nbd_par; fi
    measure $m $d /dev/nbd7
    nbd-client -d /dev/nbd7 >/dev/null 2>&1; kill $pid; wait $pid 2>/dev/null || true
  done
done
rm -f $IMG
