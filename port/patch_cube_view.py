#!/usr/bin/env python3
"""patch_cube_view.py SMASH4_DIR : an image's default view of type CUBE covers 6 layers (a cube texture with more
faces - Mario Kart 8 has one with 48 - made an invalid view: VUID-VkImageViewCreateInfo-viewType-02960)."""
import sys
root = sys.argv[1]
p = root + '/runtime/src/gpu/vulkan/renderer.cpp'
s = open(p, encoding='utf-8').read()
OLD = '''    vci.subresourceRange = {aspect, 0, img.levels, 0, ici.arrayLayers};
    VK_CHECK(vkCreateImageView(ctx_.device, &vci, nullptr, &img.view));'''
NEW = '''    vci.subresourceRange = {aspect, 0, img.levels, 0, ici.arrayLayers};
    if (view_type == VK_IMAGE_VIEW_TYPE_CUBE && ici.arrayLayers >= 6) vci.subresourceRange.layerCount = 6; // port/patch_cube_view.py
    VK_CHECK(vkCreateImageView(ctx_.device, &vci, nullptr, &img.view));'''
if NEW not in s:
    if OLD not in s:
        sys.exit('patch_cube_view: text not found')
    s = s.replace(OLD, NEW, 1)
    open(p, 'w', encoding='utf-8').write(s)
