#!/usr/bin/env python3
"""Trace prints uniform blocks as the GPU (and the translated shaders' kc()) reads them: little-endian words,
plus the raw hex. The old print byte-swapped them, which made correct GX2 uniform blocks (the title stores them
GPU-endian) look like garbage. usage: patch_trace_le.py RUNTIME_SRC_DIR (…/runtime/src)"""
import sys

p = sys.argv[1] + "/gpu/vulkan/draw.cpp"
s = open(p, encoding="utf-8").read()
old = """                        float f[4];
                        for (int k = 0; k < 4; ++k) {
                            uint32_t w = __builtin_bswap32(*reinterpret_cast<const uint32_t*>(guest_pointer(a + i * 16 + k * 4)));
                            f[k] = std::bit_cast<float>(w);
                        }
                        std::fprintf(stderr, "trace:   %s kc(%u,%u) %g %g %g %g\\n", stage == 0 ? "vs" : "ps", bank, i, f[0], f[1], f[2], f[3]);"""
new = """                        float f[4];
                        uint32_t wv[4];
                        for (int k = 0; k < 4; ++k) {
                            wv[k] = *reinterpret_cast<const uint32_t*>(guest_pointer(a + i * 16 + k * 4)); // GPU order (LE)
                            f[k] = std::bit_cast<float>(wv[k]);
                        }
                        std::fprintf(stderr, "trace:   %s kc(%u,%u) %g %g %g %g (%08X %08X %08X %08X)\\n", stage == 0 ? "vs" : "ps",
                                     bank, i, f[0], f[1], f[2], f[3], wv[0], wv[1], wv[2], wv[3]);"""
if new in s:
    print("already applied"); sys.exit(0)
assert old in s, "pattern not found"
s = s.replace(old, new)
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched", p)
