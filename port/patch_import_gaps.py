#!/usr/bin/env python3
"""patch_import_gaps.py SMASH4_DIR : the GPU imports MEM2 up to its LAST committed 64 KiB, committing holes in between.

The import used to stop at the first uncommitted 64 KiB. With an extra module (Mario Kart 8's mvplayer.rpl, data at
0x10300000 after a hole from 0x10210000) only 0x10000000-0x1020FFFF reached the GPU: every vertex buffer, texture and
uniform block in the heaps above had no device address, the shaders read zeros and every target stayed black."""
import sys
root = sys.argv[1]
p = root + '/runtime/src/gpu/vulkan/context.cpp'
s = open(p, encoding='utf-8').read()
OLD = '''        // Import the committed part from the region's start.
        uint32_t size = 0;
        while (size < r.size && guest_memory_committed(r.base + size, 0x10000)) size += 0x10000;
'''
NEW = '''        // Import the committed part from the region's start, up to its last committed 64 KiB; holes in between
        // (an extra module's data placed after a gap) are committed so the import is one piece
        // (port/patch_import_gaps.py).
        uint32_t size = 0;
        for (uint32_t off = 0; off < r.size; off += 0x10000) {
            if (guest_memory_committed(r.base + off, 0x10000)) size = off + 0x10000;
        }
        for (uint32_t off = 0; off < size; off += 0x10000) {
            if (!guest_memory_committed(r.base + off, 0x10000)) {
                std::fprintf(stderr, "ttt2: GPU: committing hole 0x%08X for the import\\n", r.base + off);
                commit_guest_memory(r.base + off, 0x10000);
            }
        }
'''
if NEW not in s:
    if OLD not in s:
        sys.exit('patch_import_gaps: text not found')
    s = s.replace(OLD, NEW, 1)
    open(p, 'w', encoding='utf-8').write(s)
