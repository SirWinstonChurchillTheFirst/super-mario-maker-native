"""TTT2_SWAP_RETIRE=2 (test switch, on top of patch_swap_retire.py): at a swap, the frame JUST swapped must also be
finished on the GPU and written back before the title goes on (costs the GPU/CPU overlap of one frame).

For Mario Tennis on the console, where waiting for the previous frame's write-backs (patch_swap_retire.py) was not
enough. Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "runtime/src/gpu/command_processor.cpp")
text = open(path, encoding="utf-8").read()
if "patch_swap_retire2" in text:
    print("already: command_processor.cpp")
    sys.exit(0)
old = "            previous = done;\n            frame_ready();\n"
new = ("            { // port/patch_swap_retire2.py\n"
       "                static const bool whole = [] {\n"
       "                    const char* v = std::getenv(\"TTT2_SWAP_RETIRE\");\n"
       "                    return v != nullptr && *v == '2';\n"
       "                }();\n"
       "                if (whole) {\n"
       "                    g_backend->idle();\n"
       "                    g_backend->wait_for(done);\n"
       "                    g_backend->retired(done);\n"
       "                }\n"
       "            }\n" + old)
if text.count(old) != 1:
    sys.exit("command_processor.cpp: anchor not found")
open(path, "w", encoding="utf-8", newline="").write(text.replace(old, new))
print("patched: command_processor.cpp")
