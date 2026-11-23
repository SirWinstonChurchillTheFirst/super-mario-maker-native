#!/usr/bin/env python3
"""patch_surface_invalid.py SMASH4_DIR : a surface with the INVALID format (0) that addrlib rejects gets size 0 and a
line in the log (three at most) instead of ending the program. Mario Kart 8 asks for the size of such a surface
(format 0, garbage tile mode) while it starts; where that surface comes from is not understood yet."""
import sys
p = sys.argv[1] + '/runtime/src/gx2/surface.cpp'
s = open(p, encoding='utf-8').read()
old = '''        if (AddrComputeSurfaceInfo(addrlib(), &in, &out) != ADDR_OK) {
'''
new = r'''        if (format == 0 && AddrComputeSurfaceInfo(addrlib(), &in, &out) != ADDR_OK) {
            static int said = 0;
            if (said < 3) {
                ++said;
                std::fprintf(stderr, "port: GX2: a %ux%ux%u surface with the invalid format 0 (tile mode 0x%X) was asked "
                             "for its size: answered 0 bytes\n", width, height, slices, uint32_t{s.tile_mode});
            }
            info.pitch = std::max(1u, width);
            info.height = std::max(1u, height);
            info.depth = slices;
            info.size = 0;
            info.base_align = info.pitch_align = info.height_align = 1;
            info.tile_mode = s.tile_mode & 0xF;
            info.bpp = 0;
            return info;
        }
        if (AddrComputeSurfaceInfo(addrlib(), &in, &out) != ADDR_OK) {
'''
if 'invalid format 0' not in s:
    if old not in s:
        sys.exit('patch_surface_invalid: text not found')
    s = s.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(s)
print('patch_surface_invalid: done')
