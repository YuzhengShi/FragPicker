"""Generated variants of the unmodified upstream scripts, used only to split a run into
its phases. Each generator copies a contiguous range of upstream lines and asserts the
cut point, so the variant cannot silently drift from the file it was cut from."""

import os

CODE = os.environ.get("FPSTUDY_CODE", "/root/fpstudy/code")
CUT_MARK = "    file_list.add(req_info[0])"


def make_up_phase1(dst):
    """upstream src/analysis/processing.py lines 1-61 (Phase 1 only) + closing the trace."""
    src = os.path.join(CODE, "upstream", "src", "analysis", "processing.py")
    lines = open(src).read().split("\n")
    idx = [i for i, l in enumerate(lines) if l.rstrip() == CUT_MARK]
    assert len(idx) == 1 and idx[0] == 60, idx  # line 61 in the file
    body = "\n".join(lines[:idx[0] + 1]) + "\ntrace_file.close()\n"
    with open(dst, "w") as f:
        f.write("# GENERATED from upstream src/analysis/processing.py lines 1-61 (Phase 1 only)\n" + body)
    return dst
