"""Loop-device file systems, dm-delay, cache control and block-layer counters.

All functions shell out to standard tools (losetup, mkfs.*, mount, dmsetup) and
must run as root inside WSL2 (or any Linux box).
"""

import os
import subprocess
import time

MKFS = {
    # upstream evaluation/tools/mount.sh uses lazy_itable_init=0,lazy_journal_init=0 for ext4
    "ext4": ["mkfs.ext4", "-q", "-F", "-E", "lazy_itable_init=0,lazy_journal_init=0"],
    "xfs": ["mkfs.xfs", "-q", "-f"],
    "btrfs": ["mkfs.btrfs", "-q", "-f"],
    "f2fs": ["mkfs.f2fs", "-q", "-f"],
}


def sh(cmd, check=True, capture=True, **kw):
    r = subprocess.run(cmd, check=False, text=True,
                       stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.PIPE if capture else None, **kw)
    if check and r.returncode != 0:
        raise RuntimeError("command failed (%d): %s\n%s%s" % (
            r.returncode, " ".join(map(str, cmd)), r.stdout or "", r.stderr or ""))
    return r.stdout if capture else ""


def make_image(path, size_mb):
    """Sparse backing file."""
    with open(path, "wb") as f:
        f.truncate(size_mb * 1024 * 1024)


def losetup(path, direct_io=True):
    args = ["losetup", "-f", "--show"]
    if direct_io:
        args.append("--direct-io=on")
    return sh(args + [path]).strip()


def lodetach(dev):
    sh(["losetup", "-d", dev], check=False)


def mkfs(fstype, dev):
    sh(MKFS[fstype] + [dev])


def mount(dev, mnt, fstype, opts=None):
    os.makedirs(mnt, exist_ok=True)
    cmd = ["mount", "-t", fstype]
    if opts:
        cmd += ["-o", opts]
    sh(cmd + [dev, mnt])


def umount(mnt):
    sh(["umount", mnt], check=False)


def sectors(dev):
    return int(sh(["blockdev", "--getsz", dev]).strip())


def dm_delay_create(name, dev, read_ms, write_ms=None):
    """Create /dev/mapper/<name> that delays reads (and writes) by the given ms.

    Table (kernel docs admin-guide/device-mapper/delay):
      <start> <len> delay <dev> <offset> <read_ms> [<wdev> <woffset> <write_ms>]
    """
    n = sectors(dev)
    if write_ms is None:
        table = "0 %d delay %s 0 %d" % (n, dev, read_ms)
    else:
        table = "0 %d delay %s 0 %d %s 0 %d" % (n, dev, read_ms, dev, write_ms)
    sh(["dmsetup", "create", name, "--table", table])
    return "/dev/mapper/" + name


def dm_remove(name):
    sh(["dmsetup", "remove", "--retry", name], check=False)


def drop_caches():
    os.sync()
    with open("/proc/sys/vm/drop_caches", "w") as f:
        f.write("3\n")


def blk_name(dev):
    """/dev/loop3 -> loop3, /dev/mapper/x -> dm-N."""
    real = os.path.realpath(dev)
    return os.path.basename(real)


def blk_stat(dev):
    """Read-side counters from /sys/block/<dev>/stat: (read_ios, read_sectors, read_ticks_ms)."""
    with open("/sys/block/%s/stat" % blk_name(dev)) as f:
        v = f.read().split()
    return {"read_ios": int(v[0]), "read_merges": int(v[1]),
            "read_sectors": int(v[2]), "read_ticks_ms": int(v[3]),
            "write_ios": int(v[4]), "write_sectors": int(v[6]),
            "in_flight": int(v[8])}


def blk_delta(before, after):
    return {k: after[k] - before[k] for k in before if k != "in_flight"}


class TestFS:
    """A loop-backed file system, optionally behind dm-delay, mounted at mnt."""

    def __init__(self, img, size_mb, fstype, mnt, delay_ms=None, direct_io=True,
                 mount_opts=None, fresh=True):
        self.img, self.size_mb, self.fstype, self.mnt = img, size_mb, fstype, mnt
        self.delay_ms, self.direct_io, self.mount_opts = delay_ms, direct_io, mount_opts
        self.loop = None
        self.dm = None
        self.dev = None
        # Real-device mode (E6): FPSTUDY_DEVICE=/dev/sdX replaces the loop image. mkfs
        # destroys the device, so it must be confirmed with
        # FPSTUDY_DEVICE_CONFIRM=wipe-<basename of the device>.
        self.real = os.environ.get("FPSTUDY_DEVICE")
        if self.real:
            ok = os.environ.get("FPSTUDY_DEVICE_CONFIRM") == "wipe-" + os.path.basename(self.real)
            if not ok:
                raise RuntimeError("refusing to use %s without FPSTUDY_DEVICE_CONFIRM=wipe-%s"
                                   % (self.real, os.path.basename(self.real)))
            self.loop = self.real
            if fresh:
                mkfs(fstype, self.loop)
            self._attach()
            return
        if fresh:
            make_image(img, size_mb)
        self.loop = losetup(img, direct_io)
        if fresh:
            mkfs(fstype, self.loop)
        self._attach()

    def _attach(self):
        self.dev = self.loop
        if self.delay_ms is not None:
            self.dm_name = "fpdelay%d" % os.getpid()
            self.dev = dm_delay_create(self.dm_name, self.loop, self.delay_ms, 0)
            self.dm = self.dm_name
        mount(self.dev, self.mnt, self.fstype, self.mount_opts)

    def remount_cold(self):
        """umount, drop caches, mount again: metadata must come from the device."""
        umount(self.mnt)
        drop_caches()
        mount(self.dev, self.mnt, self.fstype, self.mount_opts)

    def set_delay(self, delay_ms):
        """Rebuild the dm-delay layer with a new delay (file system unmounted meanwhile)."""
        umount(self.mnt)
        if self.dm:
            dm_remove(self.dm)
            self.dm = None
        self.delay_ms = delay_ms
        self._attach()

    def stat(self):
        return blk_stat(self.dev)

    def close(self, delete=True):
        umount(self.mnt)
        if self.dm:
            dm_remove(self.dm)
        if self.real:
            return
        if self.loop:
            lodetach(self.loop)
        if delete:
            try:
                os.remove(self.img)
            except OSError:
                pass
