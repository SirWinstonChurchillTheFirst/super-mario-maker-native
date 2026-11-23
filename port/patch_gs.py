#!/usr/bin/env python3
"""patch_gs.py RUNTIME_SRC_DIR (…/runtime/src) : geometry shaders (Super Mario Maker's terrain).

Latte geometry mode runs three programs: the ES (the title's vertex shader, writing each vertex to the ESGS ring
with MEM_RING exports), the GS (reading its input vertices from that ring, writing output vertices to the GSVS ring
and EMIT_VERTEX / CUT_VERTEX) and the copy shader (in the VS slot: reads one output vertex from the GSVS ring and
exports position and parameters). The runtime ran the copy shader alone as the vertex shader: nothing visible.

Now:
- ES -> Vulkan vertex shader: MEM_RING write at array_base (dwords) -> `out ivec4 esgs_out[slot = base / 4]`.
- GS -> Vulkan geometry shader: R0 = vertex "offsets" (vertex n = n << 20), ring fetch (buffer 159) at
  gpr + offset bytes -> esgs_in[vertex][byte / 16]; MEM_RING writes -> local `gsvs_ring[base / 4]`;
  EMIT_VERTEX -> copy_vertex() (the copy shader translated inline with its own registers; its ring fetches read
  gsvs_ring[emitted * vertex slots + offset / 16]) + EmitVertex(); CUT_VERTEX -> EndPrimitive().
- GS uniform blocks: DrawConstants.gs_cb (SQ_ALU_CONST_CACHE_GS_n); device feature geometryShader.
- GS pipelines are not written to pipelines.list (precompile knows two stages only).
TTT2_NO_GS=1: old behaviour (copy shader alone)."""
import sys

src = sys.argv[1]


def patch(rel, pairs):
    p = src + "/" + rel
    s = open(p, encoding="utf-8").read()
    if "patch_gs.py" in s:
        print(rel + ": already applied")
        return
    for old, new in pairs:
        assert s.count(old) == 1, rel + ": pattern not found or not unique: " + old[:80]
        s = s.replace(old, new)
    open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("patched", p)


# ------------------------------------------------------------------ shader_abi.h
patch("latte/shader_abi.h", [(
    "    uint32_t pad[2];\n};",
    "    uint32_t pad[2];\n"
    "    Buffer gs_cb[16];   // port/patch_gs.py: geometry shader uniform blocks (SQ_ALU_CONST_CACHE_GS_n)\n"
    "};")])

# ------------------------------------------------------------------ translate.h
patch("latte/translate.h", [
    ("    uint32_t vtx_const_word2[16] = {};\n",
     "    uint32_t vtx_const_word2[16] = {};\n"
     "    // port/patch_gs.py: geometry mode. gs_part: 0 normal, 1 ES (vertex shader writing the ESGS ring), 2 GS,\n"
     "    // 3 copy shader (inlined into the GS).\n"
     "    uint8_t gs_part = 0;\n"
     "    uint8_t esgs_slots = 0;       // ESGS ring item size in vec4s\n"
     "    uint8_t gs_in_vertices = 1;   // GS input primitive: 1 points, 2 lines, 3 triangles\n"
     "    uint8_t gs_out_prim = 2;      // VGT_GS_OUT_PRIM_TYPE: 0 points, 1 line strip, 2 triangle strip\n"
     "    uint16_t gsvs_vertex_slots = 1; // SQ_GS_VERT_ITEMSIZE in vec4s\n"),
    ("bool translate(const Program& program, const Program* fetch, const ShaderEnvironment& env, TranslatedShader& out,\n"
     "               std::string& error);\n",
     "bool translate(const Program& program, const Program* fetch, const ShaderEnvironment& env, TranslatedShader& out,\n"
     "               std::string& error);\n"
     "// port/patch_gs.py: a Vulkan geometry shader from the GS program and its copy shader.\n"
     "bool translate_gs(const Program& gs, const Program& copy, const ShaderEnvironment& gs_env,\n"
     "                  const ShaderEnvironment& copy_env, TranslatedShader& out, std::string& error);\n"),
])

# ------------------------------------------------------------------ environment.cpp
patch("latte/environment.cpp", [(
    "        for (uint32_t w : env.vtx_const_word2) h.add(w); // port/patch_vtx_const_fields.py\n",
    "        for (uint32_t w : env.vtx_const_word2) h.add(w); // port/patch_vtx_const_fields.py\n"
    "        h.add(env.gs_part | (env.esgs_slots << 8) | (env.gs_in_vertices << 16) | (env.gs_out_prim << 24)); // port/patch_gs.py\n"
    "        h.add(env.gsvs_vertex_slots);\n")])

