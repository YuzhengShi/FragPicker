#!/bin/bash
# WSL2's mounted linux-headers tree lacks include/linux/kconfig.h, so BCC falls back to
# the kheaders module, which it loads, extracts to /tmp and unloads on every start.
# upstream trace.sh starts two BCC tracers at once; they race on that and one of them
# fails to compile ("./include/linux/kconfig.h file not found"), silently losing all
# read (or write) events. Extract kheaders once and point BCC at it instead.
# Usage: source setup_bcc_headers.sh   (exports BCC_KERNEL_SOURCE)
set -e
K=$(uname -r)
DIR=/root/fpstudy/kheaders-$K
if [ ! -f "$DIR/include/linux/kconfig.h" ]; then
  modprobe kheaders
  mkdir -p "$DIR"
  tar -xf /sys/kernel/kheaders.tar.xz -C "$DIR"
  rmmod kheaders || true
fi
export BCC_KERNEL_SOURCE=$DIR
echo "BCC_KERNEL_SOURCE=$BCC_KERNEL_SOURCE"
