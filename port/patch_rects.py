#!/usr/bin/env python3
"""patch_rects.py SMASH4_DIR : primitive type 0x11 (rectangle list) in the Vulkan renderer.

The console draws a rectangle from three vertices and works out the fourth itself. Vulkan has no such primitive,
and the runtime skipped these draws ("unsupported primitive type (0x11)": Mario Tennis Ultra Smash, 89 of 120 draws
of a menu frame). The translated vertex shader already loads its vertices from guest memory by index, so the fourth
corner is made there: a rectangle is drawn as two triangles (6 shader vertices), and for the second triangle the
shader runs the title's vertex program for all three given vertices and builds the missing corner as
A + B - R, where R is the corner opposite the longest edge (the right angle). Every interpolated output is built
the same way; flat ones take R's value.
Only draws without an index buffer are handled (what titles use for rectangles); an indexed one is still skipped
and reported."""
import sys

root = sys.argv[1] + '/runtime/src/'


def patch(path, pairs, marker):
    p = root + path
    s = open(p, encoding='utf-8').read()
    if marker in s:
        print('patch_rects: already there:', path)
        return
    for old, new in pairs:
        if old not in s:
            sys.exit('patch_rects: text not found in %s: %r' % (path, old[:60]))
        s = s.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(s)
    print('patch_rects: done:', path)


patch('latte/translate.h', [(
    '    bool clip_space_dx = false;   // PA_CL_CLIP_CNTL.DX_CLIP_SPACE_DEF: z in [0, w]\n',
    '    bool clip_space_dx = false;   // PA_CL_CLIP_CNTL.DX_CLIP_SPACE_DEF: z in [0, w]\n'
    '    bool rects = false;           // VGT_PRIMITIVE_TYPE 0x11: the shader makes each rectangle\'s fourth corner\n',
)], 'bool rects = false;')

patch('latte/environment.cpp', [(
    '    env.point_size_export = (r(reg::PA_CL_VS_OUT_CNTL) >> 24) & 1;\n',
    '    env.point_size_export = (r(reg::PA_CL_VS_OUT_CNTL) >> 24) & 1;\n'
    '    env.rects = r(reg::VGT_PRIMITIVE_TYPE) == 0x11;\n',
), (
    '        h.add(env.clip_space_dx | (env.point_size_export << 1) | (env.stream_out_mask << 2));\n',
    '        h.add(env.clip_space_dx | (env.point_size_export << 1) | (env.stream_out_mask << 2) | (env.rects << 6));\n',
)], 'env.rects')

patch('latte/translate.cpp', [(
    '        line("R[0] = ivec4(gl_VertexIndex, 0, 0, gl_InstanceIndex);");\n',
    '        line(env_.rects ? "R[0] = ivec4(rect_vertex, 0, 0, gl_InstanceIndex);"\n'
    '                        : "R[0] = ivec4(gl_VertexIndex, 0, 0, gl_InstanceIndex);");\n',
), (
    '    out_.glsl = header() + globals + "\\n" + functions + "void main() {\\n" + init + main_vars + main_body + "}\\n";\n',
    '''    if (vs_ && env_.rects) {
        // A rectangle list (port/patch_rects.py): 6 shader vertices per rectangle. 0-2 are the title's three;
        // 3-5 are the second triangle: the two ends of the longest edge and the corner the console adds.
        std::vector<int> outs;
        for (int k = 0; k < env_.ps_input_count; ++k) {
            if (k == env_.ps_position_input) continue;
            bool exported = false;
            for (uint8_t s : env_.vs_out_semantic) exported |= s == env_.ps_inputs[k].semantic && s != 0xFF;
            if (exported) outs.push_back(k);
        }
        std::string m = "int rect_vertex;\\nvoid rect_body() {\\n" + init + main_vars + main_body + "}\\n";
        m += "void main() {\\n    int rq = gl_VertexIndex / 6, rj = gl_VertexIndex % 6;\\n";
        m += "    if (rj < 3) { rect_vertex = rq * 3 + rj; rect_body(); return; }\\n";
        m += "    vec4 rp[3];\\n";
        for (int k : outs) m += format("    vec4 rv%d[3];\\n", k);
        m += "    for (int i = 0; i < 3; ++i) {\\n        rect_vertex = rq * 3 + i;\\n        rect_body();\\n        rp[i] = gl_Position;\\n";
        for (int k : outs) m += format("        rv%d[i] = v%d;\\n", k, k);
        m += "    }\\n";
        m += "    vec2 ra = rp[0].xy / rp[0].w, rb = rp[1].xy / rp[1].w, rc = rp[2].xy / rp[2].w;\\n";
        m += "    float d01 = dot(ra - rb, ra - rb), d12 = dot(rb - rc, rb - rc), d20 = dot(rc - ra, rc - ra);\\n";
        m += "    int rr = (d01 >= d12 && d01 >= d20) ? 2 : (d12 >= d20 ? 0 : 1);\\n";
        m += "    int rA = (rr + 1) % 3, rB = (rr + 2) % 3;\\n";
        m += "    if (rj == 3) {\\n        gl_Position = rp[rA];\\n";
        for (int k : outs) m += format("        v%d = rv%d[rA];\\n", k, k);
        m += "    } else if (rj == 5) {\\n        gl_Position = rp[rB];\\n";
        for (int k : outs) m += format("        v%d = rv%d[rB];\\n", k, k);
        m += "    } else {\\n        gl_Position = rp[rA] + rp[rB] - rp[rr];\\n";
        for (int k : outs) {
            m += env_.ps_inputs[k].flat ? format("        v%d = rv%d[rr];\\n", k, k)
                                        : format("        v%d = rv%d[rA] + rv%d[rB] - rv%d[rr];\\n", k, k, k, k);
        }
        m += "    }\\n}\\n";
        out_.glsl = header() + globals + "\\n" + functions + m;
    } else {
        out_.glsl = header() + globals + "\\n" + functions + "void main() {\\n" + init + main_vars + main_body + "}\\n";
    }
''',
)], 'rect_vertex')

patch('gpu/vulkan/draw.cpp', [(
    '    case 0x13: topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST; convert = Convert::kQuads; break;\n',
    '    case 0x13: topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST; convert = Convert::kQuads; break;\n'
    '    case 0x11: // rectangle list: the vertex shader makes the fourth corner (port/patch_rects.py)\n'
    '        if (d.source != Draw::kAuto) {\n'
    '            report_once("unsupported rectangle list with an index buffer", d.count);\n'
    '            ++skipped_draws_;\n'
    '            return;\n'
    '        }\n'
    '        topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;\n'
    '        break;\n',
), (
    '        vkCmdDraw(c, d.count, instances, 0, 0);\n',
    '        vkCmdDraw(c, r(reg::VGT_PRIMITIVE_TYPE) == 0x11 ? d.count / 3 * 6 : d.count, instances, 0, 0);\n',
)], 'rectangle list: the vertex shader')
