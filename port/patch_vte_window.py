#!/usr/bin/env python3
"""patch_vte_window.py RUNTIME_SRC_DIR (…/runtime/src) — replaces patch_vte_off.py's identity viewport.

With PA_CL_VTE_CNTL's X/Y scale+offset bits off the vertex shader gives window pixels (x/w, y/w); GX2's clear and
copy special states also switch clipping off. Vulkan always clips at |x|,|y| <= w, so the old identity viewport
clipped every vertex beyond pixel 1 (Super Mario Maker's clear rect 0..1152 x 0..648 drew nothing). Now the vertex
shader scales x/y by 1/V (dc.scaled.z, float bits, 0 = off) and the viewport maps NDC -1..1 to -V..V pixels, so
pixels up to V arrive unchanged and nothing is clipped. With Z scale+offset off (dc.scaled.w = 1) the depth is z/w
as on the hardware (the translated shader's GL-style (z+w)/2 is undone). TTT2_VTE_OFF_AS_BEFORE=1 = old way."""
import sys

src = sys.argv[1]
# --- shader side ---
p = src + "/latte/translate.cpp"
s = open(p, encoding="utf-8").read()
old = """                    if (!env_.clip_space_dx) line("gl_Position.z = (gl_Position.z + gl_Position.w) * 0.5;");
"""
new = """                    if (!env_.clip_space_dx) line("gl_Position.z = (gl_Position.z + gl_Position.w) * 0.5;");
                    // port/patch_vte_window.py: viewport transform off -> window pixels, scaled into the clip volume.
                    line("if (dc.scaled.z != 0u) gl_Position.xy *= uintBitsToFloat(dc.scaled.z);");
                    if (!env_.clip_space_dx) line("if (dc.scaled.w != 0u) gl_Position.z = 2.0 * gl_Position.z - gl_Position.w;");
"""
if "patch_vte_window" not in s:
    assert s.count(old) == 1, "translate.cpp: pattern not found"
    s = s.replace(old, new)
    open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("patched", p)
else:
    print("translate.cpp: already applied")

# --- draw side ---
p = src + "/gpu/vulkan/draw.cpp"
s = open(p, encoding="utf-8").read()
if "patch_vte_window" in s:
    print("draw.cpp: already applied"); sys.exit(0)
old1 = """    dc.texture_scale = target_scale();
"""
new1 = """    dc.texture_scale = target_scale();
    // port/patch_vte_window.py: window-coordinate draws (viewport transform off).
    static const bool vte_as_before = std::getenv("TTT2_VTE_OFF_AS_BEFORE") != nullptr;
    const uint32_t vte_cntl = r(reg::PA_CL_VTE_CNTL);
    const bool vte_xy_off = !vte_as_before && (vte_cntl & 0xF) == 0;
    const bool vte_z_off = !vte_as_before && (vte_cntl & 0x30) == 0;
    // V: window pixels reachable; 2 * V * scale must stay within maxViewportDimensions (16384 on RADV/NVIDIA).
    const float vte_window = std::min(4096.0f, 8192.0f / std::max(pass_scale, 1.0f));
    dc.pad[0] = vte_xy_off ? std::bit_cast<uint32_t>(1.0f / vte_window) : 0u;
    dc.pad[1] = vte_z_off ? 1u : 0u;
"""
assert s.count(old1) == 1, "draw.cpp: dc pattern not found"
s = s.replace(old1, new1)
old2 = """    if ((r(reg::PA_CL_VTE_CNTL) & 0x3F) == 0 && std::getenv("TTT2_VTE_OFF_AS_BEFORE") == nullptr) {
        // port/patch_vte_off.py: vertices are window pixels; the identity viewport passes them through.
        viewport = {-vscale, -vscale, 2.0f * vscale, 2.0f * vscale, 0.0f, 1.0f};
    } else if ((r(reg::PA_CL_VTE_CNTL) & 0x3F) != 0x3F) {"""
new2 = """    if (vte_z_off) {
        viewport.minDepth = 0.0f; // port/patch_vte_window.py: depth = z/w (the shader undid its (z+w)/2)
        viewport.maxDepth = 1.0f;
    }
    if (vte_xy_off) {
        // port/patch_vte_window.py: NDC -1..1 -> window pixels -V..V (times the pass's scale); the shader scaled by 1/V.
        const float v = vte_window * vscale;
        viewport.x = -v;
        viewport.y = -v;
        viewport.width = 2.0f * v;
        viewport.height = 2.0f * v;
    } else if (vte_as_before && (r(reg::PA_CL_VTE_CNTL) & 0x3F) == 0) {
        viewport = {-vscale, -vscale, 2.0f * vscale, 2.0f * vscale, 0.0f, 1.0f}; // old patch_vte_off.py
    } else if ((r(reg::PA_CL_VTE_CNTL) & 0x3F) != 0x3F && !vte_z_off) {"""
assert s.count(old2) == 1, "draw.cpp: viewport pattern not found"
s = s.replace(old2, new2)
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched", p)
