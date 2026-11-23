#!/usr/bin/env python3
"""patch_rects2.py SMASH4_DIR : rectangle lists WITH an index buffer (after patch_rects.py).

Mario Tennis Ultra Smash draws its rectangles through an index buffer, which patch_rects.py still skipped. The
indices are converted to 32-bit host order as for any indexed draw; instead of binding them as an index buffer the
draw passes their place to the vertex shader (in the draw constants' fourth stream-out slot, which a rectangle draw
does not use), and the shader looks each of the rectangle's three vertices up there."""
import sys

root = sys.argv[1] + '/runtime/src/'


def patch(path, pairs, marker):
    p = root + path
    s = open(p, encoding='utf-8').read()
    if marker in s:
        print('patch_rects2: already there:', path)
        return
    for old, new in pairs:
        if old not in s:
            sys.exit('patch_rects2: text not found in %s: %r' % (path, old[:60]))
        s = s.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(s)
    print('patch_rects2: done:', path)


patch('latte/translate.cpp', [(
    '        std::string m = "int rect_vertex;\\nvoid rect_body() {\\n" + init + main_vars + main_body + "}\\n";\n',
    '        std::string m = "int rect_vertex;\\n"\n'
    '                        "int rect_index(int i) { return dc.so[3].z != 0u ? int(gload(dc.so[3], uint(i) * 4u, 4u)) : i; }\\n"\n'
    '                        "void rect_body() {\\n" + init + main_vars + main_body + "}\\n";\n',
), (
    '        m += "    if (rj < 3) { rect_vertex = rq * 3 + rj; rect_body(); return; }\\n";\n',
    '        m += "    if (rj < 3) { rect_vertex = rect_index(rq * 3 + rj); rect_body(); return; }\\n";\n',
), (
    '        m += "    for (int i = 0; i < 3; ++i) {\\n        rect_vertex = rq * 3 + i;\\n        rect_body();\\n        rp[i] = gl_Position;\\n";\n',
    '        m += "    for (int i = 0; i < 3; ++i) {\\n        rect_vertex = rect_index(rq * 3 + i);\\n        rect_body();\\n        rp[i] = gl_Position;\\n";\n',
)], 'rect_index')

patch('gpu/vulkan/draw.cpp', [(
    '        if (d.source != Draw::kAuto) {\n'
    '            report_once("unsupported rectangle list with an index buffer", d.count);\n'
    '            ++skipped_draws_;\n'
    '            return;\n'
    '        }\n'
    '        topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;\n',
    '        // (with an index buffer: port/patch_rects2.py, the shader reads the indices)\n'
    '        topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;\n',
), (
    '    std::memcpy(upload(sizeof(dc), ubo_align, dc_offset), &dc, sizeof(dc));\n',
    '    uint8_t* const dc_uploaded = reinterpret_cast<uint8_t*>(upload(sizeof(dc), ubo_align, dc_offset));\n'
    '    std::memcpy(dc_uploaded, &dc, sizeof(dc));\n',
), (
    '    // Stream-out data a run of stream-out draws wrote, read by the draws\n',
    '    if (r(reg::VGT_PRIMITIVE_TYPE) == 0x11 && indexed) {\n'
    '        // A rectangle list with indices: the vertex shader reads them (it makes the fourth corner itself).\n'
    '        if (stream_out) report_once("rectangle list with stream-out: the indices take its fourth buffer", d.count);\n'
    '        const VkDeviceAddress at = ring_.address() + index_offset;\n'
    '        const abi::Buffer where{static_cast<uint32_t>(at), static_cast<uint32_t>(at >> 32), index_count * 4, 4};\n'
    '        std::memcpy(dc_uploaded + (reinterpret_cast<const uint8_t*>(&dc.so[3]) - reinterpret_cast<const uint8_t*>(&dc)),\n'
    '                    &where, sizeof(where));\n'
    '        indexed = false;\n'
    '    }\n'
    '\n'
    '    // Stream-out data a run of stream-out draws wrote, read by the draws\n',
)], 'patch_rects2.py')
