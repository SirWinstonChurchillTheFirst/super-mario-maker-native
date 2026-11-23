#!/usr/bin/env python3
"""One-off edit of smash4/runtime/src/gpu/display.cpp: a log line for every registered GX2 event callback.
Kept for the record; the result is in port/upstream-local.patch."""
import sys

p = sys.argv[1]
lines = open(p).read().split("\n")
out = []
skip = False
for line in lines:
    if "ttt2: gx2: event callback" in line:
        skip = not line.rstrip().endswith(";")  # a broken earlier attempt spans two lines
        continue
    if skip:
        skip = False
        continue
    out.append(line)
s = "\n".join(out)
a = "    if (type >= kEventTypes) return;\n    std::lock_guard lock(g_event_mutex);\n    g_event_callbacks[type] = {function, data};"
assert a in s
NL = chr(92) + "n"
b = '    std::fprintf(stderr, "ttt2: gx2: event callback %u = 0x%08X (data 0x%08X)' + NL + '", type, function, data);\n' + a
s = s.replace(a, b)
if "#include <cstdio>" not in s:
    s = s.replace("#include <algorithm>", "#include <cstdio>\n#include <algorithm>", 1)
open(p, "w").write(s)
