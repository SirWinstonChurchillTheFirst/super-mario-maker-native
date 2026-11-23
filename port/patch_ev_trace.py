#!/usr/bin/env python3
"""One-off edit of smash4/runtime/src/gpu/display.cpp: TTT2_TRACE_EVENTS prints the first GX2 event callbacks
queued and called. Kept for the record; the result is in port/upstream-local.patch."""
import sys

p = sys.argv[1]
s = open(p).read()
NL = chr(92) + "n"
assert "event queued" not in s
a = "    if (g_event_callbacks[type].function == 0) return;\n"
b = a + ('    static const bool trace = std::getenv("TTT2_TRACE_EVENTS") != nullptr;\n'
         '    static int traced = 0;\n'
         '    if (trace && type < 2 && traced < 12) {\n'
         '        ++traced;\n'
         '        std::fprintf(stderr, "ttt2: gx2: event queued %u' + NL + '", type);\n'
         '    }\n')
assert a in s
s = s.replace(a, b)
a = "        call_guest(t->ctx, callback.function, {type, callback.data});\n"
b = ('        static const bool trace = std::getenv("TTT2_TRACE_EVENTS") != nullptr;\n'
     '        static int traced = 0;\n'
     '        if (trace && type < 2 && traced < 12) {\n'
     '            ++traced;\n'
     '            std::fprintf(stderr, "ttt2: gx2: event %u calls 0x%08X' + NL + '", type, callback.function);\n'
     '        }\n') + a
assert a in s
s = s.replace(a, b)
if "#include <cstdlib>" not in s:
    s = s.replace("#include <algorithm>", "#include <cstdlib>\n#include <algorithm>", 1)
open(p, "w").write(s)
