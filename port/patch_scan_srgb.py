"""The TV/GamePad image gets the scan buffer's own sRGB encoding (Wii U games looked too dark).

A title declares its scan buffers with GX2SetTVBuffer/GX2SetDRCBuffer; Super Mario 3D World and Mario Tennis Ultra
Smash declare format 0x41A (8-bit sRGB) but render the frame into a 10-bit UNORM colour buffer holding LINEAR values.
On the console's GPU GX2CopyColorBufferToScanBuffer converts into the scan buffer's format, i.e. sRGB-encodes the
values; Cemu does the same (output shader: applySRGBEncoding = TV buffer format has the sRGB bit). The runtime copied
the colour buffer byte for byte and showed linear values: the picture came out much too dark (measured on the console,
title screen of 3D World, 22 November: native mean RGB 106/148/117, Cemu 154/194/154).
Now copy_to_scan_buffer blits (converts) into an 8-bit image of the declared kind when the colour buffer's sRGB-ness
differs from the declared scan format; same kind keeps the exact copy. Both present paths copy the scan image's bytes
unchanged, so the encoding reaches the screen. TTT2_SCAN_RAW=1 restores the old byte copy (A/B).
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
SRC = os.path.join(ROOT, "runtime/src")


def patch(rel, pairs):
    path = os.path.join(SRC, rel)
    text = open(path, encoding="utf-8").read()
    if "patch_scan_srgb" in text:
        print("already:", rel)
        return
    for old, new in pairs:
        if text.count(old) != 1:
            sys.exit(f"{rel}: anchor not found once: {old[:60]!r}")
        text = text.replace(old, new)
    open(path, "w", encoding="utf-8", newline="").write(text)
    print("patched:", rel)


patch("gpu/gpu.h", [(
    "void set_tv_height(uint32_t rows);\nuint32_t tv_height();\n",
    "void set_tv_height(uint32_t rows);\nuint32_t tv_height();\n"
    "\n"
    "// The GX2 surface format a title declared for a scan buffer (0 TV, 1 GamePad), from GX2SetTVBuffer /\n"
    "// GX2SetDRCBuffer: its sRGB bit decides whether the copy into it encodes (port/patch_scan_srgb.py). Any thread.\n"
    "void set_scan_format(int index, uint32_t format);\n"
    "uint32_t scan_format(int index);\n")])

patch("gpu/vulkan/renderer.cpp", [
    ("uint32_t tv_height() { return g_tv_height; }\n",
     "uint32_t tv_height() { return g_tv_height; }\n"
     "\n"
     "// port/patch_scan_srgb.py\n"
     "namespace {\n"
     "std::atomic<uint32_t> g_scan_format[2]{};\n"
     "} // namespace\n"
     "void set_scan_format(int index, uint32_t format) { g_scan_format[index & 1] = format; }\n"
     "uint32_t scan_format(int index) { return g_scan_format[index & 1]; }\n"),
    ("    Image& scan = scan_[index];\n"
     "    if (scan.image == VK_NULL_HANDLE || scan.width != width || scan.height != height || scan.format != t->image.format) {\n",
     "    Image& scan = scan_[index];\n"
     "    // The declared scan format's kind (GX2 format bit 0x400 = sRGB): a colour buffer of the other kind is converted\n"
     "    // as the console's copy does (linear values into an sRGB scan buffer are encoded), else copied as it is\n"
     "    // (port/patch_scan_srgb.py).\n"
     "    static const bool raw = std::getenv(\"TTT2_SCAN_RAW\") != nullptr;\n"
     "    const uint32_t declared = scan_format(index);\n"
     "    const auto is_srgb = [](VkFormat f) {\n"
     "        return f == VK_FORMAT_R8G8B8A8_SRGB || f == VK_FORMAT_B8G8R8A8_SRGB || f == VK_FORMAT_A8B8G8R8_SRGB_PACK32;\n"
     "    };\n"
     "    const bool want_srgb = (declared & 0x400) != 0;\n"
     "    const bool convert = !raw && declared != 0 && want_srgb != is_srgb(t->image.format);\n"
     "    const VkFormat scan_fmt = !convert ? t->image.format : want_srgb ? VK_FORMAT_R8G8B8A8_SRGB : VK_FORMAT_R8G8B8A8_UNORM;\n"
     "    if (convert) {\n"
     "        static bool said[2];\n"
     "        if (!said[index]) {\n"
     "            said[index] = true;\n"
     "            std::fprintf(stderr, \"ttt2: GPU: %s scan buffer declared 0x%03X, colour buffer vk format %d: %s on the copy\\n\",\n"
     "                         index ? \"GamePad\" : \"TV\", declared, static_cast<int>(t->image.format),\n"
     "                         want_srgb ? \"sRGB-encoded\" : \"sRGB-decoded\");\n"
     "        }\n"
     "    }\n"
     "    if (scan.image == VK_NULL_HANDLE || scan.width != width || scan.height != height || scan.format != scan_fmt) {\n"),
    ("        scan = create_image(t->image.format, VK_IMAGE_ASPECT_COLOR_BIT, width, height, 1, 1,\n",
     "        scan = create_image(scan_fmt, VK_IMAGE_ASPECT_COLOR_BIT, width, height, 1, 1,\n"),
    ("    region.extent = {width, height, 1};\n"
     "    vkCmdCopyImage(cmd(), t->image.image, VK_IMAGE_LAYOUT_GENERAL, scan.image, VK_IMAGE_LAYOUT_GENERAL, 1, &region);\n"
     "    barrier();\n"
     "    scan_valid_[index] = true;\n",
     "    region.extent = {width, height, 1};\n"
     "    if (convert) {\n"
     "        VkImageBlit blit{};\n"
     "        blit.srcSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};\n"
     "        blit.dstSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};\n"
     "        blit.srcOffsets[1] = {static_cast<int32_t>(width), static_cast<int32_t>(height), 1};\n"
     "        blit.dstOffsets[1] = blit.srcOffsets[1];\n"
     "        vkCmdBlitImage(cmd(), t->image.image, VK_IMAGE_LAYOUT_GENERAL, scan.image, VK_IMAGE_LAYOUT_GENERAL, 1, &blit,\n"
     "                       VK_FILTER_NEAREST);\n"
     "    } else {\n"
     "        vkCmdCopyImage(cmd(), t->image.image, VK_IMAGE_LAYOUT_GENERAL, scan.image, VK_IMAGE_LAYOUT_GENERAL, 1, &region);\n"
     "    }\n"
     "    barrier();\n"
     "    scan_valid_[index] = true;\n"),
])

patch("gx2/display.cpp", [
    ("    if (mode < std::size(kTvSizes)) gpu::set_tv_height(kTvSizes[mode].height);\n",
     "    if (mode < std::size(kTvSizes)) gpu::set_tv_height(kTvSizes[mode].height);\n"
     "    gpu::set_scan_format(0, format); // port/patch_scan_srgb.py\n"),
    ("    g_drc.buffering = buffering;\n",
     "    g_drc.buffering = buffering;\n"
     "    gpu::set_scan_format(1, format); // port/patch_scan_srgb.py\n"),
])
