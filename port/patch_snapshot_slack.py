"""Frame-record copies keep 256 KiB free at the end of the record buffer (suspect for a GPU fault on the console).

A shader may read a uniform block beyond the part the runtime copies (read_extent): in guest memory that is still
mapped, in the frame record it ran past the end of the buffer when a copy sat at its very end - on the console's
Radeon such a read is a page fault (device lost); the PC's GPU tolerated it. Copies now stop kMaxSnapshot (256 KiB)
before the end of the record, so every read stays inside the buffer.
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "runtime/src/gpu/vulkan/interpolate.cpp")
text = open(path, encoding="utf-8").read()
if "patch_snapshot_slack" in text:
    print("already: interpolate.cpp")
    sys.exit(0)
old = "    if (start + size > f.data.size) {\n"
new = "    if (start + size + kMaxSnapshot > f.data.size) { // port/patch_snapshot_slack.py: room for reads past a copy\n"
if text.count(old) != 1:
    sys.exit("interpolate.cpp: anchor not found")
open(path, "w", encoding="utf-8", newline="").write(text.replace(old, new))
print("patched: interpolate.cpp")
