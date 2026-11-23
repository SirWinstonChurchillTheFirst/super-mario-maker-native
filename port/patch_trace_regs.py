#!/usr/bin/env python3
"""patch_trace_regs.py SMASH4_DIR : a traced draw (TTT2_TRACE_AT) also prints the uniform REGISTERS the shaders use
(VS c[0..19], PS c[0..7], as floats and hex) - for titles that draw with GX2Set*UniformReg (Mario Kart 8)."""
import sys
root = sys.argv[1]
p = root + '/runtime/src/gpu/vulkan/draw.cpp'
s = open(p, encoding='utf-8').read()
OLD = '''        trace_textures(vs, resource::kVsTexture, "vs");
        trace_textures(ps, resource::kPsTexture, "ps");
'''
NEW = OLD + '''        { // port/patch_trace_regs.py
            auto dump_regs = [&](const char* which, uint32_t base, uint32_t n) {
                for (uint32_t i = 0; i < n; ++i) {
                    const uint32_t* v = &regs.value[(base >> 2) + i * 4];
                    std::fprintf(stderr, "trace:   %s c[%u] %g %g %g %g (%08X %08X %08X %08X)\\n", which, i,
                                 std::bit_cast<float>(v[0]), std::bit_cast<float>(v[1]), std::bit_cast<float>(v[2]),
                                 std::bit_cast<float>(v[3]), v[0], v[1], v[2], v[3]);
                }
            };
            std::fprintf(stderr, "trace:   uses registers: vs %d ps %d, sq_config 0x%08X\\n", vs->info.uses_registers ? 1 : 0,
                         ps->info.uses_registers ? 1 : 0, r(reg::SQ_CONFIG));
            if (vs->info.uses_registers) dump_regs("vs", reg::SQ_ALU_CONSTANT0_256, 20);
            if (ps->info.uses_registers) dump_regs("ps", reg::SQ_ALU_CONSTANT0_0, 8);
        }
'''
if NEW not in s:
    if OLD not in s:
        sys.exit('patch_trace_regs: text not found')
    s = s.replace(OLD, NEW, 1)
    open(p, 'w', encoding='utf-8').write(s)

# Uniform BLOCKS too: the first 12 vec4 of each block bank the shaders read, from guest memory at draw time.
s = open(p, encoding='utf-8').read()
OLD2 = '''            if (vs->info.uses_registers) dump_regs("vs", reg::SQ_ALU_CONSTANT0_256, 20);'''
NEW2 = OLD2 + r'''
            for (uint32_t bank = 0; bank < 16; ++bank) {
                for (int stage = 0; stage < 2; ++stage) {
                    const ShaderModule* sm = stage == 0 ? vs : ps;
                    if (!((sm->info.constant_bank_mask >> bank) & 1)) continue;
                    const uint32_t a = r((stage == 0 ? reg::SQ_ALU_CONST_CACHE_VS_0 : reg::SQ_ALU_CONST_CACHE_PS_0) + bank * 4) << 8;
                    std::fprintf(stderr, "trace:   %s block %u at 0x%08X\n", stage == 0 ? "vs" : "ps", bank, a);
                    if (a == 0 || !guest_memory_committed(a, 12 * 16)) continue;
                    for (uint32_t i = 0; i < 12; ++i) {
                        float f[4];
                        for (int k = 0; k < 4; ++k) {
                            uint32_t w = __builtin_bswap32(*reinterpret_cast<const uint32_t*>(guest_pointer(a + i * 16 + k * 4)));
                            f[k] = std::bit_cast<float>(w);
                        }
                        std::fprintf(stderr, "trace:   %s kc(%u,%u) %g %g %g %g\n", stage == 0 ? "vs" : "ps", bank, i, f[0], f[1], f[2], f[3]);
                    }
                }
            }'''
if NEW2 not in s:
    if OLD2 not in s:
        sys.exit('patch_trace_regs: block text not found')
    s = s.replace(OLD2, NEW2, 1)
    open(p, 'w', encoding='utf-8').write(s)
