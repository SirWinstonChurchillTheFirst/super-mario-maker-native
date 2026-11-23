#!/usr/bin/env python3
"""patch_reg_extent.py RUNTIME_SRC_DIR (…/runtime/src)

Uniform-register mode: every draw copied both 4 KiB register files into the upload ring. Super Mario Maker draws
~420 times a frame in that mode (~3.4 MB a frame); on the console's APU the ring is write-combined memory and the
command processor thread spent ~20 ms a frame (PC: 2 ms), 26-38 fps. The translator now records how far a shader
reads the register file (relative indexing: all of it) and only that much is copied; the bound range stays 4 KiB.
TTT2_FULL_REG_UPLOAD=1 = old behaviour."""
import sys

src = sys.argv[1]


def patch(rel, pairs):
    p = src + "/" + rel
    s = open(p, encoding="utf-8").read()
    if "patch_reg_extent" in s:
        print(rel + ": already applied")
        return
    for old, new in pairs:
        assert s.count(old) == 1, rel + ": pattern not found or not unique: " + old[:80]
        s = s.replace(old, new)
    open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("patched", p)


patch("latte/translate.h", [(
    "    bool uses_registers = false; // reads the uniform register binding\n",
    "    bool uses_registers = false; // reads the uniform register binding\n"
    "    uint32_t register_extent = 4096; // bytes of it read from its start (port/patch_reg_extent.py)\n")])

patch("latte/translate.cpp", [
    ("    bool uses_registers_ = false;\n",
     "    bool uses_registers_ = false;\n"
     "    uint32_t register_extent_ = 0; // port/patch_reg_extent.py\n"),
    ("            return format(\"int(regs.c[(%u + %s) & 255].%c)\", index, index_register(in.index_mode).c_str(), c);\n",
     "            register_extent_ = 4096; // port/patch_reg_extent.py: relative: all of it\n"
     "            return format(\"int(regs.c[(%u + %s) & 255].%c)\", index, index_register(in.index_mode).c_str(), c);\n"),
    ("        return format(\"int(regs.c[%u].%c)\", index, c);\n",
     "        register_extent_ = std::max<uint32_t>(register_extent_, std::min<uint32_t>(index + 1, 256) * 16); // port/patch_reg_extent.py\n"
     "        return format(\"int(regs.c[%u].%c)\", index, c);\n"),
    ("    out_.uses_registers = uses_registers_;\n",
     "    out_.uses_registers = uses_registers_;\n"
     "    out_.register_extent = register_extent_ ? register_extent_ : 4096; // port/patch_reg_extent.py\n"),
])

patch("gpu/vulkan/draw.cpp", [
    ("        std::memcpy(upload(4096, ubo_align, reg_offset[0]), &regs.value[reg::SQ_ALU_CONSTANT0_256 >> 2], 4096);\n",
     "        // port/patch_reg_extent.py: only what the shader reads (the ring is write-combined on an APU)\n"
     "        static const bool full = std::getenv(\"TTT2_FULL_REG_UPLOAD\") != nullptr;\n"
     "        std::memcpy(upload(4096, ubo_align, reg_offset[0]), &regs.value[reg::SQ_ALU_CONSTANT0_256 >> 2],\n"
     "                    full ? 4096 : std::min<uint32_t>(vs->info.register_extent, 4096));\n"),
    ("        std::memcpy(upload(4096, ubo_align, reg_offset[1]), &regs.value[reg::SQ_ALU_CONSTANT0_0 >> 2], 4096);\n",
     "        static const bool full = std::getenv(\"TTT2_FULL_REG_UPLOAD\") != nullptr; // port/patch_reg_extent.py\n"
     "        std::memcpy(upload(4096, ubo_align, reg_offset[1]), &regs.value[reg::SQ_ALU_CONSTANT0_0 >> 2],\n"
     "                    full ? 4096 : std::min<uint32_t>(ps->info.register_extent, 4096));\n"),
])
