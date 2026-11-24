"""A minimal stand-in for psutil, for interpreters that have no psutil build: the
deadsnakes CPython 3.14 and free-threaded 3.14t used to re-run E8 (Debian's psutil is
built for the system's 3.12, and nothing else was installed).

The fork imports psutil in Config.auto_tune (cpu_count, virtual_memory), which every
import of its parallel package triggers, and in BackgroundMonitor (Process: cpu_percent
with an interval, memory_info, num_threads, io_counters), which E8 does not use. This
module provides exactly those, from /proc, with the same blocking behaviour
(cpu_percent(interval) sleeps for the interval). Selected by PYTHONPATH.
"""

import os
import time

__version__ = "study-shim"


def cpu_count(logical=True):
    n = os.cpu_count() or 1
    if logical:
        return n
    cores, phys, core = set(), None, None
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("physical id"):
                    phys = line.split(":", 1)[1].strip()
                elif line.startswith("core id"):
                    core = line.split(":", 1)[1].strip()
                elif not line.strip():
                    if core is not None:
                        cores.add((phys, core))
                    phys = core = None
    except OSError:
        return n
    return len(cores) or n


class _VirtualMemory:
    def __init__(self, total, available):
        self.total, self.available = total, available


def virtual_memory():
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":", 1)
            info[k] = int(v.split()[0]) * 1024
    return _VirtualMemory(info.get("MemTotal", 0), info.get("MemAvailable", info.get("MemFree", 0)))


class _MemInfo:
    def __init__(self, rss):
        self.rss = rss


class _IOCounters:
    def __init__(self, read_bytes, write_bytes):
        self.read_bytes, self.write_bytes = read_bytes, write_bytes


class Process:
    def __init__(self, pid=None):
        self.pid = pid or os.getpid()
        self._last = None

    def _cpu_seconds(self):
        with open("/proc/%d/stat" % self.pid) as f:
            fields = f.read().rsplit(")", 1)[1].split()
        return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")  # utime + stime

    def cpu_percent(self, interval=None):
        if interval:
            t0, c0 = time.monotonic(), self._cpu_seconds()
            time.sleep(interval)
            t1, c1 = time.monotonic(), self._cpu_seconds()
            return 100.0 * (c1 - c0) / max(t1 - t0, 1e-9)
        now = (time.monotonic(), self._cpu_seconds())
        prev, self._last = self._last, now
        if prev is None:
            return 0.0
        return 100.0 * (now[1] - prev[1]) / max(now[0] - prev[0], 1e-9)

    def memory_info(self):
        with open("/proc/%d/statm" % self.pid) as f:
            rss_pages = int(f.read().split()[1])
        return _MemInfo(rss_pages * os.sysconf("SC_PAGE_SIZE"))

    def num_threads(self):
        with open("/proc/%d/status" % self.pid) as f:
            for line in f:
                if line.startswith("Threads:"):
                    return int(line.split()[1])
        return 1

    def io_counters(self):
        r = w = 0
        with open("/proc/%d/io" % self.pid) as f:
            for line in f:
                k, v = line.split(":", 1)
                if k == "read_bytes":
                    r = int(v)
                elif k == "write_bytes":
                    w = int(v)
        return _IOCounters(r, w)
