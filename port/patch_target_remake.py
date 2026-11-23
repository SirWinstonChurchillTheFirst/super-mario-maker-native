#!/usr/bin/env python3
"""patch_target_remake.py SMASH4_DIR : two faults Vulkan's validation layer showed in Mario Tennis Ultra Smash.

1. A render target remade at another size copied its old picture with the OLD size as the destination corner. When
   the new image is smaller (Tennis at match start: a 1280 wide R16F target remade 1024x1024) the copy wrote outside
   the image: "vkCmdBlitImage dstOffsets exceed the extent", and on the NVIDIA driver a device fault
   ("invalid write at 0x0", vkQueueSubmit -4) that ended the program. Now only the part both images hold is copied.
2. Format 1_5_5_5 used VK_FORMAT_A1B5G5R5_UNORM_PACK16, which needs VK_KHR_maintenance5 as an enabled extension
   (the runtime does not enable it; the driver still reports the format as supported). The runtime's own other path
   (A1R5G5B5 with red and blue swapped in the view) needs no extension and is used always now."""
import sys

root = sys.argv[1] + '/runtime/src/gpu/vulkan/'


def patch(path, pairs, marker):
    p = root + path
    s = open(p, encoding='utf-8').read()
    if marker in s:
        print('patch_target_remake: already there:', path)
        return
    for old, new in pairs:
        if old not in s:
            sys.exit('patch_target_remake: text not found in %s: %r' % (path, old[:60]))
        s = s.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(s)
    print('patch_target_remake: done:', path)


patch('targets.cpp', [(
    '    blit.srcOffsets[1] = {static_cast<int32_t>(old.width), static_cast<int32_t>(old.height), 1};\n'
    '    blit.dstOffsets[1] = {static_cast<int32_t>(old.width * scale / t.scale), static_cast<int32_t>(old.height * scale / t.scale), 1};\n',
    '    // Only what both images hold (port/patch_target_remake.py): the new one may be the smaller.\n'
    '    const float remake_ratio = scale / t.scale;\n'
    '    const uint32_t copy_w = std::min(old.width, static_cast<uint32_t>(t.image.width / remake_ratio));\n'
    '    const uint32_t copy_h = std::min(old.height, static_cast<uint32_t>(t.image.height / remake_ratio));\n'
    '    blit.srcOffsets[1] = {static_cast<int32_t>(copy_w), static_cast<int32_t>(copy_h), 1};\n'
    '    blit.dstOffsets[1] = {static_cast<int32_t>(std::min<uint32_t>(static_cast<uint32_t>(copy_w * remake_ratio), t.image.width)),\n'
    '                          static_cast<int32_t>(std::min<uint32_t>(static_cast<uint32_t>(copy_h * remake_ratio), t.image.height)), 1};\n',
)], 'remake_ratio')

patch('formats.cpp', [(
    '    g_a1b5g5r5 = supported(physical, VK_FORMAT_A1B5G5R5_UNORM_PACK16_KHR, sampled);\n',
    '    // Needs VK_KHR_maintenance5 enabled, which the runtime does not do (port/patch_target_remake.py): the\n'
    '    // A1R5G5B5 path with swapped channels is used on every device.\n'
    '    g_a1b5g5r5 = false;\n',
)], 'patch_target_remake.py')
