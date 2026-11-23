"""TTT2_DUMP_THREADS_AT=<seconds> on Linux too (was Windows-only): each guest thread's name, state and guest
backtrace at that time. Applied to the runtime tree (default ~/wiiu/smash4)."""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "runtime/src/os/thread.cpp")
text = open(path, encoding="utf-8").read()
if "patch_dump_threads_linux" in text:
    sys.exit("already: " + path)
old = "void start_profiler() {}\nvoid request_profile_now() {}\n#endif\n"
assert text.count(old) == 1, "anchor"
new = ("void start_profiler() {\n"
       "    // port/patch_dump_threads_linux.py: TTT2_DUMP_THREADS_AT=seconds (as on Windows)\n"
       "    if (const char* at = std::getenv(\"TTT2_DUMP_THREADS_AT\")) {\n"
       "        const double seconds = std::atof(at);\n"
       "        std::thread([seconds] {\n"
       "            std::this_thread::sleep_for(std::chrono::duration<double>(seconds));\n"
       "            KernelLock lock(g_kernel);\n"
       "            for (const auto& [guest, t] : g_threads) {\n"
       "                const uint32_t name = field<uint32_t>(guest, kName);\n"
       "                std::fprintf(stderr, \"thread %08X \\\"%s\\\" state %u:\\n\", guest,\n"
       "                             name ? std::string(guest_string(name)).c_str() : \"\", state_of(guest));\n"
       "                dump_backtrace(t->ctx);\n"
       "            }\n"
       "            std::fflush(stderr);\n"
       "        }).detach();\n"
       "    }\n"
       "}\n"
       "void request_profile_now() {}\n#endif\n")
text = text.replace(old, new)
open(path, "w", encoding="utf-8", newline="").write(text)
print("patched", path)
