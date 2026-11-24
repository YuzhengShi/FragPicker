"""Synthetic file trees and synthetic traces in parse.sh output format.

parse.sh turns BCC output into lines "ino size pos direct type" and sorts them
with `sort -n -s -k1,1` (numeric on the inode, stable). gen_trace() writes that
format directly; gen_bcc_raw() writes BCC `trace` output so that parse.sh itself
can be exercised.
"""

import os
import random


def make_tree(root, n_files, per_dir=100, size=65536, seed=1, fsync_every=0):
    """Create n_files regular files of `size` bytes in directories of per_dir files.

    Returns the list of (inode, path) in creation order.
    """
    rnd = random.Random(seed)
    out = []
    buf = rnd.randbytes(size) if size else b""
    for i in range(n_files):
        d = os.path.join(root, "d%05d" % (i // per_dir))
        if i % per_dir == 0:
            os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "f%07d.dat" % i)
        with open(p, "wb") as f:
            if size:
                f.write(buf)
            if fsync_every and (i % fsync_every == 0):
                f.flush(); os.fsync(f.fileno())
        out.append((os.stat(p).st_ino, p))
    os.sync()
    return out


def make_fragmented_files(root, n_files, extents, block=4096, seed=1):
    """Files with ~`extents` extents each, by interleaving 1-block writes with a spacer
    file and forcing allocation with fsync after every block.

    Works on ext4/xfs (delayed allocation is forced by fsync), btrfs (COW extent per
    write) and f2fs (log-structured: blocks interleave in the same segment).
    Returns list of (inode, path). Actual extent counts must be read back with FIEMAP.
    """
    os.makedirs(root, exist_ok=True)
    data = random.Random(seed).randbytes(block)
    out = []
    for i in range(n_files):
        p = os.path.join(root, "frag%06d.dat" % i)
        sp = os.path.join(root, ".spacer")
        if extents <= 1:
            with open(p, "wb") as f:
                f.write(data * 4)
                f.flush(); os.fsync(f.fileno())
        else:
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
            sfd = os.open(sp, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            for b in range(extents):
                os.pwrite(fd, data, b * block)
                os.fsync(fd)
                os.write(sfd, data)
                os.fsync(sfd)
            os.close(fd); os.close(sfd)
            os.remove(sp)
        out.append((os.stat(p).st_ino, p))
    os.sync()
    return out


def gen_trace(path, inodes, lines_per_file, req_size=131072, direct=16384,
              pattern="seq", seed=1, rw=0, unaligned=False):
    """Write a parsed trace: per inode `lines_per_file` requests, sorted by inode
    (stable), like parse.sh output.

    pattern: 'seq' (consecutive requests), 'stride' (read_stride: 128K read, skip 288K),
             'rand' (uniform random offsets within 1 GiB, aligned unless unaligned=True).
    """
    rnd = random.Random(seed)
    rows = []
    for ino in inodes:
        pos = 0
        for k in range(lines_per_file):
            if pattern == "seq":
                p = pos; pos += req_size
            elif pattern == "stride":
                p = pos; pos += req_size + 288 * 1024
            else:
                p = rnd.randrange(0, 1 << 30)
                if not unaligned:
                    p -= p % 4096
            sz = req_size if not unaligned else rnd.randrange(1, req_size + 1)
            rows.append((ino, sz, p, direct, rw))
    rows.sort(key=lambda r: r[0])  # stable, like sort -n -s -k1,1
    with open(path, "w") as f:
        for r in rows:
            f.write("%d %d %d %d %d\n" % r)
    return len(rows)


def gen_bcc_raw(path, inodes, lines_per_file, req_size=131072, direct=16384, comm="read_seq"):
    """BCC trace output (with a header line) for parse.sh."""
    with open(path, "w") as f:
        f.write("PID     TID     COMM            FUNC             -\n")
        for ino in inodes:
            pos = 0
            for k in range(lines_per_file):
                f.write("%-7d %-7d %-15s %-16s ino = %d | size = %d | pos = %d | direct = %d | type = 0\n"
                        % (1234, 1234, comm, "vfs_read", ino, req_size, pos, direct))
                pos += req_size
