#!/usr/bin/env python3
"""patch_fault_threads.py SMASH4_DIR : on a guest/host fault, also print every other guest thread's name, state and
backtrace (TTT2_FAULT_THREADS=0 = off). For races: shows what the other threads were doing at the moment of the fault.
The kernel lock is only TRIED (the faulting thread may hold it)."""
import sys
root = sys.argv[1]


def edit(path, pairs):
    p = root + '/' + path
    s = open(p, encoding='utf-8').read()
    for old, new in pairs:
        if new in s:
            continue
        if old not in s:
            sys.exit('patch_fault_threads: text not found in %s: %r' % (path, old[:60]))
        s = s.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(s)


edit('runtime/src/diagnostics.cpp', [
    ('''void report_guest_state_and_exit(int signal) {
    if (t_current != nullptr) {
        print_guest_state(*t_current);
    }
''', '''} // namespace
void (*g_fault_threads_hook)(const PPCContext*) = nullptr; // port/patch_fault_threads.py, set by os/thread.cpp
namespace {

void report_guest_state_and_exit(int signal) {
    if (t_current != nullptr) {
        print_guest_state(*t_current);
    }
    if (g_fault_threads_hook != nullptr) {
        static const bool on = [] {
            const char* v = std::getenv("TTT2_FAULT_THREADS");
            return v == nullptr || *v != '0';
        }();
        if (on) g_fault_threads_hook(t_current);
    }
'''),
])

edit('runtime/src/os/thread.cpp', [
    ('''    // TTT2_DUMP_THREADS_AT=seconds: then,''',
     '''    // port/patch_fault_threads.py: all threads at a fault.
    g_fault_threads_hook = [](const PPCContext* faulting) {
        KernelLock lock(g_kernel, std::try_to_lock);
        std::fprintf(stderr, "\\nother guest threads at the fault%s:\\n", lock.owns_lock() ? "" : " (kernel lock busy)");
        for (const auto& [guest, t] : g_threads) {
            if (&t->ctx == faulting) continue;
            const uint32_t name = field<uint32_t>(guest, kName);
            std::fprintf(stderr, "thread %08X \\"%s\\" core %d prio %d state %u:\\n", guest,
                         name ? std::string(guest_string(name)).c_str() : "", t->core,
                         field<int32_t>(guest, kEffectivePriority), state_of(guest));
            dump_backtrace(t->ctx);
        }
        std::fflush(stderr);
    };
    // TTT2_DUMP_THREADS_AT=seconds: then,'''),
])

edit('runtime/include/cafe/runtime.h', [
    ('''namespace cafe {
''', '''namespace cafe {
extern void (*g_fault_threads_hook)(const PPCContext*); // port/patch_fault_threads.py
''')
])
