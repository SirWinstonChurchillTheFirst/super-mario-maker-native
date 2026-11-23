#!/usr/bin/env python3
"""Lists an RPL's exports (.fexports / .dexports, section type 0x80000001) and whether relocations patch them.

Own tool, reads the file only. usage: rplexports.py FILE.rpl
Export section: u32 count, u32 signature, count x (u32 value, u32 name offset from the section start), names.
"""
import struct
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
import rpxinfo  # noqa: E402

path = sys.argv[1]
secs, data, names = None, None, None
res = rpxinfo.load(path)
_, secs, data = res
shstr = None
for s in secs:
    pass


def secname(s):
    return s.get("sname") or s.get("name")


for s in secs:
    if s["type"] == 0x80000001:
        d = data(s)
        count, sig = struct.unpack_from(">II", d, 0)
        print(f"{secname(s)} @0x{s['addr']:08X} size {len(d)}: {count} exports")
        for k in range(count):
            value, noff = struct.unpack_from(">II", d, 8 + k * 8)
            noff &= 0x7FFFFFFF
            end = d.index(b"\0", noff)
            print(f"   0x{value:08X} {d[noff:end].decode()}")
for s in secs:
    if s["type"] == 4 and secs[s["info"]]["type"] == 0x80000001:
        print("relocations for export section", secname(secs[s["info"]]), "entries", len(data(s)) // 12)
