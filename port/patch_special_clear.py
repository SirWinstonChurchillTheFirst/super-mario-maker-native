#!/usr/bin/env python3
"""patch_special_clear.py RUNTIME_SRC_DIR (…/runtime/src)

GX2SetSpecialState(Clear = 0 / ClearHiZ = 1, enable) switches the viewport transform and clipping off, like Copy (2):
the title's own clear draw then gives its corners in window pixels. The runtime handled only Copy, so Super Mario
Maker's clear rect (register-mode shader with pixel corners 0..1152 x 0..648) was read as clip coordinates and
covered only the top-right quarter; colour and depth outside it kept old values and every later draw failed the
depth test there ("editor only in the top-right quarter"). TTT2_SPECIAL_COPY_ONLY=1 = old behaviour."""
import sys

p = sys.argv[1] + "/gx2/registers.cpp"
s = open(p, encoding="utf-8").read()
old = """void GX2SetSpecialState(uint32_t state, bool enable) {
    if (state != kSpecialStateCopy) return;"""
new = """void GX2SetSpecialState(uint32_t state, bool enable) {
    // port/patch_special_clear.py: Clear (0) and ClearHiZ (1) also draw in window coordinates.
    static const bool copy_only = std::getenv("TTT2_SPECIAL_COPY_ONLY") != nullptr;
    if (state > kSpecialStateCopy || (copy_only && state != kSpecialStateCopy)) return;"""
if new in s:
    print("already applied"); sys.exit(0)
assert old in s, "pattern not found"
s = s.replace(old, new)
if "#include <cstdlib>" not in s:
    s = s.replace("#include", "#include <cstdlib>\n#include", 1)
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched", p)
