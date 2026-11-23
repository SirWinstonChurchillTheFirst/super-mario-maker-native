#!/usr/bin/env python3
"""patch_reload_targets.py RUNTIME_SRC_DIR (…/runtime/src)

TTT2_RELOAD_TARGETS=1: before a draw into a colour target whose guest memory the CPU wrote after the GPU last drew
into it, the memory is loaded into the target image (through the texture loader, retiled), as on the console where
the target IS that memory. Super Mario Maker writes its static terrain tiles (the ground) into the 256x256 tile
atlas 0x47C50800 with the CPU and draws only the animated cells with the GPU every frame; the runtime's atlas image
never had the CPU part, so the ground was invisible. Only targets drawn at scale 1 and at most 4 MiB. Off by default
(a title that flushes memory over live targets without meaning to write them would lose GPU content)."""
import sys

src = sys.argv[1]


def patch(rel, pairs):
    p = src + "/" + rel
    s = open(p, encoding="utf-8").read()
    if "patch_reload_targets" in s:
        print(rel + ": already applied")
        return
    for old, new in pairs:
        assert s.count(old) == 1, rel + ": pattern not found or not unique: " + old[:80]
        s = s.replace(old, new)
    open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("patched", p)


patch("gpu/vulkan/renderer.h", [(
    "    Texture* texture(const uint32_t words[7]);\n",
    "    Texture* texture(const uint32_t words[7]);\n"
    "    void reload_target(Target& t); // port/patch_reload_targets.py\n")])

patch("gpu/vulkan/targets.cpp", [(
    "Target* Renderer::color_target(const gx2::ColorBuffer& buffer) {\n",
    "// port/patch_reload_targets.py: the target's guest memory (newer than its image) into its image.\n"
    "void Renderer::reload_target(Target& t) {\n"
    "    const uint32_t hw = t.format & 0x3F;\n"
    "    const uint32_t comp = (t.format & gx2::attrib_format::kSigned) ? 1 : 0;\n"
    "    const uint32_t num = (t.format & gx2::attrib_format::kScaled) ? 2 : (t.format & gx2::attrib_format::kInteger) ? 1 : 0;\n"
    "    uint32_t words[7];\n"
    "    words[0] = 1u /* 2D */ | (t.tile_mode << 3) | ((std::max(t.pitch, 8u) / 8 - 1) << 8) | ((t.pitch - 1) << 19);\n"
    "    words[1] = (t.height - 1) | (hw << 26);\n"
    "    words[2] = t.base_reg;\n"
    "    words[3] = t.base_reg;\n"
    "    words[4] = comp | (comp << 2) | (comp << 4) | (comp << 6) | (num << 8) |\n"
    "               (((t.format & gx2::attrib_format::kDegamma) != 0 ? 1u : 0u) << 11) | (2u << 14) |\n"
    "               (0u << 16) | (1u << 19) | (2u << 22) | (3u << 25);\n"
    "    words[5] = 0;\n"
    "    words[6] = (4u << 2) | (7u << 5) | resource::kTypeValidTexture;\n"
    "    const Texture* x = texture(words);\n"
    "    if (x == nullptr || x->source != nullptr || x->image.image == VK_NULL_HANDLE) return; // not from memory\n"
    "    end_rendering();\n"
    "    barrier();\n"
    "    VkImageCopy region{};\n"
    "    region.srcSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};\n"
    "    region.dstSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};\n"
    "    region.extent = {std::min(x->image.width, t.image.width), std::min(x->image.height, t.image.height), 1};\n"
    "    vkCmdCopyImage(cmd(), x->image.image, VK_IMAGE_LAYOUT_GENERAL, t.image.image, VK_IMAGE_LAYOUT_GENERAL, 1, &region);\n"
    "    barrier();\n"
    "    t.written = stamp();\n"
    "    static int said = 0;\n"
    "    if (said++ < 20) {\n"
    "        std::fprintf(stderr, \"ttt2: gpu: target 0x%08X %ux%u fmt 0x%03X reloaded from guest memory (the CPU wrote it)\\n\",\n"
    "                     t.address, t.pitch, t.height, t.format);\n"
    "    }\n"
    "}\n"
    "\n"
    "Target* Renderer::color_target(const gx2::ColorBuffer& buffer) {\n")])

patch("gpu/vulkan/draw.cpp", [(
    "    const uint32_t depth_control = r(reg::DB_DEPTH_CONTROL);\n    const Target* depth = nullptr;\n",
    "    // port/patch_reload_targets.py: CPU-written memory under a colour target first goes into its image.\n"
    "    if (static const bool reload = std::getenv(\"TTT2_RELOAD_TARGETS\") != nullptr && std::atoi(std::getenv(\"TTT2_RELOAD_TARGETS\")) != 0;\n"
    "        reload && !replaying_) {\n"
    "        for (uint32_t i = 0; i < color_count; ++i) {\n"
    "            Target* t = const_cast<Target*>(colors[i]);\n"
    "            if (t && t->overwritten > t->written && t->scale == 1 && !t->depth &&\n"
    "                uint64_t{t->pitch} * t->height * 4 <= (4u << 20)) {\n"
    "                reload_target(*t);\n"
    "            }\n"
    "        }\n"
    "    }\n"
    "    const uint32_t depth_control = r(reg::DB_DEPTH_CONTROL);\n    const Target* depth = nullptr;\n")])

# A new colour target starts from its guest memory too (the CPU may have written it before the GPU first drew).
p = src + "/gpu/vulkan/targets.cpp"
s = open(p, encoding="utf-8").read()
old = """    targets_sorted_[t->address].push_back(t.get());
    max_target_span_ = std::max(max_target_span_, t->end - t->address);
    targets_.push_back(std::move(t));
    return targets_.back().get();
}

// port/patch_reload_targets.py"""
new = """    targets_sorted_[t->address].push_back(t.get());
    max_target_span_ = std::max(max_target_span_, t->end - t->address);
    if (static const bool reload = std::getenv("TTT2_RELOAD_TARGETS") != nullptr && std::atoi(std::getenv("TTT2_RELOAD_TARGETS")) != 0;
        reload) {
        t->overwritten = stamp(); // port/patch_reload_targets.py: its memory first
    }
    targets_.push_back(std::move(t));
    return targets_.back().get();
}

// port/patch_reload_targets.py"""
if "its memory first" not in s:
    assert s.count(old) == 1, "new-target pattern not found"
    s = s.replace(old, new)
    open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("patched new targets")
