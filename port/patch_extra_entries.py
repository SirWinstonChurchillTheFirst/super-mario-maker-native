"""CAFE_EXTRA_ENTRIES=<hex,hex,...>: function starts the recompiler's discovery missed (cafe-recomp option).

Super Mario Maker calls 0x0272B9A4 indirectly (a small function right after another one's blr, reached only through
a pointer the analysis does not see); the runtime stops with "not the start of any guest function". The listed
addresses split the code like the other entry points. Used when translating only; the runtime is unchanged.
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "recomp/src/program.cpp")
text = open(path, encoding="utf-8").read()
if "CAFE_EXTRA_ENTRIES" in text:
    print("already: program.cpp")
    sys.exit(0)
old = "    std::set<uint32_t> starts = entered_addresses(image);\n"
new = old + ("    // port/patch_extra_entries.py: starts the discovery missed, given by hand.\n"
             "    if (const char* extra = std::getenv(\"CAFE_EXTRA_ENTRIES\")) {\n"
             "        for (const char* p = extra; *p;) {\n"
             "            char* end = nullptr;\n"
             "            const unsigned long a = std::strtoul(p, &end, 16);\n"
             "            if (end == p) break;\n"
             "            starts.insert(static_cast<uint32_t>(a));\n"
             "            p = *end == ',' ? end + 1 : end;\n"
             "        }\n"
             "    }\n")
if text.count(old) != 1:
    sys.exit("program.cpp: anchor not found")
text = text.replace(old, new)
for inc in ("#include <cstdlib>\n",):
    if inc not in text:
        first = text.index("#include <")
        text = text[:first] + inc + text[first:]
open(path, "w", encoding="utf-8", newline="").write(text)
print("patched: program.cpp")
