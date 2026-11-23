#!/usr/bin/env python3
"""One-off edit of smash4/runtime/src/os/heap.cpp: MEMFreeToFrmHeap (needs the file's private frame heap table).
Kept for the record; the result is in port/upstream-local.patch."""
import sys

p = sys.argv[1]
s = open(p).read()
anchor = "CAFE_EXPORT(coreinit, MEMGetBaseHeapHandle, MEMGetBaseHeapHandle);"
assert anchor in s and "MEMFreeToFrmHeap" not in s
new = """// MEMFreeToFrmHeap: bit 0 of the mode gives back everything taken from the head, bit 1 from the tail.
static void MEMFreeToFrmHeap(uint32_t handle, uint32_t mode) {
    std::lock_guard lock(g_heap_mutex);
    const auto it = g_frame_heaps.find(handle);
    if (it == g_frame_heaps.end()) fatal("0x%08X is not a frame heap", handle);
    if (mode & 1) it->second->head = it->second->begin;
    if (mode & 2) it->second->tail = it->second->end;
}
CAFE_EXPORT(coreinit, MEMFreeToFrmHeap, MEMFreeToFrmHeap);

"""
open(p, "w").write(s.replace(anchor, new + anchor))
