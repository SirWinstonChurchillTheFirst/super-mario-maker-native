#!/usr/bin/env python3
"""One-off edit of smash4/runtime/src/gpu/command_processor.cpp: the end-of-pipe interrupt of a user timestamp is
raised after its write has retired, not when the packet is read (the callback of Mario & Sonic Rio 2016 looks at
the timestamp). Kept for the record; the result is in port/upstream-local.patch."""
import sys

p = sys.argv[1]
s = open(p).read()
a = "    enum Kind : uint8_t { kTimestamp, kWrite32, kWrite64, kWriteClock } kind;"
b = "    enum Kind : uint8_t { kTimestamp, kWrite32, kWrite64, kWriteClock, kInterrupt } kind;"
assert a in s
s = s.replace(a, b)
a = "        case Retirement::kWriteClock: wr64(r.address, clock()); break;\n        }"
b = ("        case Retirement::kWriteClock: wr64(r.address, clock()); break;\n"
     "        case Retirement::kInterrupt: fire_event(1); break; // GX2's end-of-pipe interrupt callback\n        }")
assert a in s
s = s.replace(a, b)
start = s.index("        // shortcut: the interrupt is raised when the packet is read")
end = s.index("        break;", start)
new = ("        // INT_SEL: the end-of-pipe interrupt, after the write above has retired.\n"
       "        if ((arg(2) >> 24) & 3) retire_later({Retirement::kInterrupt, g_backend->flush(), 0, 0});\n")
s = s[:start] + new + s[end:]
open(p, "w").write(s)
