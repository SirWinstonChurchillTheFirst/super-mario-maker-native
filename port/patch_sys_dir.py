"""System titles' files (the Mii resources FFLRes*.dat of 0005001B-10056000 and the like) read from a host folder.

Rio 2016, Mario Kart 8, Super Mario Maker and 3D World open
/vol/storage_mlc01/sys/title/0005001b/10056000/content/FFLResMiddle(LG).dat (the path FFLGetResourcePath gives).
They are not part of a game dump: only the player's own console has them. Cemu keeps them in its mlc01 folder,
<mlc01>/sys/title/0005001b/10056000/content/ (on Batocera: /userdata/saves/wiiu/sys/...).

Now /vol/storage_mlc01/sys/<rest> is served read-only from CAFE_SYS_DIR/<rest> (a Cemu-style "sys" folder) when
CAFE_SYS_DIR is set; one log line names the folder. Without it (or without the file) such opens fail as before.
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "runtime/src/vfs.cpp")
text = open(path, encoding="utf-8").read()
if "patch_sys_dir" in text:
    print("already: vfs.cpp")
    sys.exit(0)

pairs = [
    ("    std::vector<std::string> save_parts; // inside the save root, or the DLC folder for kAoc\n};\n",
     "    std::vector<std::string> save_parts; // inside the save root, or the DLC folder for kAoc\n"
     "    bool sys = false; // port/patch_sys_dir.py: kAoc-like read-only area in CAFE_SYS_DIR\n};\n"),
    ("std::map<std::string, fs::path> g_aoc; // \"aoc0005000c10144f00\" -> the DLC's content folder\n",
     "std::map<std::string, fs::path> g_aoc; // \"aoc0005000c10144f00\" -> the DLC's content folder\n\n"
     "// port/patch_sys_dir.py: CAFE_SYS_DIR = a Cemu-style mlc01/sys folder serving /vol/storage_mlc01/sys read-only.\n"
     "const fs::path& sys_root() {\n"
     "    static const fs::path root = [] {\n"
     "        const char* v = std::getenv(\"CAFE_SYS_DIR\");\n"
     "        if (v == nullptr || *v == 0) return fs::path{};\n"
     "        std::error_code ec;\n"
     "        const bool ok = fs::is_directory(fs::path(v), ec);\n"
     "        std::fprintf(stderr, \"cafe: system titles from CAFE_SYS_DIR=%s%s\\n\", v, ok ? \"\" : \" (no such folder)\");\n"
     "        return ok ? fs::path(v) : fs::path{};\n"
     "    }();\n"
     "    return root;\n"
     "}\n"),
    ("fs::path area_root(const Resolved& r, std::string_view path) {\n    if (r.area != Area::kAoc) return g_save_root;\n",
     "fs::path area_root(const Resolved& r, std::string_view path) {\n    if (r.area != Area::kAoc) return g_save_root;\n"
     "    if (r.sys) return sys_root();\n"),
    ("    std::string lower = parts[1];\n    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);\n    if (g_aoc.count(lower)) {\n",
     "    if (parts.size() >= 3 && iequals(parts[1], \"storage_mlc01\") && iequals(parts[2], \"sys\") && !sys_root().empty()) {\n"
     "        r.area = Area::kAoc; // read-only host folder\n"
     "        r.sys = true;\n"
     "        r.save_parts.assign(parts.begin() + 3, parts.end());\n"
     "        return r;\n"
     "    }\n"
     "    std::string lower = parts[1];\n    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);\n    if (g_aoc.count(lower)) {\n"),
]
for old, new in pairs:
    assert text.count(old) == 1, old[:60]
    text = text.replace(old, new)
open(path, "w", encoding="utf-8", newline="\n").write(text)
print("patched: vfs.cpp (CAFE_SYS_DIR)")
