#!/usr/bin/env python3
"""Debug: TTT2_TRACE_HEAP=LO-HI (hex) prints every expanded/frame heap create, destroy, alloc and free that
touches [LO, HI) with the guest LR, to find who allocated a block a title later frees to the wrong heap.

usage: patch_heap_trace.py RUNTIME_DIR
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])


def sub(path, old, new, count=1):
    p = root / path
    text = p.read_text()
    if new in text:
        print(f"{path}: already patched")
        return
    if text.count(old) != count:
        sys.exit(f"{path}: expected {count}x {old[:60]!r}, found {text.count(old)}")
    p.write_text(text.replace(old, new))
    print(f"{path}: ok")


sub("src/os/heap.cpp", """#include <unordered_map>
""", """#include <unordered_map>
#include <algorithm> // port/patch_heap_trace.py
#include <cstdio>
#include <cstdlib>
""")

sub("src/os/heap.cpp", """uint32_t align_up(uint32_t v, uint32_t a) { return (v + a - 1) & ~(a - 1); }""",
    """uint32_t align_up(uint32_t v, uint32_t a) { return (v + a - 1) & ~(a - 1); }

// port/patch_heap_trace.py: TTT2_TRACE_HEAP=LO-HI
void trace_heap(const char* what, uint32_t heap, uint32_t a, uint32_t b) {
    static const std::pair<uint32_t, uint32_t> range = [] {
        const char* v = std::getenv("TTT2_TRACE_HEAP");
        if (v == nullptr) return std::pair<uint32_t, uint32_t>{0, 0};
        char* end = nullptr;
        const uint32_t lo = static_cast<uint32_t>(std::strtoul(v, &end, 16));
        const uint32_t hi = end && *end == '-' ? static_cast<uint32_t>(std::strtoul(end + 1, nullptr, 16)) : lo + 1;
        return std::pair<uint32_t, uint32_t>{lo, hi};
    }();
    if (range.second == 0) return;
    const uint32_t lo = std::min(a, b), hi = std::max(a, b) + 1;
    if (hi <= range.first || lo >= range.second) return;
    const uint32_t lr = current_thread() ? static_cast<uint32_t>(current_thread()->ctx.lr) : 0;
    std::fprintf(stderr, "heap: %s heap %08X %08X %08X lr %08X\\n", what, heap, a, b, lr);
}""")

sub("src/os/heap.cpp", """uint32_t MEMCreateExpHeapEx(GuestAddress start, uint32_t size, uint32_t) {
    std::lock_guard lock(g_heap_mutex);
    return create_exp_heap(start.value, size);""", """uint32_t MEMCreateExpHeapEx(GuestAddress start, uint32_t size, uint32_t) {
    std::lock_guard lock(g_heap_mutex);
    trace_heap("create exp", 0, start.value, start.value + size); // port/patch_heap_trace.py
    return create_exp_heap(start.value, size);""")
sub("src/os/heap.cpp", """    std::lock_guard lock(g_heap_mutex);
    g_exp_heaps.erase(heap.value);""", """    std::lock_guard lock(g_heap_mutex);
    if (const auto it = g_exp_heaps.find(heap.value); it != g_exp_heaps.end()) // port/patch_heap_trace.py
        trace_heap("destroy exp", heap.value, it->second->begin, it->second->end);
    g_exp_heaps.erase(heap.value);""")
sub("src/os/heap.cpp", """    std::lock_guard lock(g_heap_mutex);
    return exp_alloc(exp_heap(heap), size, alignment);""", """    std::lock_guard lock(g_heap_mutex);
    const uint32_t payload = exp_alloc(exp_heap(heap), size, alignment);
    trace_heap("alloc exp", heap, payload, payload + size); // port/patch_heap_trace.py
    return payload;""")
sub("src/os/heap.cpp", """    std::lock_guard lock(g_heap_mutex);
    exp_free(exp_heap(heap), payload);""", """    std::lock_guard lock(g_heap_mutex);
    trace_heap("free exp", heap, payload, payload); // port/patch_heap_trace.py
    exp_free(exp_heap(heap), payload);""")
