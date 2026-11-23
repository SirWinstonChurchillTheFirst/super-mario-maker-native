"""Shared saves under /vol/storage_mlc01/usr (the Mii databases FFL_ODB.dat / FFL_HDB.dat) live in the port's own save
folder, and _SYSGetSystemApplicationTitleId names the real system applications.

FFL (the Mii library linked into Rio 2016, Mario Kart 8, Super Mario Maker, ...) keeps its Mii databases in Mii
Maker's shared save: SAVEGetSharedSaveDataPath(_SYSGetSystemApplicationTitleId(4)) + "db/FFL_ODB.dat" / FFL_HDB.dat.
The runtime answered title 0 and had no /vol/storage_mlc01/usr at all, so FFL's boot load got an FS error it treats
as fatal (FFLInitResEx 19): no Miis, and Rio read through a null MiiData after "Now loading...".

Now _SYSGetSystemApplicationTitleId gives the console's ids (Europe; region in the low half-word: JPN 0x000,
USA 0x100, EUR 0x200; CAFE_SYS_REGION=jpn|usa|eur), and /vol/storage_mlc01/usr/<rest> is a writable folder
<save root>/mlc01/usr/<rest>; a file written there gets its folders made. FFL then finds no database, makes empty
ones and saves them there (the player's own Cemu or console data is never read or written).
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")


def patch(rel, pairs, marker):
    path = os.path.join(ROOT, rel)
    text = open(path, encoding="utf-8").read()
    if marker in text:
        print("already:", rel)
        return
    for old, new in pairs:
        assert text.count(old) == 1, (rel, old[:70])
        text = text.replace(old, new)
    open(path, "w", encoding="utf-8", newline="\n").write(text)
    print("patched:", rel)


patch("runtime/src/vfs.cpp", [
    ("    bool sys = false; // port/patch_sys_dir.py: kAoc-like read-only area in CAFE_SYS_DIR\n",
     "    bool sys = false; // port/patch_sys_dir.py: kAoc-like read-only area in CAFE_SYS_DIR\n"
     "    bool mlc = false; // port/patch_mlc_usr.py: /vol/storage_mlc01/usr in the save root (mlc01/usr)\n"),
    ("    if (parts.size() >= 3 && iequals(parts[1], \"storage_mlc01\") && iequals(parts[2], \"sys\") && !sys_root().empty()) {\n",
     "    if (parts.size() >= 3 && iequals(parts[1], \"storage_mlc01\") && iequals(parts[2], \"usr\")) {\n"
     "        r.area = Area::kSave;\n"
     "        r.mlc = true;\n"
     "        r.save_parts = {\"mlc01\"};\n"
     "        r.save_parts.insert(r.save_parts.end(), parts.begin() + 2, parts.end());\n"
     "        return r;\n"
     "    }\n"
     "    if (parts.size() >= 3 && iequals(parts[1], \"storage_mlc01\") && iequals(parts[2], \"sys\") && !sys_root().empty()) {\n"),
    ("    if (r.area == Area::kSave) return open_host(host_resolve(g_save_root, r.save_parts), mode, handle);\n",
     "    if (r.area == Area::kSave && r.mlc && mode.find_first_of(\"wa\") != std::string_view::npos) {\n"
     "        std::error_code ec; // port/patch_mlc_usr.py: the shared save's folders exist on a console\n"
     "        fs::create_directories(host_resolve(g_save_root, r.save_parts).parent_path(), ec);\n"
     "    }\n"
     "    if (r.area == Area::kSave) return open_host(host_resolve(g_save_root, r.save_parts), mode, handle);\n"),
], "patch_mlc_usr")

patch("runtime/src/os/offline_services.cpp", [
    ("#include <cstdio>\n#include <cstring>\n", "#include <cstdio>\n#include <cstdlib>\n#include <cstring>\n"),
    ("CAFE_EXPORT(sysapp, _SYSGetSystemApplicationTitleId, zero64);\n",
     "// port/patch_mlc_usr.py: the system applications' title ids (wut's SYSTEM_APP_ID order), Europe unless\n"
     "// CAFE_SYS_REGION says jpn or usa. FFL finds the Mii databases in Mii Maker's (4) shared save.\n"
     "uint64_t sys_application_title_id(uint32_t app) {\n"
     "    // Only the two whose ids are certain: Wii U Menu (0) and Mii Maker (4); the others stay 0 as before.\n"
     "    const uint64_t base = app == 0 ? 0x0005001010040000ull : app == 4 ? 0x000500101004A000ull : 0;\n"
     "    if (base == 0) return 0;\n"
     "    uint64_t region = 0x200;\n"
     "    if (const char* r = std::getenv(\"CAFE_SYS_REGION\")) {\n"
     "        if (r[0] == 'j' || r[0] == 'J') region = 0x000;\n"
     "        else if (r[0] == 'u' || r[0] == 'U') region = 0x100;\n"
     "    }\n"
     "    return base | region;\n"
     "}\n"
     "CAFE_EXPORT(sysapp, _SYSGetSystemApplicationTitleId, sys_application_title_id);\n"),
], "patch_mlc_usr")
