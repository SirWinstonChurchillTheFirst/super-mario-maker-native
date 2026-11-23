#!/usr/bin/env python3
"""patch_scancopy_regs.py RUNTIME_SRC_DIR (…/runtime/src)

GX2CopyColorBufferToScanBuffer: the console's copy reads only the colour buffer's SURFACE. The runtime looked the
source target up by the buffer's register words (cb_color_size/info), which a title need not have initialised:
Super Mario Maker passes its GamePad buffer (0xF5C7B800 854x480 pitch 864, format 0x019) with zero register words
-> format 0 -> no target -> GamePad picture always black. Now the register words are rebuilt from the surface on a
copy of the struct (init_color_buffer_regs). TTT2_SCANCOPY_AS_IS=1 = old behaviour."""
import sys

p = sys.argv[1] + "/gx2/display.cpp"
s = open(p, encoding="utf-8").read()
old = """    g_copied[target == 4 ? 1 : 0] = true;
    HlePacket(pm4::kHleCopyColorToScan).u32(target).guest_struct(*buffer).write();"""
new = """    g_copied[target == 4 ? 1 : 0] = true;
    // port/patch_scancopy_regs.py: the copy uses the surface only; register words rebuilt from it.
    static const bool as_is = std::getenv("TTT2_SCANCOPY_AS_IS") != nullptr;
    ColorBuffer copy = *buffer;
    if (!as_is) init_color_buffer_regs(copy);
    HlePacket(pm4::kHleCopyColorToScan).u32(target).guest_struct(copy).write();"""
if "patch_scancopy_regs" in s:
    print("already applied"); sys.exit(0)
assert old in s, "pattern not found"
s = s.replace(old, new)
if "#include <cstdlib>" not in s:
    s = s.replace("#include", "#include <cstdlib>\n#include", 1)
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched", p)
