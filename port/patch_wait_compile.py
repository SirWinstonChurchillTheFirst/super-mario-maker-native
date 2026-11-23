#!/usr/bin/env python3
"""patch_wait_compile.py SMASH4_DIR : draws into slices of 3D/array/cube surfaces or thick-tiled targets wait for
their shaders and pipeline instead of being dropped while those still compile.

With asynchronous compiling a draw whose shader or pipeline is not ready is skipped ("deferred"). That is harmless
for things drawn every frame, but Mario Kart 8 draws its colour-grading LUT (8x8x8, 8 slices in one MRT draw) once
when a race loads: the draw was dropped, the LUT stayed black, so was every race picture. Such one-time setup draws
render into slices (CB_COLORn_VIEW slice > 0) or thick-tiled (3D) targets; those now wait. TTT2_WAIT_COMPILE=0 never
waits, =1 waits for every draw (debugging). Needs patch_slice_targets.py (the slice loop) first."""
import sys
root = sys.argv[1]


def edit(path, pairs):
    p = root + '/' + path
    s = open(p, encoding='utf-8').read()
    for old, new in pairs:
        if new in s:
            continue
        if old not in s:
            sys.exit('patch_wait_compile: text not found in %s: %r' % (path, old[:70]))
        s = s.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(s)


edit('runtime/src/gpu/vulkan/draw.cpp', [
    ('''    std::array<const Target*, 8> colors{};
    uint32_t color_count = 0;
''', '''    std::array<const Target*, 8> colors{};
    uint32_t color_count = 0;
    bool must_draw = false; // port/patch_wait_compile.py: a one-time setup draw (slices, thick targets)
'''),
    ('''        if (slice != 0 && slice_targets_enabled()) {
            const uint32_t size_reg''', '''        if (slice != 0) must_draw = true;
        if (((info >> 8) & 0xF) == 3 || ((info >> 8) & 0xF) == 7) must_draw = true;
        if (slice != 0 && slice_targets_enabled()) {
            const uint32_t size_reg'''),
    ('''    if (vs->module == VK_NULL_HANDLE || ps->module == VK_NULL_HANDLE) {
        ++deferred_draws_; // a shader still compiling
''', '''    static const int wait_mode = [] {
        const char* v = std::getenv("TTT2_WAIT_COMPILE");
        return v == nullptr ? 2 : std::atoi(v);
    }();
    const bool wait_compile = wait_mode == 1 || (wait_mode == 2 && must_draw);
    if (wait_compile) {
        for (int spin = 0; spin < 20000 && (vs->module == VK_NULL_HANDLE || ps->module == VK_NULL_HANDLE) &&
                           !vs->failed && !ps->failed;
             ++spin) {
            std::this_thread::sleep_for(std::chrono::microseconds(250));
            if (vs->module == VK_NULL_HANDLE) resolve_module(*const_cast<ShaderModule*>(vs));
            if (ps->module == VK_NULL_HANDLE) resolve_module(*const_cast<ShaderModule*>(ps));
        }
    }
    if (vs->module == VK_NULL_HANDLE || ps->module == VK_NULL_HANDLE) {
        ++deferred_draws_; // a shader still compiling
'''),
    ('''    if (pipe->state.load() != Built::kReady) {
        ++deferred_draws_; // its pipeline still compiling
''', '''    if (wait_compile) {
        for (int spin = 0; spin < 40000 && pipe->state.load() == Built::kPending; ++spin) {
            std::this_thread::sleep_for(std::chrono::microseconds(250));
        }
    }
    if (pipe->state.load() != Built::kReady) {
        ++deferred_draws_; // its pipeline still compiling
'''),
])