# ------------------------------------------------------------------ translate.cpp
patch("latte/translate.cpp", [
    # class members
    ("    void emit_stream_out(const CfInstruction& cf);\n",
     "    void emit_stream_out(const CfInstruction& cf);\n"
     "    void emit_ring_write(const CfInstruction& cf);             // port/patch_gs.py\n"
     "    void emit_ring_read(const VtxInstruction& v, bool copy);  // port/patch_gs.py\n"),
    ("    TranslatedShader& out_;\n    bool vs_ = false;\n",
     "    TranslatedShader& out_;\n    bool vs_ = false;\n"
     "    // port/patch_gs.py: geometry mode parts (see ShaderEnvironment::gs_part).\n"
     "    bool es_ = false, gs_ = false, copy_ = false;\n"
     "    uint32_t gs_emits_ = 0;      // EMIT_VERTEX instructions\n"
     "    uint32_t gs_ring_slots_ = 0; // GSVS ring vec4s the GS writes\n"
     "    struct Pieces {\n"
     "        std::string globals, functions, init, vars, body;\n"
     "    } pieces_;\n"
     "\n"
     "public:\n"
     "    bool run_gs(const Program& copy, const ShaderEnvironment& copy_env, std::string& error);\n"
     "\n"
     "private:\n"),
    # run(): parts
    ("bool Translator::run(std::string& error) {\n    vs_ = env_.stage == Stage::kVertex;\n",
     "bool Translator::run(std::string& error) {\n    vs_ = env_.stage == Stage::kVertex;\n"
     "    es_ = env_.gs_part == 1; // port/patch_gs.py\n"
     "    gs_ = env_.gs_part == 2;\n"
     "    copy_ = env_.gs_part == 3;\n"
     "    if (gs_) note_gpr(1, false); // the input vertex offsets in R0/R1\n"),
    ("        line(env_.rects ? \"R[0] = ivec4(rect_vertex, 0, 0, gl_InstanceIndex);\"\n"
     "                        : \"R[0] = ivec4(gl_VertexIndex, 0, 0, gl_InstanceIndex);\");\n"
     "        line(\"gl_PointSize = dc.params.y;\"); // PA_SU_POINT_SIZE unless the shader exports a size\n"
     "        for (int k = 0; k < env_.ps_input_count; ++k) {\n",
     "        if (gs_) { // port/patch_gs.py: input vertex n is at ring \"offset\" n << 20\n"
     "            line(\"R[0] = ivec4(0, 1 << 20, gl_PrimitiveIDIn, 2 << 20);\");\n"
     "            line(\"R[1] = ivec4(3 << 20, 4 << 20, 0, 5 << 20);\");\n"
     "        } else if (copy_) {\n"
     "            line(\"R[0] = ivec4(0);\");\n"
     "        } else {\n"
     "            line(env_.rects ? \"R[0] = ivec4(rect_vertex, 0, 0, gl_InstanceIndex);\"\n"
     "                            : \"R[0] = ivec4(gl_VertexIndex, 0, 0, gl_InstanceIndex);\");\n"
     "        }\n"
     "        if (!gs_ && !copy_) line(\"gl_PointSize = dc.params.y;\"); // PA_SU_POINT_SIZE unless the shader exports a size\n"
     "        for (int k = 0; k < env_.ps_input_count && !es_ && !gs_; ++k) {\n"),
    # pieces
    ("    if (vs_ && env_.rects) {\n",
     "    pieces_ = {globals, functions, init, main_vars, main_body}; // port/patch_gs.py\n"
     "    if (vs_ && env_.rects) {\n"),
    # header: gs_cb, ES outputs
    ("    h += \"    uvec4 vb[16];\\n    uvec4 so[4];\\n    uvec4 vtx;\\n    vec4 params;\\n    uvec4 scaled;\\n} dc;\\n\";\n",
     "    h += \"    uvec4 vb[16];\\n    uvec4 so[4];\\n    uvec4 vtx;\\n    vec4 params;\\n    uvec4 scaled;\\n\";\n"
     "    if (gs_) h += \"    uvec4 gs_cb[16];\\n\"; // port/patch_gs.py\n"
     "    h += \"} dc;\\n\";\n"),
    ("    // Interface between the stages.\n",
     "    // Interface between the stages.\n"
     "    if (es_) h += format(\"layout(location = 0) out ivec4 esgs_out[%u];\\n\", std::max<uint32_t>(env_.esgs_slots, 1)); // port/patch_gs.py\n"),
    ("        if (k == env_.ps_position_input) continue;\n"
     "        const ShaderEnvironment::PsInput& in = env_.ps_inputs[k];\n"
     "        bool exported = false;\n",
     "        if (k == env_.ps_position_input || es_) continue; // (ES: only the ring, port/patch_gs.py)\n"
     "        const ShaderEnvironment::PsInput& in = env_.ps_inputs[k];\n"
     "        bool exported = false;\n"),
    # exports: MEM_RING
    ("        if (cf.inst == cf::kExp || cf.inst == cf::kExpDone) emit_export(cf);\n",
     "        if (cf.inst == cf::kExp || cf.inst == cf::kExpDone) emit_export(cf);\n"
     "        else if (cf.inst == cf::kMemRing && (es_ || gs_)) emit_ring_write(cf); // port/patch_gs.py\n"),
    # EMIT / CUT
    ("    case cf::kPush:\n        push();\n        break;\n",
     "    case cf::kEmitVertex: // port/patch_gs.py\n"
     "    case cf::kEmitCutVertex:\n"
     "    case cf::kCutVertex:\n"
     "        if (!gs_) {\n"
     "            fail(format(\"CF %u: %s outside a geometry shader\", cf.index, cf_name(cf.inst)));\n"
     "            break;\n"
     "        }\n"
     "        if (cf.inst != cf::kCutVertex) {\n"
     "            line(\"if (act) { copy_vertex(); EmitVertex(); gs_emit++; }\");\n"
     "            ++gs_emits_;\n"
     "        }\n"
     "        if (cf.inst != cf::kEmitVertex) line(\"if (act) EndPrimitive();\");\n"
     "        break;\n"
     "    case cf::kPush:\n        push();\n        break;\n"),
    # ring reads
    ("void Translator::emit_buffer_fetch(const TexInstruction& t) {\n    const VtxInstruction& v = t.vtx;\n",
     "void Translator::emit_buffer_fetch(const TexInstruction& t) {\n    const VtxInstruction& v = t.vtx;\n"
     "    if (gs_ && v.buffer_id == 159) { // port/patch_gs.py: the ESGS ring\n"
     "        emit_ring_read(v, false);\n"
     "        return;\n"
     "    }\n"),
    ("void Translator::emit_vertex_fetch(const VtxInstruction& v) {\n",
     "void Translator::emit_vertex_fetch(const VtxInstruction& v) {\n"
     "    if (copy_ && v.buffer_id == 159) { // port/patch_gs.py: the GSVS ring\n"
     "        emit_ring_read(v, true);\n"
     "        return;\n"
     "    }\n"),
    # new methods + run_gs + translate_gs, before control flow section
    ("// ------------------------------------------------------------ control flow\n",
     "// port/patch_gs.py: geometry mode rings.\n"
     "void Translator::emit_ring_write(const CfInstruction& cf) {\n"
     "    const ExportInstruction& e = cf.exp;\n"
     "    if (e.type != 0) {\n"
     "        fail(\"indexed ring write\");\n"
     "        return;\n"
     "    }\n"
     "    if (e.array_base % 4 != 0) {\n"
     "        fail(format(\"ring write at dword %u (not a vec4)\", e.array_base));\n"
     "        return;\n"
     "    }\n"
     "    for (uint32_t b = 0; b <= e.burst_count; ++b) {\n"
     "        const uint32_t slot = e.array_base / 4 + b;\n"
     "        if (es_ && slot >= env_.esgs_slots) {\n"
     "            fail(format(\"ES ring write to vec4 %u beyond the item size %u\", slot, env_.esgs_slots));\n"
     "            return;\n"
     "        }\n"
     "        const std::string reg = gpr(e.rw_gpr + b, e.rw_rel, kLoopIndex);\n"
     "        for (int i = 0; i < 4; ++i) {\n"
     "            if (!(e.comp_mask & (1u << i))) continue;\n"
     "            line(format(\"if (act) %s[%u].%c = %s.%c;\", es_ ? \"esgs_out\" : \"gsvs_ring\", slot, kChan[i], reg.c_str(), kChan[i]));\n"
     "        }\n"
     "        if (gs_) gs_ring_slots_ = std::max(gs_ring_slots_, slot + 1);\n"
     "    }\n"
     "}\n"
     "\n"
     "void Translator::emit_ring_read(const VtxInstruction& v, bool copy) {\n"
     "    open(\"\");\n"
     "    line(format(\"uint ra = uint(%s.%c) + %uu;\", gpr(v.src_gpr, v.src_rel, kLoopIndex).c_str(), kChan[v.src_sel_x & 3],\n"
     "                v.offset));\n"
     "    if (copy) {\n"
     "        line(format(\"ivec4 f = gsvs_ring[clamp(gs_emit * %u + int((ra & 0xFFFFFu) >> 4u), 0, gsvs_ring.length() - 1)];\",\n"
     "                    std::max<uint32_t>(env_.gsvs_vertex_slots, 1)));\n"
     "    } else {\n"
     "        line(format(\"ivec4 f = esgs_in[min(int(ra >> 20u), %d)][min(int((ra & 0xFFFFFu) >> 4u), %d)];\",\n"
     "                    std::max<int>(env_.gs_in_vertices, 1) - 1, std::max<int>(env_.esgs_slots, 1) - 1));\n"
     "    }\n"
     "    const int dst = v.semantic_or_gpr;\n"
     "    for (int i = 0; i < 4; ++i) {\n"
     "        const uint8_t sel = v.dst_sel[i];\n"
     "        if (sel == kSelMask) continue;\n"
     "        const std::string value = sel < 4 ? format(\"f.%c\", kChan[sel]) : sel == kSel1 ? \"0x3F800000\" : \"0\";\n"
     "        line(gpr_store(dst, v.dst_rel, kLoopIndex, kChan[i], value));\n"
     "    }\n"
     "    close();\n"
     "}\n"
     "\n"
     "bool Translator::run_gs(const Program& copy, const ShaderEnvironment& copy_env, std::string& error) {\n"
     "    TranslatedShader copy_out;\n"
     "    Translator c(copy, nullptr, copy_env, copy_out);\n"
     "    std::string copy_error;\n"
     "    if (!c.run(copy_error)) {\n"
     "        error = \"copy shader: \" + copy_error;\n"
     "        return false;\n"
     "    }\n"
     "    if (c.relative_ || !copy.subroutines.empty() || c.texture_mask_ || c.uses_registers_ || c.constant_bank_mask_ ||\n"
     "        c.buffer_mask_ || c.uses_kill_) {\n"
     "        error = \"copy shader with features the geometry path lacks\";\n"
     "        return false;\n"
     "    }\n"
     "    if (!run(error)) return false;\n"
     "    if (texture_mask_ || uses_registers_ || buffer_mask_) {\n"
     "        error = \"geometry shader with textures, uniform registers or buffers\";\n"
     "        return false;\n"
     "    }\n"
     "    bool loops = !p_.subroutines.empty();\n"
     "    for (const CfInstruction& cf : p_.cf) {\n"
     "        if (cf.kind == CfInstruction::kNormal && (cf.inst == cf::kLoopStart || cf.inst == cf::kLoopStartDx10 ||\n"
     "                                                  cf.inst == cf::kLoopStartNoAl || cf.inst == cf::kCall)) {\n"
     "            loops = true;\n"
     "        }\n"
     "    }\n"
     "    uint32_t outputs = 1; // position\n"
     "    for (int k = 0; k < env_.ps_input_count; ++k) {\n"
     "        if (k == env_.ps_position_input) continue;\n"
     "        bool exported = false;\n"
     "        for (uint8_t s : env_.vs_out_semantic) exported |= s == env_.ps_inputs[k].semantic && s != 0xFF;\n"
     "        if (exported) ++outputs;\n"
     "    }\n"
     "    const uint32_t by_components = std::max<uint32_t>(1, 1024 / (4 * outputs));\n"
     "    const uint32_t max_vertices = std::min<uint32_t>(256, loops || gs_emits_ == 0 ? by_components : std::min(gs_emits_, by_components));\n"
     "    const uint32_t stride = std::max<uint32_t>(env_.gsvs_vertex_slots, 1);\n"
     "    const uint32_t ring = std::max<uint32_t>({gs_ring_slots_, max_vertices * stride, 1});\n"
     "    static constexpr const char* kIn[] = {\"points\", \"lines\", \"triangles\"};\n"
     "    static constexpr const char* kOut[] = {\"points\", \"line_strip\", \"triangle_strip\"};\n"
     "    std::string g = header();\n"
     "    g += format(\"layout(%s) in;\\nlayout(%s, max_vertices = %u) out;\\n\", kIn[std::clamp<int>(env_.gs_in_vertices, 1, 3) - 1],\n"
     "                kOut[std::min<int>(env_.gs_out_prim, 2)], max_vertices);\n"
     "    g += format(\"layout(location = 0) in ivec4 esgs_in[][%u];\\n\", std::max<uint32_t>(env_.esgs_slots, 1));\n"
     "    g += pieces_.globals;\n"
     "    g += format(\"ivec4 gsvs_ring[%u];\\nint gs_emit = 0;\\n\\n\", ring);\n"
     "    g += \"void copy_vertex() {\\n\";\n"
     "    for (size_t pos = 0; pos < c.pieces_.globals.size();) { // the copy shader's registers, as locals\n"
     "        const size_t end = c.pieces_.globals.find('\\n', pos);\n"
     "        g += \"    \" + c.pieces_.globals.substr(pos, end - pos) + \"\\n\";\n"
     "        pos = end == std::string::npos ? c.pieces_.globals.size() : end + 1;\n"
     "    }\n"
     "    g += c.pieces_.init + c.pieces_.vars + c.pieces_.body + \"}\\n\\n\";\n"
     "    g += pieces_.functions;\n"
     "    g += \"void main() {\\n\" + pieces_.init + pieces_.vars + pieces_.body + \"}\\n\";\n"
     "    out_.glsl = g;\n"
     "    return true;\n"
     "}\n"
     "\n"
     "// ------------------------------------------------------------ control flow\n"),
    ("bool translate(const Program& program, const Program* fetch, const ShaderEnvironment& env, TranslatedShader& out,\n"
     "               std::string& error) {\n"
     "    out = TranslatedShader{};\n"
     "    Translator translator(program, fetch, env, out);\n"
     "    return translator.run(error);\n"
     "}\n",
     "bool translate(const Program& program, const Program* fetch, const ShaderEnvironment& env, TranslatedShader& out,\n"
     "               std::string& error) {\n"
     "    out = TranslatedShader{};\n"
     "    Translator translator(program, fetch, env, out);\n"
     "    return translator.run(error);\n"
     "}\n"
     "\n"
     "// port/patch_gs.py\n"
     "bool translate_gs(const Program& gs, const Program& copy, const ShaderEnvironment& gs_env,\n"
     "                  const ShaderEnvironment& copy_env, TranslatedShader& out, std::string& error) {\n"
     "    out = TranslatedShader{};\n"
     "    Translator translator(gs, nullptr, gs_env, out);\n"
     "    return translator.run_gs(copy, copy_env, error);\n"
     "}\n"),
])

