#!/usr/bin/env python3
"""patch_tiny_color.py RUNTIME_SRC_DIR (…/runtime/src)

A Vulkan pass covers only the area all its attachments have; the console's GPU draws wherever the scissor allows.
Super Mario Maker clears its 1152x656 depth buffer with a stale 8x8 colour target still bound (0x2564B000): the
runtime clipped the whole clear to 8x8, the depth buffer kept the background's depth, and every terrain tile
drawn after it failed the depth test (ground, blocks invisible). In a clear/copy draw (viewport transform off) a colour target at
most half as wide and high as both the depth target and the scissor is now left out. TTT2_KEEP_TINY_COLOR=1 = old behaviour."""
import sys

p = sys.argv[1] + "/gpu/vulkan/draw.cpp"
s = open(p, encoding="utf-8").read()
if "patch_tiny_color" in s:
    print("already applied"); sys.exit(0)
old = """        depth = depth_target(r(reg::DB_DEPTH_BASE), r(reg::DB_DEPTH_SIZE), r(reg::DB_DEPTH_INFO));
    }
"""
new = """        depth = depth_target(r(reg::DB_DEPTH_BASE), r(reg::DB_DEPTH_SIZE), r(reg::DB_DEPTH_INFO));
    }
    // port/patch_tiny_color.py: a stale tiny colour target must not clip a big depth draw (the console's GPU does not).
    if (static const bool keep = std::getenv("TTT2_KEEP_TINY_COLOR") != nullptr; depth && !keep && (r(reg::PA_CL_VTE_CNTL) & 0xF) == 0) {
        const uint32_t sbr = r(reg::PA_SC_GENERIC_SCISSOR_TL + 4), svbr = r(reg::PA_SC_VPORT_SCISSOR_0_TL + 4);
        const uint32_t sw = std::min(sbr & 0x7FFF, svbr & 0x7FFF), sh = std::min((sbr >> 16) & 0x7FFF, (svbr >> 16) & 0x7FFF);
        for (uint32_t i = 0; i < color_count; ++i) {
            if (colors[i] && colors[i]->pitch * 2 <= std::min(sw, depth->pitch) &&
                colors[i]->height * 2 <= std::min(sh, depth->height)) {
                report_once("colour target far smaller than the depth target and scissor: left out of the draw", colors[i]->address);
                colors[i] = nullptr;
            }
        }
        while (color_count > 0 && colors[color_count - 1] == nullptr) --color_count;
    }
"""
assert s.count(old) == 1, "pattern not found"
s = s.replace(old, new)
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched", p)
