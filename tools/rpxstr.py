#!/usr/bin/env python3
"""rpxstr.py FILE ADDR... : the zero-terminated text at guest addresses of an RPX (own tool, reads only)."""
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0].rsplit("\\", 1)[0])
from rpxinfo import load
d, secs, data = load(sys.argv[1])
for a in sys.argv[2:]:
    a = int(a, 16)
    for s in secs:
        if s["addr"] <= a < s["addr"] + s["size"] and s["type"] == 1:
            b = data(s)[a - s["addr"]:a - s["addr"] + 120]
            print("%08X %s %r" % (a, s["sname"], b.split(b"\0")[0][:100]))
