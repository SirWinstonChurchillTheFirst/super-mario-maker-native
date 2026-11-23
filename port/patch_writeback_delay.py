"""TTT2_WRITEBACK_DELAY_MS=<n>: the retirement thread waits n ms before each batch of write-backs (test switch).

Makes write-backs land late on purpose, to reproduce on a fast PC the timing of the console, where Mario Tennis's
match picture comes out turned (port/patch_writeback_guard.py). Off unless set.
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "runtime/src/gpu/vulkan/targets.cpp")
text = open(path, encoding="utf-8").read()
if "patch_writeback_delay" in text:
    print("already: targets.cpp")
    sys.exit(0)
old = "void Renderer::retired(uint64_t value) {\n"
new = (old +
       "    // port/patch_writeback_delay.py: late write-backs on purpose (test switch).\n"
       "    static const int delay_ms = [] {\n"
       "        const char* v = std::getenv(\"TTT2_WRITEBACK_DELAY_MS\");\n"
       "        return v ? std::atoi(v) : 0;\n"
       "    }();\n"
       "    if (delay_ms > 0) {\n"
       "        bool any;\n"
       "        {\n"
       "            std::lock_guard lock(write_back_mutex_);\n"
       "            any = !write_backs_.empty() && write_backs_.front().value <= value;\n"
       "        }\n"
       "        if (any) std::this_thread::sleep_for(std::chrono::milliseconds(delay_ms));\n"
       "    }\n")
if text.count(old) != 1:
    sys.exit("targets.cpp: retired() not found")
text = text.replace(old, new)
for inc in ("#include <thread>\n", "#include <chrono>\n"):
    if inc not in text:
        first = text.index("#include <")
        text = text[:first] + inc + text[first:]
open(path, "w", encoding="utf-8", newline="").write(text)
print("patched: targets.cpp")
