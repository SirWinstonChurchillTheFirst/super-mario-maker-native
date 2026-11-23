"""TTT2_DUMP_WB=<seconds> (test switch): from that many seconds after start, each written-back render target is saved
once as raw bytes (as the GPU produced them, before tiling) to $TTT2_CAPTURE/wb_<address>_<pitch>x<height>_<bpp>.bin.

For comparing the small targets Mario Tennis reads back between the console's Radeon and the PC, without a full frame
trace. Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "runtime/src/gpu/vulkan/targets.cpp")
text = open(path, encoding="utf-8").read()
if "patch_dump_wb" in text:
    print("already: targets.cpp")
    sys.exit(0)
old = "        TiledLevel level{};\n        level.data = guest_pointer(w.address);\n"
new = ("        { // port/patch_dump_wb.py\n"
       "            static const double dump_at = [] {\n"
       "                const char* v = std::getenv(\"TTT2_DUMP_WB\");\n"
       "                return v ? std::atof(v) : -1.0;\n"
       "            }();\n"
       "            static const auto started = std::chrono::steady_clock::now();\n"
       "            static std::set<uint32_t> dumped;\n"
       "            const char* dir = std::getenv(\"TTT2_CAPTURE\");\n"
       "            if (dump_at >= 0 && dir != nullptr &&\n"
       "                std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count() >= dump_at &&\n"
       "                dumped.insert(w.address).second) {\n"
       "                char name[96];\n"
       "                std::snprintf(name, sizeof(name), \"/wb_%08X_%ux%u_%u.bin\", w.address, w.pitch, w.height, w.bpp);\n"
       "                if (FILE* f = std::fopen((std::string(dir) + name).c_str(), \"wb\")) {\n"
       "                    std::fwrite(data, 1, size_t{w.pitch} * w.height * (w.bpp / 8), f);\n"
       "                    std::fclose(f);\n"
       "                    std::fprintf(stderr, \"ttt2: dumped write-back %s\\n\", name);\n"
       "                }\n"
       "            }\n"
       "        }\n" + old)
if text.count(old) != 1:
    sys.exit("targets.cpp: anchor not found")
text = text.replace(old, new)
for inc in ("#include <set>\n", "#include <chrono>\n", "#include <string>\n", "#include <cstdio>\n"):
    if inc not in text:
        first = text.index("#include <")
        text = text[:first] + inc + text[first:]
open(path, "w", encoding="utf-8", newline="").write(text)
print("patched: targets.cpp")