# kc() reads the GS's own blocks in a geometry shader
p = src + "/latte/translate.cpp"
s = open(p, encoding="utf-8").read()
old_kc = ("                \"    return ivec4(GuestVec4s(uvec2(b.x & ~15u, b.y)).v[index]);\\n\"\n"
          "                \"}\\n\",\n"
          "                vs_ ? \"vs\" : \"ps\");\n")
new_kc = ("                \"    return ivec4(GuestVec4s(uvec2(b.x & ~15u, b.y)).v[index]);\\n\"\n"
          "                \"}\\n\",\n"
          "                gs_ ? \"gs\" : vs_ ? \"vs\" : \"ps\"); // (gs: port/patch_gs.py)\n")
if old_kc in s:
    s = s.replace(old_kc, new_kc)
    open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("patched kc()")
else:
    assert new_kc in s, "kc() pattern not found"

# ------------------------------------------------------------------ renderer.h
patch("gpu/vulkan/renderer.h", [
    ("    const latte::Program* program(uint32_t address, uint32_t size, uint64_t& hash);\n",
     "    const latte::Program* program(uint32_t address, uint32_t size, uint64_t& hash);\n"
     "    // port/patch_gs.py: the geometry shader of a GS draw (GS program + copy shader).\n"
     "    const ShaderModule* gs_shader(uint32_t address, uint32_t size, uint32_t copy_address, uint32_t copy_size,\n"
     "                                  const latte::ShaderEnvironment& vs_env, uint32_t esgs_slots, uint32_t in_vertices,\n"
     "                                  uint32_t out_prim, uint32_t vertex_slots);\n"),
    ("    VkPipelineLayout pipeline_layout(uint32_t vs_textures, uint32_t ps_textures, bool vs_registers,\n"
     "                                     bool ps_registers);\n",
     "    VkPipelineLayout pipeline_layout(uint32_t vs_textures, uint32_t ps_textures, bool vs_registers,\n"
     "                                     bool ps_registers, bool gs = false);\n"),
    ("                             const VkFormat* colors, uint32_t color_count, VkFormat depth, uint32_t topology_class);\n",
     "                             const VkFormat* colors, uint32_t color_count, VkFormat depth, uint32_t topology_class,\n"
     "                             const ShaderModule* gs = nullptr);\n"),
    ("    VkPipeline build_pipeline(const PipelineKey& k, VkShaderModule vs, VkShaderModule ps, VkPipelineLayout layout);\n",
     "    VkPipeline build_pipeline(const PipelineKey& k, VkShaderModule vs, VkShaderModule ps, VkPipelineLayout layout,\n"
     "                              VkShaderModule gs = VK_NULL_HANDLE);\n"),
])

