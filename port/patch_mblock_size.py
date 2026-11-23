"""coreinit MEMGetSizeForMBlockExpHeap: the usable size of an expanded-heap block (Mario Kart 8's mvplayer module).

Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "runtime/src/os/heap.cpp")
text = open(path, encoding="utf-8").read()
if "patch_mblock_size" in text:
    print("already: heap.cpp")
    sys.exit(0)
old1 = "uint32_t MEMSetAllocModeForExpHeap(uint32_t, uint32_t) { return 0; }\n"
new1 = old1 + (
    "// port/patch_mblock_size.py: payload up to the block's end, as allocated (sizes are rounded up to 4).\n"
    "uint32_t MEMGetSizeForMBlockExpHeap(uint32_t payload) {\n"
    "    std::lock_guard lock(g_heap_mutex);\n"
    "    for (const auto& [handle, heap] : g_exp_heaps) {\n"
    "        const auto it = heap->used.find(payload);\n"
    "        if (it != heap->used.end()) return it->second.second - payload;\n"
    "    }\n"
    "    return 0;\n"
    "}\n")
old2 = "CAFE_EXPORT(coreinit, MEMSetAllocModeForExpHeap, MEMSetAllocModeForExpHeap);\n"
new2 = old2 + "CAFE_EXPORT(coreinit, MEMGetSizeForMBlockExpHeap, MEMGetSizeForMBlockExpHeap);\n"
if text.count(old1) != 1 or text.count(old2) != 1:
    sys.exit("heap.cpp: anchors not found")
open(path, "w", encoding="utf-8", newline="").write(text.replace(old1, new1).replace(old2, new2))
print("patched: heap.cpp")
