#!/usr/bin/env python3
"""patch_slice_targets.py SMASH4_DIR : render targets for slices of 3D / array surfaces (CB_COLORn_VIEW slice start).

The runtime ignored CB_COLORn_VIEW: a title that renders into slice z of a 3D or array texture (Mario Kart 8's
8x8x8 colour-grading LUT, its 512x288x2 array) drew every slice into the same 2D target at the surface's base, and a
3D/array texture read back only slice 0 from a target. The LUT's other slices stayed empty, so the final colour
grading turned the whole race black.

Now a target drawn with slice start z > 0 is kept under the key base + z * slice size (slice size = the target's
pitch * height * bytes, rounded up to 256 bytes, 2 KiB for macro-tiled modes so the swizzle bits stay clear), and a
3D/array texture whose slice 0 comes from a target picks up its other slices from the targets under those keys
(copied into the 3D depth / array layer). TTT2_SLICE_TARGETS=0 = old behaviour. Only GPU-side copies use the keys;
a slice target's write-back to guest memory is turned off (its memory layout would be wrong for thick tiling)."""
import sys
root = sys.argv[1]


def edit(path, pairs):
    p = root + '/' + path
    s = open(p, encoding='utf-8').read()
    for old, new in pairs:
        if new in s:
            continue
        if old not in s:
            sys.exit('patch_slice_targets: text not found in %s: %r' % (path, old[:70]))
        s = s.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(s)


edit('runtime/src/gpu/vulkan/draw.cpp', [
    ('''        const uint32_t info = r(reg::CB_COLOR0_INFO + t * 4), base = r(reg::CB_COLOR0_BASE + t * 4);
''', '''        const uint32_t info = r(reg::CB_COLOR0_INFO + t * 4);
        uint32_t base = r(reg::CB_COLOR0_BASE + t * 4);
'''),
    ('''        if (((target_mask >> (4 * t)) & 0xF) == 0 || ((info >> 2) & 0x3F) == 0 || base == 0) continue;
        colors[t] = color_target(base, r(reg::CB_COLOR0_SIZE + t * 4), info);
''', '''        if (((target_mask >> (4 * t)) & 0xF) == 0 || ((info >> 2) & 0x3F) == 0 || base == 0) continue;
        // port/patch_slice_targets.py: slice z of a 3D/array surface is its own target, at base + z * slice size.
        const uint32_t slice = r(reg::CB_COLOR0_VIEW + t * 4) & 0x7FF;
        if (slice != 0 && slice_targets_enabled()) {
            const uint32_t size_reg = r(reg::CB_COLOR0_SIZE + t * 4);
            const uint32_t pitch = ((size_reg & 0x3FF) + 1) * 8;
            const uint32_t height = (((size_reg >> 10) & 0xFFFFF) + 1) * 64 / pitch;
            const uint32_t tile = (info >> 8) & 0xF;
            const uint32_t bytes = std::max(1u, color_format(color_buffer_surface_format(info)).bytes);
            base += slice * slice_key_bytes(pitch, height, bytes, tile) >> 8;
        }
        colors[t] = color_target(base, r(reg::CB_COLOR0_SIZE + t * 4), info);
        if (slice != 0 && colors[t] && slice_targets_enabled()) const_cast<Target*>(colors[t])->write_back = false;
'''),
])

edit('runtime/src/gpu/vulkan/renderer.h', [
    ('''    bool load_texture_from_targets(Texture& t);''',
     '''    bool load_texture_from_targets(Texture& t);
    // port/patch_slice_targets.py
    static bool slice_targets_enabled() {
        static const bool on = [] {
            const char* v = std::getenv("TTT2_SLICE_TARGETS");
            return v == nullptr || *v != '0';
        }();
        return on;
    }
    static uint32_t slice_key_bytes(uint32_t pitch, uint32_t height, uint32_t bytes, uint32_t tile_mode) {
        const uint32_t align = tile_mode >= 4 ? 0x800u : 0x100u;
        return (pitch * height * bytes + align - 1) & ~(align - 1);
    }'''),
])

edit('runtime/src/gpu/vulkan/textures.cpp', [
    ('''    if (t.source == sources[0] && t.loaded >= newest && t.scale == sources[0]->scale) return true;
''', '''    // port/patch_slice_targets.py: the other slices of a 3D/array texture, from their slice targets.
    const Target* slice_sources[64] = {};
    const uint32_t slice_count = r.depth > 1 && !f.compressed && slice_targets_enabled() ? std::min(r.depth, 64u) : 0;
    if (slice_count > 1) {
        const Target* s0 = sources[0];
        const uint32_t step = slice_key_bytes(s0->pitch, s0->height, std::max(1u, f.bytes), r.tile_mode);
        for (uint32_t z = 1; z < slice_count; ++z) {
            const Target* src = find_target(s0->address + z * step, 0, false);
            if (src == nullptr || src->written <= src->overwritten || src->pitch != s0->pitch ||
                src->height != s0->height || src->scale != s0->scale || color_format(src->format).bytes != f.bytes) {
                continue;
            }
            slice_sources[z] = src;
            note_target_read(src);
            newest = std::max(newest, src->written);
        }
    }
    if (t.source == sources[0] && t.loaded >= newest && t.scale == sources[0]->scale) return true;
'''),
    ('''    barrier();
    profile_mark("texture from target", sources[0]->address, scaled(r.width, scale), scaled(r.height, scale));
''', '''    for (uint32_t z = 1; z < slice_count; ++z) { // port/patch_slice_targets.py
        const Target* src = slice_sources[z];
        if (src == nullptr) continue;
        const bool is_3d = r.dim == gx2::kDim3D;
        VkImageCopy region{};
        region.srcSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
        region.dstSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, is_3d ? 0u : z, 1};
        region.dstOffset = {0, 0, is_3d ? static_cast<int32_t>(z) : 0};
        region.extent = {std::min(scaled(r.width, scale), std::min(src->image.width, t.image.width)),
                         std::min(scaled(r.height, scale), std::min(src->image.height, t.image.height)), 1};
        vkCmdCopyImage(cmd(), src->image.image, VK_IMAGE_LAYOUT_GENERAL, t.image.image, VK_IMAGE_LAYOUT_GENERAL, 1,
                       &region);
    }
    barrier();
    profile_mark("texture from target", sources[0]->address, scaled(r.width, scale), scaled(r.height, scale));
'''),
])
