"""The two 60 Hz changes OFF by default (console GPU fault 22 Nov 17:45 with them on; not a reliable Tennis fix).

port/patch_snapshot_constants.py: only with TTT2_SNAPSHOT_CONSTANTS=1. port/patch_swap_retire.py: only with
TTT2_SWAP_RETIRE=1 (or 2). Without those switches the runtime behaves as before both patches.
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
SRC = os.path.join(ROOT, "runtime/src/gpu")
pairs = [
    ("vulkan/interpolate.cpp",
     "snapshot_constants_ = frames_per_frame_ == 1 && (v == nullptr || *v != '0');",
     "snapshot_constants_ = frames_per_frame_ == 1 && v != nullptr && *v == '1'; // off by default (port/patch_60hz_off.py)"),
    ("command_processor.cpp",
     "                    return v == nullptr || *v != '0';\n",
     "                    return v != nullptr && (*v == '1' || *v == '2'); // off by default (port/patch_60hz_off.py)\n"),
]
for rel, old, new in pairs:
    path = os.path.join(SRC, rel)
    text = open(path, encoding="utf-8").read()
    if "patch_60hz_off" in text:
        print("already:", rel)
        continue
    if text.count(old) != 1:
        sys.exit(rel + ": anchor not found once")
    open(path, "w", encoding="utf-8", newline="").write(text.replace(old, new))
    print("patched:", rel)
