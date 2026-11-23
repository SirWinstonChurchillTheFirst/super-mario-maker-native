#!/usr/bin/env python3
"""patch_fetch_2101010.py SMASH4_DIR : vertex fetch data format 0x19 (2_10_10_10: X, Y, Z in 10 bits each from the
low end, W in the top 2 bits) in the Latte shader translator. Super Mario 3D World packs its normals this way; without
it most of its vertex shaders could not be translated and the scene's models were not drawn.
Conversion per component width: signed normalized divides X, Y, Z by 511 and W by 1; unsigned by 1023 and 3."""
import sys
p = sys.argv[1] + '/runtime/src/latte/translate.cpp'
s = open(p, encoding='utf-8').read()
if 'case 0x19: // 2_10_10_10' in s:
    print('patch_fetch_2101010: already there')
    sys.exit(0)
old1 = '    case 0x1B: // 10_10_10_2: the 2-bit W is normalized/converted with 2 bits\n'
new1 = ('    case 0x19: // 2_10_10_10 (port/patch_fetch_2101010.py): same bit layout, converted below\n'
        '        c = "uvec4(w.x & 0x3FFu, (w.x >> 10) & 0x3FFu, (w.x >> 20) & 0x3FFu, w.x >> 30)";\n'
        '        bits = 10;\n'
        '        break;\n') + old1
old2 = '    std::string value;\n    if (is_float || raw32 || (bits == 32 && num_format != 2)) {\n'
new2 = r'''    if (data_format == 0x19 && !raw32) {
        // X, Y, Z are 10 bits wide and W 2 bits: each is sign-extended and scaled by its own width.
        const std::string si = format("ivec4(bitfieldExtract(ivec3((%s).xyz), 0, 10), bitfieldExtract(int((%s).w), 0, 2))",
                                      c.c_str(), c.c_str());
        if (num_format == 1) return is_signed ? si : "ivec4(" + c + ")";
        if (num_format == 2) return is_signed ? "floatBitsToInt(vec4(" + si + "))" : "floatBitsToInt(vec4(" + c + "))";
        return is_signed ? "floatBitsToInt(max(vec4(" + si + ") / vec4(511.0, 511.0, 511.0, 1.0), -1.0))"
                         : "floatBitsToInt(vec4(" + c + ") / vec4(1023.0, 1023.0, 1023.0, 3.0))";
    }
''' + old2
for old, new in ((old1, new1), (old2, new2)):
    if old not in s:
        sys.exit('patch_fetch_2101010: text not found: %r' % old[:50])
    s = s.replace(old, new, 1)
open(p, 'w', encoding='utf-8').write(s)
print('patch_fetch_2101010: done')
