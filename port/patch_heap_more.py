#!/usr/bin/env python3
"""coreinit MEMInitAllocatorForExpHeap, MEMResizeForMBlockExpHeap, MEMVisitAllocatedForExpHeap (Paper Mario Color Splash).

usage: patch_heap_more.py RUNTIME_DIR   (after patch_heap_headers.py)
- allocator {functions, heap, alignment, 0}; its functions allocate from / free to that expanded heap
- resize grows a block in place into a free block right after it, or shrinks it; returns the new size, 0 if it cannot
- visit calls visitor(block, heap, param) for every allocated block, in address order
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


sub("src/os/heap.cpp", """CAFE_EXPORT(coreinit, MEMAllocFromAllocator, MEMAllocFromAllocator);""", """// ---------------------------------------------------------------- port/patch_heap_more.py
uint32_t exp_allocator_alloc(GuestAddress allocator, uint32_t size) {
    const uint32_t heap = *guest<be<uint32_t>>(allocator.value + 4);
    const int32_t alignment = static_cast<int32_t>(static_cast<uint32_t>(*guest<be<uint32_t>>(allocator.value + 8)));
    return MEMAllocFromExpHeapEx(heap, size, alignment);
}
void exp_allocator_free(GuestAddress allocator, uint32_t block) {
    MEMFreeToExpHeap(*guest<be<uint32_t>>(allocator.value + 4), block);
}
void thunk_exp_allocator_alloc(PPCContext& ctx, uint8_t*) { abi::invoke<exp_allocator_alloc>(ctx); }
void thunk_exp_allocator_free(PPCContext& ctx, uint8_t*) { abi::invoke<exp_allocator_free>(ctx); }
void MEMInitAllocatorForExpHeap(GuestAddress allocator, uint32_t heap, int32_t alignment) {
    static uint32_t functions = 0;
    if (functions == 0) {
        functions = system_alloc(8, 4);
        guest<be<uint32_t>>(functions)[0] = register_host_function(thunk_exp_allocator_alloc, "allocator: expanded heap alloc");
        guest<be<uint32_t>>(functions)[1] = register_host_function(thunk_exp_allocator_free, "allocator: expanded heap free");
    }
    auto* a = guest<be<uint32_t>>(allocator.value);
    a[0] = functions;
    a[1] = heap;
    a[2] = static_cast<uint32_t>(alignment);
    a[3] = 0;
}

uint32_t MEMResizeForMBlockExpHeap(uint32_t handle, uint32_t payload, uint32_t size) {
    std::lock_guard lock(g_heap_mutex);
    ExpHeap& heap = exp_heap(handle);
    const auto it = heap.used.find(payload);
    if (it == heap.used.end()) return 0;
    size = align_up(size == 0 ? 1 : size, 4);
    uint32_t& end = it->second.second;
    const uint32_t wanted = payload + size;
    if (wanted <= end) { // shrink: the rest goes back (joined with a free block right after)
        if (end - wanted >= kBlockHeader + 4) {
            uint32_t free_start = wanted, free_end = end;
            auto next = heap.free.find(end);
            if (next != heap.free.end()) {
                free_end += next->second;
                remove_free(heap, next);
            }
            add_free(heap, free_start, free_end - free_start);
            end = wanted;
        }
        return end - payload;
    }
    auto next = heap.free.find(end);
    if (next == heap.free.end() || uint64_t{end} + next->second < wanted) return 0;
    const uint32_t free_end = next->first + next->second;
    remove_free(heap, next);
    if (free_end - wanted >= kBlockHeader + 4) {
        add_free(heap, wanted, free_end - wanted);
        end = wanted;
    } else {
        end = free_end;
    }
    return end - payload;
}

void MEMVisitAllocatedForExpHeap(PPCContext& ctx, uint32_t handle, uint32_t visitor, uint32_t param) {
    std::vector<uint32_t> blocks;
    {
        std::lock_guard lock(g_heap_mutex);
        for (const auto& [payload, range] : exp_heap(handle).used) blocks.push_back(payload);
    }
    for (const uint32_t block : blocks) call_guest(ctx, visitor, {block, handle, param});
}

CAFE_EXPORT(coreinit, MEMInitAllocatorForExpHeap, MEMInitAllocatorForExpHeap);
CAFE_EXPORT(coreinit, MEMResizeForMBlockExpHeap, MEMResizeForMBlockExpHeap);
CAFE_EXPORT(coreinit, MEMVisitAllocatedForExpHeap, MEMVisitAllocatedForExpHeap);
CAFE_EXPORT(coreinit, MEMAllocFromAllocator, MEMAllocFromAllocator);""")

sub("src/os/heap.cpp", """#include <unordered_map>
#include <algorithm> // port/patch_heap_trace.py""", """#include <unordered_map>
#include <vector>    // port/patch_heap_more.py
#include <algorithm> // port/patch_heap_trace.py""")

# Color Splash: snd_core AXInitWithParams (renderer/pipeline parameters) = AXInit.
sub("src/os/ax.cpp", """CAFE_EXPORT(snd_core, AXInit, AXInit);""", """CAFE_EXPORT(snd_core, AXInit, AXInit);
CAFE_EXPORT(snd_core, AXInitWithParams, AXInit); // port/patch_heap_more.py""")
