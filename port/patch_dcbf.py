#!/usr/bin/env python3
"""dcbf in game code = "the CPU wrote this cache line" for the renderer.

usage: patch_dcbf.py SMASH4_DIR   (e.g. ~/wiiu/smash4; recompiler + runtime; regenerate a title's gen/ afterwards)

Before: the recompiler emitted dcbf/dcbst as nothing (host caches are coherent). Sochi 2014's font engine
(urals::scfont::TextureCache::UpdateTextureCache) draws new glyphs into its cache texture with the CPU and flushes
them with an inline dcbf loop, not DCFlushRange - so the renderer never re-read the texture and old glyphs stayed:
garbled text ("Flagewi" for "Zurueck"). After: dcbf calls cafe_ppc_dcbf(line) -> gpu::cpu_wrote(line, 32);
gpu::cpu_wrote joins a write that continues the previous one (a flush loop = one range).
dcbst stays a no-op (Sochi has ~19,900 of them, inlined store loops; dcbf only 4).
Titles translated before this keep the old behaviour until their gen/ is regenerated.
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])


def sub(path, old, new, count=1):
    p = root / path
    text = p.read_text()
    if new in text:
        print(f"{path}: already patched")
        return
    if text.count(old) != count:
        sys.exit(f"{path}: expected {count}x {old[:60]!r}, found {text.count(old)}")
    p.write_text(text.replace(old, new))
    print(f"{path}: ok")


sub("recomp/src/codegen.cpp", """        case Op::dcbf:
        case Op::dcbi:
        case Op::dcbst:
        case Op::dcbt:""", """        case Op::dcbf: // port/patch_dcbf.py: the CPU wrote this line (the renderer keeps GPU copies)
            line(text::format("ppc::dcbf({});", ea_x(ra, rb)));
            return;
        case Op::dcbi:
        case Op::dcbst:
        case Op::dcbt:""")

sub("runtime/include/cafe/ppc_ops.h", """uint64_t cafe_ppc_timebase(void);
}""", """uint64_t cafe_ppc_timebase(void);
void cafe_ppc_dcbf(uint32_t line_address); // port/patch_dcbf.py
}""")

sub("runtime/include/cafe/ppc_ops.h", """inline void dcbz(uint8_t* base, uint32_t ea) {""", """// port/patch_dcbf.py: a data cache flush = CPU-written data the GPU may hold a copy of
inline void dcbf(uint32_t ea) { cafe_ppc_dcbf(ea & ~31u); }

inline void dcbz(uint8_t* base, uint32_t ea) {""")

sub("runtime/src/diagnostics.cpp", """#include "cafe/runtime.h"
""", """#include "cafe/runtime.h"
#include "gpu/gpu.h" // port/patch_dcbf.py
""")

sub("runtime/src/diagnostics.cpp", """uint64_t cafe_ppc_timebase(void) {""", """void cafe_ppc_dcbf(uint32_t line_address) { cafe::gpu::cpu_wrote(line_address, 32); } // port/patch_dcbf.py

uint64_t cafe_ppc_timebase(void) {""")

sub("runtime/src/gpu/command_processor.cpp", """    if (size == 0) return;
    std::lock_guard lock(g_written_mutex);
    g_written.emplace_back(address, size);""", """    if (size == 0) return;
    std::lock_guard lock(g_written_mutex);
    // port/patch_dcbf.py: a flush loop (dcbf line by line) continues the previous range
    if (!g_written.empty() && uint64_t{g_written.back().first} + g_written.back().second == address &&
        g_written.back().second < (1u << 20)) {
        g_written.back().second += size;
        return;
    }
    g_written.emplace_back(address, size);""")
