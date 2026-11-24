#!/bin/bash
# Run a command as root in a private mount namespace, so that experiments can mount
# the file system under test at /mnt (which upstream FragPicker hard-codes) without
# touching WSL's own /mnt/c, /mnt/d, /mnt/wsl.
# A 9p (drvfs) directory is bind-mounted at /root/fpstudy/ns9p first, for E1 case C.
# Usage: run_in_ns.sh <command> [args...]
set -euo pipefail
NS9P_SRC=${NS9P_SRC:-/mnt/d/fragpicker-study/scratch9p}
mkdir -p /root/fpstudy/ns9p "$NS9P_SRC" 2>/dev/null || true
exec unshare -m --propagation private bash -c '
  set -e
  if [ -d "'"$NS9P_SRC"'" ]; then mount --bind "'"$NS9P_SRC"'" /root/fpstudy/ns9p; fi
  # hide WSL submounts under /mnt from find / os.walk: put an empty tmpfs over /mnt
  mount -t tmpfs -o size=1m nsroot /mnt
  exec "$@"
' bash "$@"
