"""CAFE_RPL_REBASE=<code delta>,<data delta> (hex): load an RPL moved to free addresses (multi-module step 1).

A title's own modules (Mario Kart 8: mvplayer.rpl, mw_igr.rpl, mw_igr_sbc.rpl) are linked at the same addresses as
the title (.text at 0x02000000, data at 0x10000000). The console's loader moves each module to free memory and
applies its relocations there. This makes rpx::load do the same: every section at or above 0x10000000 moves by the
data delta, every other allocated section by the code delta, symbols move with their section, the entry point with
the code, and the relocations are then applied with the moved values. Unset, nothing changes.
Applied to the recompiler tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "recomp/src/rpx.cpp")
text = open(path, encoding="utf-8").read()
if "CAFE_RPL_REBASE" in text:
    sys.exit("already patched")


def sub(old, new):
    global text
    if text.count(old) != 1:
        sys.exit(f"not found once: {old[:70]!r}")
    text = text.replace(old, new)


sub("Image load(const std::vector<uint8_t>& raw, bool apply_relocations) {\n",
    "Image load(const std::vector<uint8_t>& raw, bool apply_relocations) {\n"
    "    // CAFE_RPL_REBASE=<code delta>,<data delta> (hex): a module moved to free addresses (port/patch_rpl_rebase.py).\n"
    "    uint32_t rebase_code = 0, rebase_data = 0;\n"
    "    if (const char* r = std::getenv(\"CAFE_RPL_REBASE\")) {\n"
    "        char* end = nullptr;\n"
    "        rebase_code = static_cast<uint32_t>(std::strtoul(r, &end, 16));\n"
    "        if (end && *end == ',') rebase_data = static_cast<uint32_t>(std::strtoul(end + 1, nullptr, 16));\n"
    "        std::fprintf(stderr, \"rpx: moving the module: code by 0x%08X, data by 0x%08X\\n\", rebase_code, rebase_data);\n"
    "    }\n"
    "    std::vector<uint32_t> section_delta;\n")

sub("        section.address = read_be32(header + 12);\n",
    "        section.address = read_be32(header + 12);\n"
    "        section_delta.resize(shnum, 0);\n"
    "        if (section.address != 0 && (rebase_code | rebase_data)) {\n"
    "            section_delta[index] = section.address >= 0x10000000u ? rebase_data : rebase_code;\n"
    "            section.address += section_delta[index];\n"
    "        }\n")

sub("    image.entry_point = read_be32(&raw[24]);\n",
    "    image.entry_point = read_be32(&raw[24]) + rebase_code;\n")

sub("        symbol.value = read_be32(entry + 4);\n",
    "        symbol.value = read_be32(entry + 4);\n"
    "        {\n"
    "            const uint16_t home = read_be16(entry + 14);\n"
    "            if (home != 0 && home < section_delta.size()) symbol.value += section_delta[home];\n"
    "        }\n")

if "#include <cstdlib>" not in text:
    text = "#include <cstdlib>\n#include <cstdio>\n" + text
open(path, "w", encoding="utf-8", newline="").write(text)
print("patched: recomp/src/rpx.cpp")
