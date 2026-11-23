#!/usr/bin/env python3
"""patch_vte_off.py SMASH4_DIR : draws with the viewport transform switched off (PA_CL_VTE_CNTL scale/offset bits all 0).

Such a draw gives its vertices in window pixels already (Mario Tennis Ultra Smash: its full-screen passes, with
VTE_CNTL = 0x400). The runtime set the title's viewport all the same, so the pixels were read as clip coordinates.
Vulkan has no switch for this; a viewport of x -1, y -1, width 2, height 2 (times the pass's scale) and depth 0..1
makes its transform the identity, so the window coordinates arrive unchanged. A draw with only SOME of the six bits
set is still reported and drawn as before."""
import sys
p = sys.argv[1] + '/runtime/src/gpu/vulkan/draw.cpp'
s = open(p, encoding='utf-8').read()
if 'patch_vte_off' in s:
    print('patch_vte_off: already there'); sys.exit(0)
old = '    if ((r(reg::PA_CL_VTE_CNTL) & 0x3F) != 0x3F) report_once("viewport transform partly disabled", r(reg::PA_CL_VTE_CNTL));\n'
new = ('    if ((r(reg::PA_CL_VTE_CNTL) & 0x3F) == 0 && std::getenv("TTT2_VTE_OFF_AS_BEFORE") == nullptr) {\n'
       '        // port/patch_vte_off.py: vertices are window pixels; the identity viewport passes them through.\n'
       '        viewport = {-vscale, -vscale, 2.0f * vscale, 2.0f * vscale, 0.0f, 1.0f};\n'
       '    } else if ((r(reg::PA_CL_VTE_CNTL) & 0x3F) != 0x3F) {\n'
       '        report_once("viewport transform partly disabled", r(reg::PA_CL_VTE_CNTL));\n'
       '    }\n')
if old not in s:
    sys.exit('patch_vte_off: text not found')
open(p, 'w', encoding='utf-8').write(s.replace(old, new, 1))
print('patch_vte_off: done')
