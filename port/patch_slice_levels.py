#!/usr/bin/env python3
"""patch_slice_levels.py SMASH4_DIR (after patch_slice_targets.py): the other slices of a 3D/array/cube texture
are taken from slice targets for EVERY mip level that comes from a target, not only level 0 (Mario Kart 8 renders
each driver's 32x32 lighting cube and its 16x16 level 1 as two six-face MRT draws)."""
import sys
root = sys.argv[1]


def edit(path, pairs):
    p = root + '/' + path
    s = open(p, encoding='utf-8').read()
    for old, new in pairs:
        if new in s:
            continue
        if old not in s:
            sys.exit('patch_slice_levels: text not found in %s: %r' % (path, old[:70]))
        s = s.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(s)


edit('runtime/src/gpu/vulkan/textures.cpp', [
    ('''    const Target* slice_sources[64] = {};
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
''', '''    const Target* slice_sources[14][64] = {}; // port/patch_slice_levels.py: per level
    const uint32_t slice_count = r.depth > 1 && !f.compressed && slice_targets_enabled() ? std::min(r.depth, 64u) : 0;
    for (uint32_t level = 0; slice_count > 1 && level < levels; ++level) {
        const Target* s0 = sources[level];
        if (s0 == nullptr) continue;
        const uint32_t step = slice_key_bytes(s0->pitch, s0->height, std::max(1u, f.bytes), s0->tile_mode);
        for (uint32_t z = 1; z < slice_count; ++z) {
            const Target* src = find_target(s0->address + z * step, 0, false);
            if (src == nullptr || src->written <= src->overwritten || src->pitch != s0->pitch ||
                src->height != s0->height || src->scale != s0->scale || color_format(src->format).bytes != f.bytes) {
                continue;
            }
            slice_sources[level][z] = src;
            note_target_read(src);
            newest = std::max(newest, src->written);
        }
    }
'''),
    ('''    for (uint32_t z = 1; z < slice_count; ++z) { // port/patch_slice_targets.py
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
''', '''    for (uint32_t level = 0; slice_count > 1 && level < levels; ++level) { // port/patch_slice_levels.py
        const bool is_3d = r.dim == gx2::kDim3D;
        // a 3D texture's levels also halve in depth
        const uint32_t level_slices = is_3d ? std::max(1u, slice_count >> level) : slice_count;
        for (uint32_t z = 1; z < level_slices; ++z) {
            const Target* src = slice_sources[level][z];
            if (src == nullptr || src->scale != scale) continue;
            const uint32_t width = std::min(scaled(std::max(1u, r.width >> level), scale), std::max(1u, t.image.width >> level));
            const uint32_t height = std::min(scaled(std::max(1u, r.height >> level), scale), std::max(1u, t.image.height >> level));
            VkImageCopy region{};
            region.srcSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
            region.dstSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, level, is_3d ? 0u : z, 1};
            region.dstOffset = {0, 0, is_3d ? static_cast<int32_t>(z) : 0};
            region.extent = {std::min(width, src->image.width), std::min(height, src->image.height), 1};
            vkCmdCopyImage(cmd(), src->image.image, VK_IMAGE_LAYOUT_GENERAL, t.image.image, VK_IMAGE_LAYOUT_GENERAL, 1,
                           &region);
        }
    }
'''),
])
