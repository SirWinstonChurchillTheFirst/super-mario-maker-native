#!/usr/bin/env python3
"""patch_log_scancopy.py RUNTIME_SRC_DIR : TTT2_LOG_SCANCOPY=1 prints the first 40 GX2CopyColorBufferToScanBuffer calls
(target, image address, format, size, pitch) - debugging a black GamePad picture."""
import sys

p = sys.argv[1] + "/gx2/display.cpp"
s = open(p, encoding="utf-8").read()
old = """void GX2CopyColorBufferToScanBuffer(ColorBuffer* buffer, uint32_t target) {
    ApiLock lock;
"""
new = """void GX2CopyColorBufferToScanBuffer(ColorBuffer* buffer, uint32_t target) {
    ApiLock lock;
    if (static const bool log = std::getenv("TTT2_LOG_SCANCOPY") != nullptr; log) { // port/patch_log_scancopy.py
        static int n = 0;
        if (n++ < 40) {
            std::fprintf(stderr, "scancopy: target %u image 0x%08X format 0x%03X %ux%u pitch %u aa %u tile %u mip %u\\n", target,
                         static_cast<uint32_t>(buffer->surface.image), static_cast<uint32_t>(buffer->surface.format),
                         static_cast<uint32_t>(buffer->surface.width), static_cast<uint32_t>(buffer->surface.height),
                         static_cast<uint32_t>(buffer->surface.pitch), static_cast<uint32_t>(buffer->surface.aa),
                         static_cast<uint32_t>(buffer->surface.tile_mode), static_cast<uint32_t>(buffer->view_mip));
        }
    }
"""
if "patch_log_scancopy" in s:
    print("already applied"); sys.exit(0)
assert old in s, "pattern not found"
s = s.replace(old, new)
for inc in ("#include <cstdio>", "#include <cstdlib>"):
    if inc not in s:
        s = s.replace("#include", inc + "\n#include", 1)
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched", p)
