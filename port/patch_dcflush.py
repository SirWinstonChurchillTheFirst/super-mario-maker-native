#!/usr/bin/env python3
"""patch_dcflush.py SMASH4_DIR : DCFlushRange tells the renderer that the CPU wrote that memory.

Mario Tennis Ultra Smash draws each letter into a texture the first time a text needs it, flushes the data cache over
the texture (DCFlushRange) and uses it; it sends no ranged GX2Invalidate. The runtime reloaded a texture only after a
ranged invalidation, so every letter that came after the texture's first use was missing on screen ("uic  tart" for
"Quick Start"). On the console a flush is what makes CPU writes visible to the GPU, so it is taken as that here too:
textures over the range are checked (by hash) the next time they are used."""
import sys
p = sys.argv[1] + '/runtime/src/os/coreinit_misc.cpp'
s = open(p, encoding='utf-8').read()
if 'patch_dcflush' in s:
    print('patch_dcflush: already there'); sys.exit(0)
old = 'void DCFlushRange(uint32_t, uint32_t) {}\n'
new = ('// port/patch_dcflush.py: a flush makes CPU writes visible to the GPU; textures over the range are re-checked.\n'
       'void DCFlushRange(uint32_t address, uint32_t size) { gpu::cpu_wrote(address, size); }\n')
if old not in s:
    sys.exit('patch_dcflush: text not found')
s = s.replace(old, new, 1)
s = s.replace('#include "guest_format.h"\n', '#include "guest_format.h"\n#include "gpu/gpu.h"\n', 1)
open(p, 'w', encoding='utf-8').write(s)
print('patch_dcflush: done')
