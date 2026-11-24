#!/bin/bash
# Remove leftovers of interrupted runs: dm-delay targets, loop devices, nbd clients.
for d in $(dmsetup ls 2>/dev/null | awk '/^fpdelay/{print $1}'); do dmsetup remove --noudevsync "$d" && echo "removed dm $d"; done
for n in /dev/nbd*; do nbd-client -c "$n" >/dev/null 2>&1 && nbd-client -d "$n" >/dev/null 2>&1 && echo "disconnected $n"; done
pkill -f "nbdkit .*fpstudy" 2>/dev/null
for l in $(losetup -a | grep fpstudy | cut -d: -f1); do losetup -d "$l" && echo "detached $l"; done
rm -f /root/fpstudy/img/e5_*.img /root/fpstudy/img/e2_*.img /root/fpstudy/img/e3_*.img /root/fpstudy/img/e4_*.img /root/fpstudy/img/e1*.img
losetup -a; dmsetup ls
