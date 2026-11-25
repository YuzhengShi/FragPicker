#!/usr/bin/env python3
"""Sample a block device's in-flight read count from a separate process (so that the
measured interpreter's lock cannot stall the sampling) until SIGTERM, then print one
JSON line: number of samples, the maximum, the mean, and the share of samples with at
least 2 reads in flight. Usage: inflight_sampler.py /sys/block/dm-0/inflight [interval_s]
"""

import json
import signal
import sys
import time

path = sys.argv[1]
interval = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0005
stop = False


def on_term(signum, frame):
    global stop
    stop = True


signal.signal(signal.SIGTERM, on_term)
vals = []
with open(path) as f:
    print("ready", flush=True)  # the caller waits for this before it starts timing
    while not stop:
        f.seek(0)
        vals.append(int(f.read().split()[0]))
        time.sleep(interval)
busy = [v for v in vals if v > 0]
print(json.dumps({"samples": len(vals), "max": max(vals) if vals else 0,
                  "mean_busy": sum(busy) / len(busy) if busy else 0.0,
                  "share_ge2": sum(1 for v in vals if v >= 2) / len(vals) if vals else 0.0}))
