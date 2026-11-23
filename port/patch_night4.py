#!/usr/bin/env python3
"""patch_night4.py SMASH4_DIR : four runtime changes of 19 November (applied with `patch -p1 < night4.diff`).

1. gpu/vulkan/targets.cpp - a depth clear through a 16-bit depth view also sets the colour target of the same place
   and size (Mario Tennis Ultra Smash clears its 16-bit float linear-depth target that way: 0.48436 = 0x7BFF, the
   largest half float). Without it old characters stayed in the character panels.
2. gpu/vulkan/draw.cpp - colour write mask = CB_TARGET_MASK & CB_SHADER_MASK: targets a pixel shader does not
   output to are not written (the title leaves its G-buffer bound while one-output lighting shaders run; Vulkan
   wrote undefined values into it - the characters were coloured noise).
3. latte/translate.cpp - the register file is zeroed with one statement per register, not a loop: Mesa's RADV
   (the console's Vega 6) kept the registers in memory with the loop and a full-screen draw took 6-60 ms.
4. latte/cafe_shader_main.cpp - builds with libc++ on Windows (path to string).
Run after the older patch scripts (see setup.sh)."""
import os, subprocess, sys
d = sys.argv[1]
if 'patch_shader_mask' in open(d + '/runtime/src/gpu/vulkan/draw.cpp', encoding='utf-8').read():
    print('patch_night4: already there'); sys.exit(0)
diff = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'night4.diff')
subprocess.run(['patch', '-p1', '-d', d, '-i', diff], check=True)
print('patch_night4: done')
