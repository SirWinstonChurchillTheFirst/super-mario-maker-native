#!/usr/bin/env python3
"""patch_fetch_1010102_order.py SMASH4_DIR : EXPERIMENT SWITCH (19 Nov), off by default.

With TTT2_1010102_HIGH=1 at run time, vertex fetch format 0x1B with normalized/scaled conversion is read with X in the
TOP ten bits (X 22-31, Y 12-21, Z 2-11, W 0-1) instead of upstream's order (X in the low bits, as format 0x19).
Mario Tennis Ultra Smash's character models are garbage with either order (their vertex shaders also fail with
"ALU clause runs past the end of the program"), so which order is right is NOT known; the default stays upstream's.
Remove the title's shader cache folder (build-NAME/cache) when switching."""
import sys
p = sys.argv[1] + '/runtime/src/latte/translate.cpp'
s = open(p, encoding='utf-8').read()
old = '''    case 0x1B: // 10_10_10_2: the 2-bit W is normalized/converted with 2 bits
        c = "uvec4(w.x & 0x3FFu, (w.x >> 10) & 0x3FFu, (w.x >> 20) & 0x3FFu, w.x >> 30)";
'''
new = '''    case 0x1B: // 10_10_10_2: the 2-bit W is normalized/converted with 2 bits
        c = "uvec4(w.x & 0x3FFu, (w.x >> 10) & 0x3FFu, (w.x >> 20) & 0x3FFu, w.x >> 30)";
        // port/patch_fetch_1010102_order.py (experiment): converted values with X in the top bits, only with TTT2_1010102_HIGH=1
        if (num_format != 1 && std::getenv("TTT2_1010102_HIGH") != nullptr) {
            c = "uvec4(w.x >> 22, (w.x >> 12) & 0x3FFu, (w.x >> 2) & 0x3FFu, w.x & 3u)";
        }
'''
if "patch_fetch_1010102_order" in s:
    print('already there'); sys.exit(0)
if old not in s:
    sys.exit('text not found')
s = s.replace(old, new, 1)
i = s.index('#include')
s = s[:i] + '#include <cstdlib>
' + s[i:]
open(p, 'w', encoding='utf-8').write(s)
print('patch_fetch_1010102_order: done')
