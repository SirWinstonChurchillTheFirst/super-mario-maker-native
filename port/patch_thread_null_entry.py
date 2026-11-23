"""OSCreateThread with entry 0: a thread object for OSRunThread later (Mario Party 10's audio/Havok/effect threads).
As in Cemu, such a thread is created in state "none" (not suspended, nothing runs), so OSIsThreadTerminated is true
and OSRunThread may start work on it. Before, it counted as created-and-suspended: MP10's main thread waited for
"NdSysAudio::runThread" to be idle forever. Applied to the runtime tree (default ~/wiiu/smash4)."""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "runtime/src/os/thread.cpp")
text = open(path, encoding="utf-8").read()
if "patch_thread_null_entry" in text:
    sys.exit("already: " + path)
old = ("    init_guest_thread(thread.value, entry, stack_top, stack_size, priority,\n"
       "                      static_cast<uint8_t>(attr));\n"
       "    auto* t = new Thread;\n")
assert text.count(old) == 1, "anchor"
new = ("    init_guest_thread(thread.value, entry, stack_top, stack_size, priority,\n"
       "                      static_cast<uint8_t>(attr));\n"
       "    if (entry == 0) { // port/patch_thread_null_entry.py: only for OSRunThread later\n"
       "        set_state(thread.value, kNone);\n"
       "        field<int32_t>(thread.value, kSuspend) = 0;\n"
       "        if (trace_threads()) {\n"
       "            std::fprintf(stderr, \"ttt2: thread 0x%08X created without entry (for OSRunThread), by 0x%08X\\n\",\n"
       "                         thread.value, current_thread()->guest);\n"
       "        }\n"
       "        return true;\n"
       "    }\n"
       "    auto* t = new Thread;\n")
text = text.replace(old, new)
open(path, "w", encoding="utf-8", newline="").write(text)
print("patched", path)
