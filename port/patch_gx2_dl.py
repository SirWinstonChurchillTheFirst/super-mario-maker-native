#!/usr/bin/env python3
"""One-off edit of smash4/runtime/src/gx2/cbpool.cpp: GX2GetCurrentDisplayList (needs the file's recording state).
Kept for the record; the result is in port/upstream-local.patch."""
import sys

p = sys.argv[1]
s = open(p).read()
a = "bool GX2GetDisplayListWriteStatus() { return t_recording; }\n"
assert a in s and "GX2GetCurrentDisplayList" not in s
b = a + """// The list this thread is recording: its buffer and size in bytes. False when none is being recorded.
bool GX2GetCurrentDisplayList(be<uint32_t>* list, be<uint32_t>* bytes) {
    if (!t_recording) return false;
    if (list) *list = t_display_list.base;
    if (bytes) *bytes = t_display_list.size * 4;
    return true;
}
"""
s = s.replace(a, b)
a = "CAFE_EXPORT(gx2, GX2GetDisplayListWriteStatus, GX2GetDisplayListWriteStatus);"
assert a in s
s = s.replace(a, a + "\nCAFE_EXPORT(gx2, GX2GetCurrentDisplayList, GX2GetCurrentDisplayList);")
open(p, "w").write(s)
