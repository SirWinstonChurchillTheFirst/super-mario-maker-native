#!/usr/bin/env python3
"""One-off edits of the Smash4PC runtime (kept for the record; the result is in port/upstream-local.patch):
GX2SetEventCallback's callbacks are really called. Upstream accepts and never calls them ("call them if the title
waits on them"); Mario & Sonic Rio 2016 waits for them and otherwise reports a GPU timeout twice a second.
  GX2EventType: 0 start-of-pipe interrupt, 1 end-of-pipe interrupt, 2 vsync, 3 flip, 4 display list overrun.
  Called here: 2 at every vertical blank, 3 at every flip, 1 when a user timestamp submitted with its interrupt
  flag has been written. Not called: 0 and 4.
usage: patch_gx2_events.py <smash4/runtime/src>"""
import sys

root = sys.argv[1]

# ---- gpu/gpu.h: the interface
p = root + "/gpu/gpu.h"
s = open(p).read()
a = "void host_vsync_stopped();"
assert a in s and "fire_event" not in s
s = s.replace(a, a + """

// GX2 event callbacks (GX2SetEventCallback): callback(type, data) on a guest thread of its own, with interrupts
// off as on the console. fire_event queues one call; it never blocks and may be called under any lock.
void set_event_callback(uint32_t type, uint32_t function, uint32_t data);
void fire_event(uint32_t type);""")
open(p, "w").write(s)

# ---- gpu/display.cpp: the thread, and the vsync and flip events
p = root + "/gpu/display.cpp"
s = open(p).read()
a = """void flip(uint64_t now) {
    ++g_flips;"""
b = """constexpr uint32_t kEventTypes = 5;
struct EventCallback {
    uint32_t function = 0, data = 0;
};
std::mutex g_event_mutex;
std::condition_variable g_event_ready;
EventCallback g_event_callbacks[kEventTypes];
uint32_t g_event_pending[kEventTypes] = {};
os::Thread* g_event_thread = nullptr;

void* event_main(void*) {
    os::Thread* t = g_event_thread;
    os::bind_current_thread(t);
    for (;;) {
        uint32_t type = 0;
        EventCallback callback;
        {
            std::unique_lock lock(g_event_mutex);
            g_event_ready.wait(lock, [] {
                for (uint32_t pending : g_event_pending) {
                    if (pending) return true;
                }
                return false;
            });
            while (g_event_pending[type] == 0) ++type;
            --g_event_pending[type];
            callback = g_event_callbacks[type];
        }
        if (callback.function == 0) continue;
        os::KernelLock lock(os::kernel_mutex());
        os::acquire_interrupt_lock(lock, t);
        lock.unlock();
        call_guest(t->ctx, callback.function, {type, callback.data});
        lock.lock();
        bool held = false;
        os::release_interrupt_lock_for_wait(t, held);
    }
    return nullptr;
}

void flip(uint64_t now) {
    fire_event(3);
    ++g_flips;"""
assert a in s
s = s.replace(a, b)
a = """void vsync_locked() {
    const uint64_t now = cafe_ppc_timebase();"""
b = """void vsync_locked() {
    fire_event(2);
    const uint64_t now = cafe_ppc_timebase();"""
assert a in s
s = s.replace(a, b)
a = "void host_vsync(uint32_t count) {"
assert a in s
b = """void set_event_callback(uint32_t type, uint32_t function, uint32_t data) {
    if (type >= kEventTypes) return;
    std::lock_guard lock(g_event_mutex);
    g_event_callbacks[type] = {function, data};
    if (function != 0 && g_event_thread == nullptr) {
        g_event_thread = os::create_internal_thread("cafe gx2 events", 0);
        pthread_t host;
        pthread_attr_t attr;
        pthread_attr_init(&attr);
        pthread_attr_setstacksize(&attr, 64u << 20);
        pthread_create(&host, &attr, event_main, nullptr);
        pthread_attr_destroy(&attr);
        pthread_detach(host);
    }
}

void fire_event(uint32_t type) {
    if (type >= kEventTypes) return;
    std::lock_guard lock(g_event_mutex);
    if (g_event_callbacks[type].function == 0) return;
    // A callback that falls behind is not owed every blank it missed.
    if (g_event_pending[type] < 2) ++g_event_pending[type];
    g_event_ready.notify_one();
}

"""
s = s.replace(a, b + a)
for inc in ("#include <condition_variable>", "#include <mutex>", "#include <pthread.h>", '#include "cafe/export.h"'):
    if inc not in s:
        s = s.replace("#include <algorithm>", inc + "\n#include <algorithm>", 1)
# flip() and vsync_locked() are defined before fire_event: declare it is enough (gpu.h), nothing more to do.
open(p, "w").write(s)

# ---- gx2/display.cpp: registering, and the interrupt flag of a user timestamp
p = root + "/gx2/display.cpp"
s = open(p).read()
a = """// shortcut: event callbacks (vsync, flip, ...) are accepted and never called; call them if the title waits on them.
void GX2SetEventCallback(uint32_t, uint32_t, uint32_t) {}"""
b = """// Event callbacks (GX2EventType: 0/1 start/end-of-pipe interrupt, 2 vsync, 3 flip, 4 display list overrun) are
// called by the display and the command processor (gpu/display.cpp); 0 and 4 never happen here.
void GX2SetEventCallback(uint32_t type, uint32_t function, uint32_t data) {
    gpu::set_event_callback(type, function, data);
}"""
assert a in s
s = s.replace(a, b)
a = """void GX2SubmitUserTimeStamp(be<uint64_t>* out, uint64_t value, uint32_t event, bool) {"""
b = """void GX2SubmitUserTimeStamp(be<uint64_t>* out, uint64_t value, uint32_t event, bool interrupt) {"""
assert a in s
s = s.replace(a, b)
a = """write_packet(pm4::kEventWriteEop, {type | pm4::kEventIndexTs, address, pm4::kEopData64, lo, hi});"""
b = """// INT_SEL (bits 24-25 of the third word): the end-of-pipe interrupt once the data is written.
        write_packet(pm4::kEventWriteEop,
                     {type | pm4::kEventIndexTs, address, pm4::kEopData64 | (interrupt ? 2u << 24 : 0u), lo, hi});"""
assert a in s
s = s.replace(a, b)
open(p, "w").write(s)

# ---- gpu/command_processor.cpp: the interrupt of an end-of-pipe write
p = root + "/gpu/command_processor.cpp"
s = open(p).read()
a = """        default: break;
        }
        break;
    }
    case pm4::kMemWrite: {"""
b = """        default: break;
        }
        // shortcut: the interrupt is raised when the packet is read, not when its write retires; a title that
        // reads the timestamp inside the callback could see the old value.
        if ((arg(2) >> 24) & 3) fire_event(1);
        break;
    }
    case pm4::kMemWrite: {"""
assert a in s
s = s.replace(a, b)
open(p, "w").write(s)
