#!/usr/bin/env python3
"""patch_vtx_const_fields.py RUNTIME_SRC_DIR (…/runtime/src)

Vertex fetches with USE_CONST_FIELDS take data format, number format, sign and endian swap from the attribute
buffer's resource (SQ_VTX_CONSTANT_WORD2: DATA_FORMAT 20-25, NUM_FORMAT_ALL 26-27, FORMAT_COMP_ALL 28,
ENDIAN_SWAP 30-31) instead of the instruction. The translator refused them ("vertex fetch with formats from the
resource"), so Super Mario Maker's terrain shader (vs f476431ad0da0944) was never drawn: the ground was missing.
The vertex environment now carries those bits of the 16 attribute resources (and its key includes them)."""
import sys

src = sys.argv[1]


def patch(rel, pairs):
    p = src + "/" + rel
    s = open(p, encoding="utf-8").read()
    if "patch_vtx_const_fields" in s:
        print(rel + ": already applied")
        return
    for old, new in pairs:
        assert s.count(old) == 1, rel + ": pattern not found or not unique: " + old[:70]
        s = s.replace(old, new)
    open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("patched", p)


patch("latte/translate.h", [(
    "    uint16_t stream_out_stride[4] = {}; // bytes per vertex\n",
    "    uint16_t stream_out_stride[4] = {}; // bytes per vertex\n"
    "    // port/patch_vtx_const_fields.py: SQ_VTX_CONSTANT_WORD2 bits 19-31 (formats, endian) of attribute buffers 0-15,\n"
    "    // for fetches with USE_CONST_FIELDS.\n"
    "    uint32_t vtx_const_word2[16] = {};\n")])

patch("latte/environment.cpp", [
    ("    env.point_size_export = (r(reg::PA_CL_VS_OUT_CNTL) >> 24) & 1;\n",
     "    env.point_size_export = (r(reg::PA_CL_VS_OUT_CNTL) >> 24) & 1;\n"
     "    if (stage == Stage::kVertex) { // port/patch_vtx_const_fields.py\n"
     "        for (uint32_t i = 0; i < 16; ++i) {\n"
     "            const uint32_t base = kResourceBase + (resource::kVsAttrib + i) * resource::kWords * 4;\n"
     "            env.vtx_const_word2[i] = r(base + 8) & 0xFFF80000u;\n"
     "        }\n"
     "    }\n"),
    ("        for (uint16_t s : env.stream_out_stride) h.add(s);\n",
     "        for (uint16_t s : env.stream_out_stride) h.add(s);\n"
     "        for (uint32_t w : env.vtx_const_word2) h.add(w); // port/patch_vtx_const_fields.py\n"),
])

patch("latte/translate.cpp", [(
    """    if (v.use_const_fields) {
        fail("vertex fetch with formats from the resource");
        return;
    }
    const int buffer = static_cast<int>(v.buffer_id) - 160;
    const std::string b = (buffer >= 0 && buffer < 16) ? format("dc.vb[%d]", buffer) : std::string("uvec4(0)");
""",
    """    const int buffer = static_cast<int>(v.buffer_id) - 160;
    // port/patch_vtx_const_fields.py: USE_CONST_FIELDS -> formats from the attribute buffer's resource.
    uint32_t data_format = v.data_format, num_format = v.num_format, endian = v.endian;
    bool format_signed = v.format_signed;
    if (v.use_const_fields) {
        const uint32_t w2 = (buffer >= 0 && buffer < 16) ? env_.vtx_const_word2[buffer] : 0;
        if (((w2 >> 20) & 0x3F) == 0) {
            fail("vertex fetch with formats from the resource (none set)");
            return;
        }
        data_format = (w2 >> 20) & 0x3F;
        num_format = (w2 >> 26) & 3;
        format_signed = ((w2 >> 28) & 1) != 0;
        endian = (w2 >> 30) & 3;
    }
    const std::string b = (buffer >= 0 && buffer < 16) ? format("dc.vb[%d]", buffer) : std::string("uvec4(0)");
""")])

# the fetch itself and the "1" for integer formats use the chosen fields
p = src + "/latte/translate.cpp"
s = open(p, encoding="utf-8").read()
old = """    const std::string value = fetch_value(b, index + " * " + b + ".w + " + format("%uu", v.offset), v.data_format,
                                          v.num_format, v.format_signed, v.endian, false);
    line("ivec4 f = " + value + ";");
    const char* one = v.num_format == 1 ? "1" : "0x3F800000";"""
new = """    const std::string value = fetch_value(b, index + " * " + b + ".w + " + format("%uu", v.offset), data_format,
                                          num_format, format_signed, endian, false);
    line("ivec4 f = " + value + ";");
    const char* one = num_format == 1 ? "1" : "0x3F800000";"""
if old in s:
    s = s.replace(old, new)
    open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("patched fetch call")
else:
    assert new in s, "fetch call pattern not found"
