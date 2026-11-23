"""At a swap, the previous frame's write-backs are in guest memory before the title may go on (Mario Tennis).

The command processor lets the title go on at a swap once the previous frame's GPU work has finished (wait_for).
The small render targets that frame wrote reach guest memory only when the retirement thread gets to them
(Renderer::retired), which can be later. With frame interpolation the replays delayed the title enough; at 60 frames
a second (the console) the title could read the previous frame's results before they were there.
Now the command processor tiles them itself right after the wait (retired(previous); the retirement thread skips what
is done). TTT2_SWAP_RETIRE=0 turns it off (A/B).
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "runtime/src/gpu/command_processor.cpp")
text = open(path, encoding="utf-8").read()
if "patch_swap_retire" in text:
    print("already: command_processor.cpp")
    sys.exit(0)
old = ("                g_backend->idle(); // (a held-back submission would never finish)\n"
       "                g_backend->wait_for(previous);\n")
new = old + ("                // port/patch_swap_retire.py: that frame's write-backs in guest memory before the title goes on.\n"
             "                static const bool retire = [] {\n"
             "                    const char* v = std::getenv(\"TTT2_SWAP_RETIRE\");\n"
             "                    return v == nullptr || *v != '0';\n"
             "                }();\n"
             "                if (retire) g_backend->retired(previous);\n")
if text.count(old) != 1:
    sys.exit("command_processor.cpp: anchor not found")
text = text.replace(old, new)
if "#include <cstdlib>" not in text:
    first = text.index("#include <")
    text = text[:first] + "#include <cstdlib>\n" + text[first:]
open(path, "w", encoding="utf-8", newline="").write(text)
print("patched: command_processor.cpp")
