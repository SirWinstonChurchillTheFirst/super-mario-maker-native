#!/usr/bin/env python3
"""patch_threads3.py SMASH4_DIR (after patch_threads2.py): a thread started by a more urgent thread of the same core
does not run ahead of it, and a thread suspended before its first instruction stays stopped.

On the console a thread resumed by a more urgent thread on its own core does not run until that thread waits.
Mario Tennis Ultra Smash relies on it: its main thread (priority 16) resumes a priority-26 thread and suspends it
again at once, to start it later. Here every guest thread is a free host thread, so the new thread ran at once
and the title hung. This is NOT a scheduler: the new thread only gives its resumer 2 ms and then honours its
suspend count before its first instruction."""
import sys
root = sys.argv[1]


def edit(path, pairs):
    p = root + '/' + path
    s = open(p, encoding='utf-8').read()
    for old, new in pairs:
        if new in s:
            continue
        if old not in s:
            sys.exit('patch_threads3: text not found in %s: %r' % (path, old[:60]))
        s = s.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(s)


edit('runtime/src/os/kernel.h', [
    ('    bool finished = false; // entry returned or OSExitThread ran\n',
     '    bool finished = false; // entry returned or OSExitThread ran\n'
     '    bool after_resumer = false; // resumed by a more urgent thread of the same core (port/patch_threads3.py)\n'),
])
edit('runtime/src/os/thread.cpp', [
    ('''        const uint32_t entry = field<uint32_t>(t->guest, kEntry);
        if (t == g_main_thread && g_preinit_user != 0) run_preinit_user(t->ctx, g_preinit_user);
''',
     '''        const uint32_t entry = field<uint32_t>(t->guest, kEntry);
        if (t == g_main_thread && g_preinit_user != 0) run_preinit_user(t->ctx, g_preinit_user);
        if (t->after_resumer) {
            std::this_thread::sleep_for(std::chrono::milliseconds(2));
            KernelLock lock(g_kernel);
            wait_until(lock, t->guest, [&] { return field<int32_t>(t->guest, kSuspend) <= 0; });
        }
'''),
    ('''        if (previous == 1 && !t->host_started) {
            set_state(thread.value, kRunning);
            start_host_thread(t);''',
     '''        if (previous == 1 && !t->host_started) {
            set_state(thread.value, kRunning);
            if (Thread* self = t_current) {
                t->after_resumer = self->core == t->core &&
                                   field<int32_t>(self->guest, kEffectivePriority) <
                                       field<int32_t>(thread.value, kEffectivePriority);
            }
            start_host_thread(t);'''),
])
print('patch_threads3: done')
