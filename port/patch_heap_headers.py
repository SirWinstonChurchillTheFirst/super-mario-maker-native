#!/usr/bin/env python3
"""Cafe heap headers in guest memory: data range and the parent's list of child heaps.

usage: patch_heap_headers.py RUNTIME_DIR   (after patch_heap_trace.py)

Before: MEMCreateExpHeapEx/MEMCreateFrmHeapEx wrote only the tag ("EXPH"/"FRMH") at the heap handle. Paper Mario
Color Splash frees memory through its own lookup (0x02414908): it reads heap->dataStart (+0x18) / dataEnd (+0x1C) and
walks the heap's child list (+0x0C head, link at +0x04 of each child) to find the innermost heap holding a pointer, like
coreinit's MEMFindContainHeap. With zeros there it freed a child heap's block to the parent: fatal "free of 0x33CC3740,
which this heap did not allocate".
After: every expanded/frame heap gets the MEMHeapHeader fields as on hardware - link {prev, next} at 0x04, child list
{head, tail, u16 count, u16 offset=4} at 0x0C, dataStart 0x18, dataEnd 0x1C - and a heap made inside another heap's
range is appended to that heap's child list (removed again on destroy).
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


sub("src/os/heap.cpp", """// The free list, by address and by size: allocations take the smallest block""", """// port/patch_heap_headers.py: MEMHeapHeader in guest memory. Offsets: 0x04 link {prev, next}, 0x0C child list
// {head, tail, u16 count, u16 offset}, 0x18 dataStart, 0x1C dataEnd. Children are linked through their link field.
struct HeapRange { uint32_t start, end, parent; };
std::map<uint32_t, HeapRange> g_heap_ranges; // handle -> data range and parent heap (0: none)

void put32(uint32_t address, uint32_t value) { *guest<be<uint32_t>>(address) = value; }
uint32_t get32(uint32_t address) { return *guest<be<uint32_t>>(address); }

// The innermost heap whose data range holds [start, end), or 0.
uint32_t containing_heap(uint32_t start, uint32_t end, uint32_t self) {
    uint32_t best = 0, best_size = 0xFFFFFFFFu;
    for (const auto& [handle, r] : g_heap_ranges) {
        if (handle == self || start < r.start || end > r.end) continue;
        if (r.end - r.start < best_size) {
            best = handle;
            best_size = r.end - r.start;
        }
    }
    return best;
}

void register_heap(uint32_t handle, uint32_t data_start, uint32_t data_end) {
    for (uint32_t o = 0x04; o < 0x18; o += 4) put32(handle + o, 0);
    *guest<be<uint16_t>>(handle + 0x16) = 4; // the children's link offset
    put32(handle + 0x18, data_start);
    put32(handle + 0x1C, data_end);
    const uint32_t parent = containing_heap(handle, data_end, handle);
    g_heap_ranges[handle] = {data_start, data_end, parent};
    if (parent == 0) return;
    const uint32_t tail = get32(parent + 0x10);
    put32(handle + 0x04, tail); // prev
    put32(handle + 0x08, 0);    // next
    if (tail) put32(tail + 0x08, handle);
    else put32(parent + 0x0C, handle);
    put32(parent + 0x10, handle);
    *guest<be<uint16_t>>(parent + 0x14) = static_cast<uint16_t>(*guest<be<uint16_t>>(parent + 0x14) + 1);
}

void unregister_heap(uint32_t handle) {
    const auto it = g_heap_ranges.find(handle);
    if (it == g_heap_ranges.end()) return;
    const uint32_t parent = it->second.parent;
    g_heap_ranges.erase(it);
    if (parent == 0 || g_heap_ranges.find(parent) == g_heap_ranges.end()) return;
    const uint32_t prev = get32(handle + 0x04), next = get32(handle + 0x08);
    if (prev) put32(prev + 0x08, next);
    else put32(parent + 0x0C, next);
    if (next) put32(next + 0x04, prev);
    else put32(parent + 0x10, prev);
    *guest<be<uint16_t>>(parent + 0x14) = static_cast<uint16_t>(*guest<be<uint16_t>>(parent + 0x14) - 1);
}

// The free list, by address and by size: allocations take the smallest block""")

sub("src/os/heap.cpp", """    add_free(*heap, heap->begin, end - heap->begin);
    g_exp_heaps[begin] = std::move(heap);
    return begin;""", """    add_free(*heap, heap->begin, end - heap->begin);
    register_heap(begin, heap->begin, end); // port/patch_heap_headers.py
    g_exp_heaps[begin] = std::move(heap);
    return begin;""")

sub("src/os/heap.cpp", """    *guest<be<uint32_t>>(begin) = kFrmMagic;
    g_frame_heaps[begin] = std::make_unique<FrameHeap>(
        FrameHeap{begin + kHeaderSize, end, begin + kHeaderSize, end});
    return begin;""", """    *guest<be<uint32_t>>(begin) = kFrmMagic;
    g_frame_heaps[begin] = std::make_unique<FrameHeap>(
        FrameHeap{begin + kHeaderSize, end, begin + kHeaderSize, end});
    register_heap(begin, begin + kHeaderSize, end); // port/patch_heap_headers.py
    return begin;""")

sub("src/os/heap.cpp", """        trace_heap("destroy exp", heap.value, it->second->begin, it->second->end);
    g_exp_heaps.erase(heap.value);""", """        trace_heap("destroy exp", heap.value, it->second->begin, it->second->end);
    unregister_heap(heap.value); // port/patch_heap_headers.py
    g_exp_heaps.erase(heap.value);""")
