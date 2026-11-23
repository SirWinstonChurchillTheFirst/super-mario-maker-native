#!/usr/bin/env python3
"""One-off edit of smash4/runtime/src/gx2/display.cpp: TTT2_TRACE_EVENTS prints the first user timestamps a title
submits. Kept for the record; the result is in port/upstream-local.patch."""
import sys

p = sys.argv[1]
s = open(p).read()
a = "void GX2SubmitUserTimeStamp(be<uint64_t>* out, uint64_t value, uint32_t event, bool interrupt) {\n    ApiLock lock;\n"
assert a in s and "user timestamp" not in s
NL = chr(92) + "n"
b = a + ('    static const bool trace = std::getenv("TTT2_TRACE_EVENTS") != nullptr;\n'
         '    static int traced = 0;\n'
         '    if (trace && traced < 8) {\n'
         '        ++traced;\n'
         '        std::fprintf(stderr, "ttt2: gx2: user timestamp 0x%llX to 0x%08X, pipe event %u, interrupt %d' + NL + '",\n'
         '                     static_cast<unsigned long long>(value), guest_address(out), event, interrupt);\n'
         '    }\n')
s = s.replace(a, b)
if "#include <cstdlib>" not in s:
    s = s.replace("#include <cstdio>", "#include <cstdio>\n#include <cstdlib>", 1)
open(p, "w").write(s)
