#!/usr/bin/env python3
"""One-off edit of smash4/runtime/src/gx2/display.cpp: a user timestamp is written as [low word][high word].
Mario & Sonic Rio 2016's interrupt callback (0x0340061C) reads the word at +4 as the high half; with upstream's
order ([high][low]) the game reported a GPU timeout twice a second (16 in 14 s), with this order none (measured
19 Nov, null GPU). TTT2_TS_HIGH_FIRST=1 gives upstream's order back. NOT checked against Tekken Tag 2 or Smash,
which upstream was written for. Kept for the record; the result is in port/upstream-local.patch."""
import sys

p = sys.argv[1]
s = open(p).read()
a = "    const uint32_t lo = static_cast<uint32_t>(value), hi = static_cast<uint32_t>(value >> 32);\n"
assert a in s and "TTT2_TS_HIGH_FIRST" not in s
b = ('    static const bool swap = std::getenv("TTT2_TS_HIGH_FIRST") == nullptr;\n'
     "    const uint32_t lo = static_cast<uint32_t>(swap ? value >> 32 : value);\n"
     "    const uint32_t hi = static_cast<uint32_t>(swap ? value : value >> 32);\n")
open(p, "w").write(s.replace(a, b))
