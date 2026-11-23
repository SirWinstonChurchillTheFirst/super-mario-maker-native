"""TTT2_MAX_PENDING_SWAPS=<n>: how many swaps the title may queue ahead of the display (runtime default 5).

Test switch for Mario Tennis's turned match picture on the console: the title reads data the GPU wrote back a couple
of frames later; a CPU that runs further ahead than on the console may read it before it is there.
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "runtime/src/gx2/display.cpp")
text = open(path, encoding="utf-8").read()
if "TTT2_MAX_PENDING_SWAPS" in text:
    print("already: display.cpp")
    sys.exit(0)
old = "        if (status.swaps - status.flips <= kMaxPendingSwaps) break;\n"
new = ("        static const uint32_t max_pending = [] { // port/patch_pending_swaps.py\n"
       "            const char* v = std::getenv(\"TTT2_MAX_PENDING_SWAPS\");\n"
       "            return v ? static_cast<uint32_t>(std::atoi(v)) : kMaxPendingSwaps;\n"
       "        }();\n"
       "        if (status.swaps - status.flips <= max_pending) break;\n")
if text.count(old) != 1:
    sys.exit("display.cpp: anchor not found")
open(path, "w", encoding="utf-8", newline="").write(text.replace(old, new))
print("patched: display.cpp")
