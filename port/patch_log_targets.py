#!/usr/bin/env python3
"""patch_log_targets.py SMASH4_DIR : TTT2_LOG_TARGETS=1 prints every new colour target (address, format, size, tile
mode) and every first draw into a 3D/array slice > 0 - for finding which pass makes a texture (debugging)."""
import sys
root = sys.argv[1]


def edit(path, pairs):
    p = root + '/' + path
    s = open(p, encoding='utf-8').read()
    for old, new in pairs:
        if new in s:
            continue
        if old not in s:
            sys.exit('patch_log_targets: text not found in %s: %r' % (path, old[:70]))
        s = s.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(s)


edit('runtime/src/gpu/vulkan/targets.cpp', [
    ('''    auto t = std::make_unique<Target>();
    t->address = address;
    t->format = format;
    t->pitch = pitch;
    t->height = height;
    t->tile_mode = tile_mode;
    t->base_reg = base_reg;
''', '''    if (static const bool log = std::getenv("TTT2_LOG_TARGETS") != nullptr; log) { // port/patch_log_targets.py
        std::fprintf(stderr, "ttt2: new colour target 0x%08X fmt 0x%03X %ux%u tile %u (frame %llu)\\n", address, format,
                     pitch, height, tile_mode, static_cast<unsigned long long>(frame_number_));
    }
    auto t = std::make_unique<Target>();
    t->address = address;
    t->format = format;
    t->pitch = pitch;
    t->height = height;
    t->tile_mode = tile_mode;
    t->base_reg = base_reg;
'''),
])

# TTT2_LOG_TARGETS=3 also traces every draw into a thick-tiled (3D) target, and any value logs slice draws.
edit('runtime/src/gpu/vulkan/renderer.h', [
    ('    bool tracing() const { return frame_number_ == trace_frame_; }',
     '    bool tracing() const { return frame_number_ == trace_frame_ || trace_this_draw_; }\n'
     '    bool trace_this_draw_ = false; // port/patch_log_targets.py: TTT2_LOG_TARGETS=3 traces draws into tile-3 (thick) targets'),
])
edit('runtime/src/gpu/vulkan/draw.cpp', [
    ('''    const uint32_t depth_control = r(reg::DB_DEPTH_CONTROL);
    const Target* depth = nullptr;''', '''    { // port/patch_log_targets.py
        static const char* lt = std::getenv("TTT2_LOG_TARGETS");
        trace_this_draw_ = false;
        for (uint32_t i = 0; lt && *lt == '3' && i < 8; ++i) {
            if (colors[i] && (colors[i]->tile_mode == 3 || colors[i]->tile_mode == 7)) trace_this_draw_ = true;
        }
    }
    const uint32_t depth_control = r(reg::DB_DEPTH_CONTROL);
    const Target* depth = nullptr;'''),
    ('''            base += slice * slice_key_bytes(pitch, height, bytes, tile) >> 8;
''', r'''            base += slice * slice_key_bytes(pitch, height, bytes, tile) >> 8;
            if (static const bool log = std::getenv("TTT2_LOG_TARGETS") != nullptr; log) {
                std::fprintf(stderr, "ttt2: slice draw: cb%u base 0x%08X slice %u (frame %llu, draw %llu)\n", t,
                             r(reg::CB_COLOR0_BASE + t * 4) << 8, slice, static_cast<unsigned long long>(frame_number_),
                             static_cast<unsigned long long>(draws_));
            }
'''),
])
