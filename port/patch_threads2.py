#!/usr/bin/env python3
"""patch_threads2.py SMASH4_DIR (after patch_threads.py): a thread that suspends ITSELF really waits until it is
resumed (Tennis Ultra Smash's workers sleep that way); SAVEOpenFileAsync."""
import sys
root = sys.argv[1]


def edit(path, pairs):
    p = root + '/' + path
    s = open(p, encoding='utf-8').read()
    for old, new in pairs:
        if new in s:
            continue
        if old not in s:
            sys.exit('patch_threads2: text not found in %s: %r' % (path, old[:60]))
        s = s.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(s)


edit('runtime/src/os/thread.cpp', [
    ('''    suspend = previous + 1;
    if (t != nullptr && t->host_started && !t->finished) {''',
     '''    suspend = previous + 1;
    if (t != nullptr && t == current_thread()) {
        // Suspending oneself: sleep here until resumed as often as suspended.
        wait_until(lock, thread.value, [&] { return field<int32_t>(thread.value, kSuspend) <= 0; });
        return previous;
    }
    if (t != nullptr && t->host_started && !t->finished) {'''),
    ('''        suspend = previous - 1;
        if (previous == 1 && !t->host_started) {
            set_state(thread.value, kRunning);
            start_host_thread(t);
        }''',
     '''        suspend = previous - 1;
        if (previous == 1 && !t->host_started) {
            set_state(thread.value, kRunning);
            start_host_thread(t);
        } else if (previous == 1) {
            wake(thread.value); // a thread that suspended itself waits on its own channel
        }'''),
])
edit('runtime/src/os/fs.cpp', [
    ('CAFE_EXPORT(nn_save, SAVEOpenFile, SAVEOpenFile);',
     '''static int32_t SAVEOpenFileAsync(PPCContext& ctx, GuestAddress client, GuestAddress block, uint8_t slot, uint32_t path,
                                 uint32_t mode, be<int32_t>* handle, uint32_t mask, const be<uint32_t>* async) {
    return complete_async(ctx, client, block, SAVEOpenFile(client, block, slot, path, mode, handle, mask), async);
}
CAFE_EXPORT(nn_save, SAVEOpenFileAsync, SAVEOpenFileAsync);
CAFE_EXPORT(nn_save, SAVEOpenFile, SAVEOpenFile);'''),
])
print('patch_threads2: done')
