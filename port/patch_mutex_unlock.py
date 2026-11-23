#!/usr/bin/env python3
"""OSUnlockMutex by a thread that does not own the mutex: ignored (as coreinit does), not fatal.

usage: patch_mutex_unlock.py RUNTIME_DIR
Paper Mario Color Splash unlocks a mutex from another thread after "Druecke den A-Knopf" on the title screen; the
runtime stopped with a fatal error. coreinit (and Cemu) leave the mutex alone in that case. Printed once per mutex.
"""
import pathlib
import sys

p = pathlib.Path(sys.argv[1]) / "src/os/sync.cpp"
s = p.read_text()
old = """    if (mutex_owner(mutex) != self) {
        fatal("OSUnlockMutex on 0x%08X by a thread that does not own it", mutex);
    }"""
new = """    if (mutex_owner(mutex) != self) { // port/patch_mutex_unlock.py: coreinit ignores it
        static std::unordered_map<uint32_t, bool> said;
        if (!said[mutex]) {
            said[mutex] = true;
            std::fprintf(stderr, "port: OSUnlockMutex on 0x%08X by a thread that does not own it (owner 0x%08X): ignored\\n",
                         mutex, mutex_owner(mutex));
        }
        return;
    }"""
if new in s:
    print("already patched")
else:
    assert s.count(old) == 1
    s = s.replace(old, new)
    if "#include <cstdio>" not in s:
        s = s.replace('#include "kernel.h"', '#include "kernel.h"\n#include <cstdio>', 1)
    p.write_text(s)
    print("ok")