# ------------------------------------------------------------------ context.cpp
patch("gpu/vulkan/context.cpp", [(
    "    ef.depthClamp = af.depthClamp;\n",
    "    ef.depthClamp = af.depthClamp;\n"
    "    ef.geometryShader = af.geometryShader; // port/patch_gs.py\n")])

# ------------------------------------------------------------------ draw.cpp
patch("gpu/vulkan/draw.cpp", [
    # gs_shader()
    ("// Takes `entry`'s module from a finished worker compile, if any.\n",
     "// port/patch_gs.py: the geometry shader of a GS draw, compiled on the draw thread (few titles, few shaders).\n"
     "const ShaderModule* Renderer::gs_shader(uint32_t address, uint32_t size, uint32_t copy_address, uint32_t copy_size,\n"
     "                                        const ShaderEnvironment& vs_env, uint32_t esgs_slots, uint32_t in_vertices,\n"
     "                                        uint32_t out_prim, uint32_t vertex_slots) {\n"
     "    uint64_t gs_hash = 0, copy_hash = 0;\n"
     "    const Program* gp = program(address, size, gs_hash);\n"
     "    const Program* cp = program(copy_address, copy_size, copy_hash);\n"
     "    if (gp == nullptr || cp == nullptr) return nullptr;\n"
     "    ShaderEnvironment gs_env = vs_env;\n"
     "    gs_env.gs_part = 2;\n"
     "    gs_env.rects = false;\n"
     "    for (uint8_t& s : gs_env.vtx_semantic) s = 0xFF;\n"
     "    gs_env.esgs_slots = static_cast<uint8_t>(esgs_slots);\n"
     "    gs_env.gs_in_vertices = static_cast<uint8_t>(in_vertices);\n"
     "    gs_env.gs_out_prim = static_cast<uint8_t>(out_prim);\n"
     "    gs_env.gsvs_vertex_slots = static_cast<uint16_t>(vertex_slots);\n"
     "    ShaderEnvironment copy_env = gs_env;\n"
     "    copy_env.gs_part = 3;\n"
     "    const uint64_t keys[4] = {gs_hash, copy_hash, environment_key(gs_env), 0x6753ull};\n"
     "    const uint64_t key = fnv(keys, sizeof(keys));\n"
     "    auto& entry = shaders_[key];\n"
     "    if (entry) return entry->failed ? nullptr : entry.get();\n"
     "    entry = std::make_unique<ShaderModule>();\n"
     "    std::string error;\n"
     "    bool translated;\n"
     "    {\n"
     "        Timed timed{spent_translate_};\n"
     "        translated = translate_gs(*gp, *cp, gs_env, copy_env, entry->info, error);\n"
     "    }\n"
     "    if (!translated) {\n"
     "        std::fprintf(stderr, \"ttt2: gpu: cannot translate gs %016llx (copy %016llx): %s\\n\",\n"
     "                     static_cast<unsigned long long>(gs_hash), static_cast<unsigned long long>(copy_hash), error.c_str());\n"
     "        entry->failed = true;\n"
     "        return nullptr;\n"
     "    }\n"
     "    if (const char* dir = dump_directory()) {\n"
     "        char name[128];\n"
     "        std::snprintf(name, sizeof(name), \"gs_%016llx_%016llx.glsl\", static_cast<unsigned long long>(gs_hash),\n"
     "                      static_cast<unsigned long long>(key));\n"
     "        std::ofstream(std::filesystem::path(dir) / name) << entry->info.glsl;\n"
     "    }\n"
     "    const uint64_t glsl_hash = fnv(entry->info.glsl.data(), entry->info.glsl.size());\n"
     "    entry->glsl_hash = glsl_hash;\n"
     "    std::vector<uint32_t> spirv = load_cached_spirv(glsl_hash);\n"
     "    if (spirv.empty()) {\n"
     "        shaderc_compile_options_t options = shaderc_compile_options_initialize();\n"
     "        shaderc_compile_options_set_target_env(options, shaderc_target_env_vulkan, shaderc_env_version_vulkan_1_3);\n"
     "        shaderc_compile_options_set_optimization_level(options, shaderc_optimization_level_zero);\n"
     "        Timed timed{spent_compile_};\n"
     "        shaderc_compilation_result_t result = shaderc_compile_into_spv(\n"
     "            compiler_, entry->info.glsl.data(), entry->info.glsl.size(), shaderc_geometry_shader, \"gs\", \"main\", options);\n"
     "        shaderc_compile_options_release(options);\n"
     "        if (shaderc_result_get_compilation_status(result) != shaderc_compilation_status_success) {\n"
     "            std::fprintf(stderr, \"ttt2: gpu: cannot compile gs %016llx:\\n%s\\n\", static_cast<unsigned long long>(gs_hash),\n"
     "                         shaderc_result_get_error_message(result));\n"
     "            shaderc_result_release(result);\n"
     "            entry->failed = true;\n"
     "            return nullptr;\n"
     "        }\n"
     "        const auto* code = reinterpret_cast<const uint32_t*>(shaderc_result_get_bytes(result));\n"
     "        spirv.assign(code, code + shaderc_result_get_length(result) / 4);\n"
     "        shaderc_result_release(result);\n"
     "        store_cached_spirv(glsl_hash, spirv);\n"
     "    }\n"
     "    entry->module = cached_module(glsl_hash, &spirv);\n"
     "    return entry.get();\n"
     "}\n"
     "\n"
     "// Takes `entry`'s module from a finished worker compile, if any.\n"),
    # pipeline layout
    ("VkPipelineLayout Renderer::pipeline_layout(uint32_t vs_textures, uint32_t ps_textures, bool vs_registers,\n"
     "                                           bool ps_registers) {\n"
     "    const uint64_t key = uint64_t{vs_textures} | (uint64_t{ps_textures} << 18) | (uint64_t{vs_registers} << 36) |\n"
     "                         (uint64_t{ps_registers} << 37);\n",
     "VkPipelineLayout Renderer::pipeline_layout(uint32_t vs_textures, uint32_t ps_textures, bool vs_registers,\n"
     "                                           bool ps_registers, bool gs) {\n"
     "    const uint64_t key = uint64_t{vs_textures} | (uint64_t{ps_textures} << 18) | (uint64_t{vs_registers} << 36) |\n"
     "                         (uint64_t{ps_registers} << 37) | (uint64_t{gs} << 38); // (gs: port/patch_gs.py)\n"),
    ("    bindings.push_back({abi::kDrawConstantsBinding, VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, 1,\n"
     "                        VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT, nullptr});\n",
     "    bindings.push_back({abi::kDrawConstantsBinding, VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, 1,\n"
     "                        VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT |\n"
     "                            (gs ? VK_SHADER_STAGE_GEOMETRY_BIT : VkShaderStageFlags{0}),\n"
     "                        nullptr});\n"),
    # pipeline()
    ("const Pipeline* Renderer::pipeline(const Registers& regs, const ShaderModule* vs, const ShaderModule* ps,\n"
     "                                   const VkFormat* colors, uint32_t color_count, VkFormat depth, uint32_t topology_class) {\n",
     "const Pipeline* Renderer::pipeline(const Registers& regs, const ShaderModule* vs, const ShaderModule* ps,\n"
     "                                   const VkFormat* colors, uint32_t color_count, VkFormat depth, uint32_t topology_class,\n"
     "                                   const ShaderModule* gs) {\n"),
    ("    k.ps_glsl = ps->glsl_hash;\n",
     "    k.ps_glsl = ps->glsl_hash;\n"
     "    if (gs) k.vs_glsl ^= gs->glsl_hash * 0x9E3779B97F4A7C15ull + 0x6753; // port/patch_gs.py (never precompiled)\n"),
    ("        if (state == Built::kReady && !entry->listed) {\n",
     "        if (state == Built::kReady && !entry->listed && gs == nullptr) {\n"),
    ("    entry->layout = pipeline_layout(vs->info.texture_mask, ps->info.texture_mask, vs->info.uses_registers,\n"
     "                                    ps->info.uses_registers);\n",
     "    entry->layout = pipeline_layout(vs->info.texture_mask, ps->info.texture_mask, vs->info.uses_registers,\n"
     "                                    ps->info.uses_registers, gs != nullptr);\n"),
    ("        compile_async([this, p = entry.get(), vm = vs->module, pm = ps->module] {\n"
     "            p->pipeline = build_pipeline(p->key, vm, pm, p->layout);\n",
     "        compile_async([this, p = entry.get(), vm = vs->module, pm = ps->module, gm = gs ? gs->module : VK_NULL_HANDLE] {\n"
     "            p->pipeline = build_pipeline(p->key, vm, pm, p->layout, gm);\n"),
    ("        entry->pipeline = build_pipeline(k, vs->module, ps->module, entry->layout);\n",
     "        entry->pipeline = build_pipeline(k, vs->module, ps->module, entry->layout, gs ? gs->module : VK_NULL_HANDLE);\n"),
    ("    entry->listed = true;\n    append_saved(\"pipelines.list\", k);\n    return entry.get();\n",
     "    entry->listed = true;\n    if (gs == nullptr) append_saved(\"pipelines.list\", k);\n    return entry.get();\n"),
    # build_pipeline
    ("VkPipeline Renderer::build_pipeline(const PipelineKey& k, VkShaderModule vs, VkShaderModule ps,\n"
     "                                    VkPipelineLayout layout) {\n",
     "VkPipeline Renderer::build_pipeline(const PipelineKey& k, VkShaderModule vs, VkShaderModule ps,\n"
     "                                    VkPipelineLayout layout, VkShaderModule gs) {\n"),
    ("    VkPipelineShaderStageCreateInfo stages[2]{};\n"
     "    stages[0].sType = stages[1].sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;\n",
     "    VkPipelineShaderStageCreateInfo stages[3]{};\n"
     "    stages[0].sType = stages[1].sType = stages[2].sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;\n"
     "    stages[2].stage = VK_SHADER_STAGE_GEOMETRY_BIT; // port/patch_gs.py\n"
     "    stages[2].module = gs;\n"
     "    stages[2].pName = \"main\";\n"),
    ("    gci.stageCount = 2;\n",
     "    gci.stageCount = gs != VK_NULL_HANDLE ? 3 : 2;\n"),
    # draw(): shaders
    ("    const ShaderModule* vs = shader(Stage::kVertex, r(reg::SQ_PGM_START_VS) << 8, r(reg::SQ_PGM_START_VS + 4) << 3,\n"
     "                                    r(reg::SQ_PGM_START_FS) << 8, r(reg::SQ_PGM_START_FS + 4) << 3, vs_env);\n",
     "    // port/patch_gs.py: a geometry draw runs ES (vertex stage) -> GS (copy shader inlined) -> pixel shader.\n"
     "    static const bool no_gs = std::getenv(\"TTT2_NO_GS\") != nullptr;\n"
     "    const bool gs_mode = !no_gs && (r(reg::VGT_GS_MODE) & 3) != 0;\n"
     "    const ShaderModule* gs = nullptr;\n"
     "    const ShaderModule* vs = nullptr;\n"
     "    if (gs_mode) {\n"
     "        ShaderEnvironment es_env = vs_env;\n"
     "        es_env.gs_part = 1;\n"
     "        es_env.rects = false;\n"
     "        es_env.esgs_slots = static_cast<uint8_t>(std::clamp<uint32_t>(((r(reg::SQ_ESGS_RING_ITEMSIZE) & 0x7FFF) + 3) / 4, 1, 32));\n"
     "        vs = shader(Stage::kVertex, r(reg::SQ_PGM_START_ES) << 8, r(reg::SQ_PGM_START_ES + 4) << 3,\n"
     "                    r(reg::SQ_PGM_START_FS) << 8, r(reg::SQ_PGM_START_FS + 4) << 3, es_env);\n"
     "        gs = gs_shader(r(reg::SQ_PGM_START_GS) << 8, r(reg::SQ_PGM_START_GS + 4) << 3, r(reg::SQ_PGM_START_VS) << 8,\n"
     "                       r(reg::SQ_PGM_START_VS + 4) << 3, vs_env, es_env.esgs_slots, topology_class + 1,\n"
     "                       r(reg::VGT_GS_OUT_PRIM_TYPE) & 3,\n"
     "                       std::max<uint32_t>(((r(reg::SQ_GS_VERT_ITEMSIZE) & 0x7FFF) + 3) / 4, 1));\n"
     "        if (gs == nullptr) vs = nullptr;\n"
     "    } else {\n"
     "        vs = shader(Stage::kVertex, r(reg::SQ_PGM_START_VS) << 8, r(reg::SQ_PGM_START_VS + 4) << 3,\n"
     "                    r(reg::SQ_PGM_START_FS) << 8, r(reg::SQ_PGM_START_FS + 4) << 3, vs_env);\n"
     "    }\n"),
    ("    const Pipeline* pipe = pipeline(regs, vs, ps, formats, color_count, depth_format, topology_class);\n",
     "    const Pipeline* pipe = pipeline(regs, vs, ps, formats, color_count, depth_format, topology_class, gs);\n"),
    # GS uniform blocks
    ("    // port/patch_vte_window.py: window-coordinate draws (viewport transform off).\n",
     "    if (gs) { // port/patch_gs.py: the geometry shader's uniform blocks\n"
     "        for (uint32_t i = 0; i < 16; ++i) {\n"
     "            if (const uint32_t a = r(reg::SQ_ALU_CONST_CACHE_GS_0 + i * 4)) {\n"
     "                dc.gs_cb[i] = buffer_descriptor(a << 8, r(reg::SQ_ALU_CONST_BUFFER_SIZE_GS_0 + i * 4) << 8, 16);\n"
     "            }\n"
     "        }\n"
     "    }\n"
     "    // port/patch_vte_window.py: window-coordinate draws (viewport transform off).\n"),
])
