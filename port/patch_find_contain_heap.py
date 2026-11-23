"""coreinit MEMFindContainHeap(ptr): the innermost expanded/frame heap whose data range holds ptr (Mario Party 10
imports it). Uses the ranges port/patch_heap_headers.py keeps. Applied to the runtime tree (default ~/wiiu/smash4)."""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "runtime/src/os/heap.cpp")
text = open(path, encoding="utf-8").read()
if "patch_find_contain_heap" in text:
    sys.exit("already: " + path)
old = "CAFE_EXPORT(coreinit, MEMCreateExpHeapEx, MEMCreateExpHeapEx);\n"
assert text.count(old) == 1
new = ("// port/patch_find_contain_heap.py\n"
       "uint32_t MEMFindContainHeap(uint32_t pointer) { return containing_heap(pointer, pointer + 1, 0); }\n"
       "CAFE_EXPORT(coreinit, MEMFindContainHeap, MEMFindContainHeap);\n" + old)
text = text.replace(old, new)
open(path, "w", encoding="utf-8", newline="").write(text)
print("patched", path)
