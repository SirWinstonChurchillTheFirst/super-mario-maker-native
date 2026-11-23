#!/usr/bin/env python3
"""patch_threads.py SMASH4_DIR : default threads for cores 0 and 2, OSRunThread, OSSuspendThread, OSContinueThread
(Mario Tennis Ultra Smash runs its jobs on the other cores' default threads)."""
import sys
root = sys.argv[1]
p = root + '/runtime/src/os/thread.cpp'
s = open(p, encoding='utf-8').read()

OLD = 'uint32_t OSGetDefaultThread(uint32_t core) { return core == 1 && g_main_thread ? g_main_thread->guest : 0; }\n'
NEW = r'''// Cores 0 and 2 get a default thread the first time a title asks: an OSThread with a 1 MB stack that has not run
// yet (state "none"), for OSRunThread (port/patch_threads.py).
uint32_t g_default_threads[3]{};
uint32_t OSGetDefaultThread(uint32_t core) {
    if (core == 1) return g_main_thread ? g_main_thread->guest : 0;
    if (core > 2) return 0;
    KernelLock lock(g_kernel);
    if (g_default_threads[core] == 0) {
        constexpr uint32_t kStack = 1u << 20;
        const uint32_t thread = system_alloc(kSize, 8);
        const uint32_t stack = system_alloc(kStack, 16);
        init_guest_thread(thread, 0, stack + kStack, kStack, 16, static_cast<uint8_t>(1u << core));
        set_state(thread, kNone);
        field<int32_t>(thread, kSuspend) = 0;
        g_default_threads[core] = thread;
    }
    return g_default_threads[core];
}

// OSRunThread: starts `entry` on a thread that is not running (never started, or ended). False while it still runs.
bool OSRunThread(GuestAddress thread, uint32_t entry, uint32_t argc, uint32_t argv) {
    KernelLock lock(g_kernel);
    Thread* old = thread_for(thread.value);
    if (old != nullptr) {
        if (!old->finished) return false;
        g_threads.erase(thread.value);
        delete old;
    }
    const uint8_t attr = *guest<uint8_t>(thread.value + kAttr);
    field<uint32_t>(thread.value, kEntry) = entry;
    auto* t = new Thread;
    t->guest = thread.value;
    t->core = core_for(attr, current_thread()->core);
    prepare_context(t, argc, argv);
    field<int32_t>(thread.value, kSuspend) = 0;
    set_state(thread.value, kRunning);
    g_threads[thread.value] = t;
    if (trace_threads()) {
        std::fprintf(stderr, "ttt2: thread 0x%08X run: entry 0x%08X, core %d, by 0x%08X\n", thread.value, entry,
                     t->core, current_thread()->guest);
    }
    start_host_thread(t);
    return true;
}

// OSSuspendThread: counts. A thread that has not started stays stopped until resumed as often; a thread that
// already runs is NOT stopped (every guest thread is a free host thread) - said once.
int32_t OSSuspendThread(GuestAddress thread) {
    KernelLock lock(g_kernel);
    Thread* t = thread_for(thread.value);
    be<int32_t>& suspend = field<int32_t>(thread.value, kSuspend);
    const int32_t previous = suspend;
    suspend = previous + 1;
    if (t != nullptr && t->host_started && !t->finished) {
        static bool said = false;
        if (!said) {
            said = true;
            std::fprintf(stderr, "port: OSSuspendThread on running thread 0x%08X: counted, the thread keeps running\n",
                         thread.value);
        }
    }
    return previous;
}

// OSContinueThread: clears the suspend count and lets the thread go.
int32_t OSContinueThread(GuestAddress thread) {
    {
        KernelLock lock(g_kernel);
        be<int32_t>& suspend = field<int32_t>(thread.value, kSuspend);
        if (suspend <= 0) return suspend;
        suspend = 1;
    }
    return OSResumeThread(thread);
}
'''
EXP_OLD = 'CAFE_EXPORT(coreinit, OSGetDefaultThread, OSGetDefaultThread);\n'
EXP_NEW = EXP_OLD + ('CAFE_EXPORT(coreinit, OSRunThread, OSRunThread);\n'
                     'CAFE_EXPORT(coreinit, OSSuspendThread, OSSuspendThread);\n'
                     'CAFE_EXPORT(coreinit, OSContinueThread, OSContinueThread);\n')
if 'bool OSRunThread' not in s:
    for old, new in ((OLD, NEW), (EXP_OLD, EXP_NEW)):
        if old not in s:
            sys.exit('patch_threads: text not found: %r' % old[:50])
        s = s.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(s)
print('patch_threads: done')
