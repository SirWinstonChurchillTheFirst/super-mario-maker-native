#!/usr/bin/env python3
"""wbstats.py DIR: statistics of dumped write-backs (TTT2_DUMP_WB): R32 float for 0xF55E.. (8x8..96x96 reduction chain),
R11G11B10 float for the rest. Prints min/max/mean per channel and NaN/Inf counts."""
import glob, math, os, struct, sys

def f11(v, mb):
    e, m = v >> mb, v & ((1 << mb) - 1)
    if e == 31:
        return float("nan") if m else float("inf")
    if e == 0:
        return m / (1 << mb) * 2.0 ** -14
    return (1 + m / (1 << mb)) * 2.0 ** (e - 15)

for f in sorted(glob.glob(os.path.join(sys.argv[1], "wb_*.bin"))):
    d = open(f, "rb").read()
    n = len(d) // 4
    name = os.path.basename(f)
    if "F55E" in name:
        vals = [struct.unpack_from("<f", d, i * 4)[0] for i in range(n)]
        chans = [vals]
    else:
        ws = struct.unpack_from("<%dI" % n, d)
        chans = [[f11(w & 0x7FF, 6) for w in ws], [f11((w >> 11) & 0x7FF, 6) for w in ws], [f11(w >> 22, 5) for w in ws]]
    out = []
    for c in chans:
        fin = [x for x in c if math.isfinite(x)]
        bad = len(c) - len(fin)
        out.append("min %.4g max %.4g mean %.4g bad %d" % (min(fin) if fin else 0, max(fin) if fin else 0, sum(fin) / len(fin) if fin else 0, bad))
    print(name, " | ".join(out))
