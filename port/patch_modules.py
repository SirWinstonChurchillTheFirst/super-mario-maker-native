"""Several program modules in one port (Mario Kart 8: Turbo.rpx + mvplayer.rpl), MK8 multi-module steps 2-4.

Step 1 (port/patch_rpl_rebase.py) translates an RPL at moved addresses. This patch adds what is needed to link it:
- rpx.cpp: CAFE_DATA_IMPORT_FIRST=<n> starts a module's data-import slots at slot n (the title uses the first ones);
  CAFE_DATA_IMPORT_MAP=<file> ("module name hexaddress" per line) resolves data imports of the title to objects a
  translated module exports (its .dexports, already moved), instead of a slot of their own. Used by cafe-recomp
  when translating, and by the runtime when it loads the same executable (game_main.cpp sets it from
  data-imports.map next to the program).
- dispatch.cpp: register_guest_function(address, function) adds a module's functions to the indirect-call table.
- CMakeLists.txt: GAME_MODULE_DIRS (list) = more cafe-recomp output folders compiled into the same program; their
  tables are renamed by port/module_rename.py so they do not clash with the title's.
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")


def patch(rel, pairs):
    path = os.path.join(ROOT, rel)
    text = open(path, encoding="utf-8").read()
    if "patch_modules" in text:
        print("already:", rel)
        return
    for old, new in pairs:
        if text.count(old) != 1:
            sys.exit(f"{rel}: anchor not found once: {old[:70]!r}")
        text = text.replace(old, new)
    open(path, "w", encoding="utf-8", newline="").write(text)
    print("patched:", rel)


patch("recomp/src/rpx.cpp", [
    ("    std::map<uint32_t, uint32_t> data_slots;\n"
     "    for (auto& import : image.imports) {\n"
     "        if (import.is_data) {\n"
     "            import.address = layout::kDataImportBase +\n"
     "                             static_cast<uint32_t>(data_slots.size()) *\n"
     "                                 layout::kDataImportSlot;\n",
     "    std::map<uint32_t, uint32_t> data_slots;\n"
     "    // port/patch_modules.py: a module's slots after the title's; data a translated module exports.\n"
     "    uint32_t first_slot = 0;\n"
     "    if (const char* f = std::getenv(\"CAFE_DATA_IMPORT_FIRST\")) first_slot = static_cast<uint32_t>(std::strtoul(f, nullptr, 0));\n"
     "    std::map<std::string, uint32_t> linked;\n"
     "    if (const char* m = std::getenv(\"CAFE_DATA_IMPORT_MAP\")) {\n"
     "        if (FILE* file = std::fopen(m, \"r\")) {\n"
     "            char module[128], name[256];\n"
     "            unsigned int address;\n"
     "            while (std::fscanf(file, \"%127s %255s %x\", module, name, &address) == 3) {\n"
     "                linked[std::string(module) + \":\" + name] = address;\n"
     "            }\n"
     "            std::fclose(file);\n"
     "        }\n"
     "    }\n"
     "    uint32_t used_slots = 0;\n"
     "    for (auto& import : image.imports) {\n"
     "        if (import.is_data) {\n"
     "            if (const auto l = linked.find(import.module + \":\" + import.name); l != linked.end()) {\n"
     "                import.address = l->second;\n"
     "                data_slots[import.stub_address] = import.address;\n"
     "                continue;\n"
     "            }\n"
     "            import.address = layout::kDataImportBase +\n"
     "                             (first_slot + used_slots++) *\n"
     "                                 layout::kDataImportSlot;\n"),
])

# rpx.cpp needs <cstdio>/<cstdlib>/<string>/<map>
path = os.path.join(ROOT, "recomp/src/rpx.cpp")
text = open(path, encoding="utf-8").read()
for inc in ("#include <cstdio>\n", "#include <cstdlib>\n", "#include <map>\n", "#include <string>\n"):
    if inc not in text:
        first = text.index("#include <")
        text = text[:first] + inc + text[first:]
open(path, "w", encoding="utf-8", newline="").write(text)

patch("runtime/src/dispatch.cpp", [
    ("void build_dispatch_table() {\n",
     "// port/patch_modules.py: a translated module's functions (it is loaded after the title).\n"
     "void register_guest_function(uint32_t address, PPCFunc* function) { insert(address, function, function != nullptr); }\n"
     "\n"
     "void build_dispatch_table() {\n"),
    ("    const size_t wanted = (cafe_guest_function_count + cafe_guest_import_count + 0x10000) * 2;\n",
     "    const size_t wanted = (cafe_guest_function_count + cafe_guest_import_count + 0x40000) * 2; // + modules\n"),
])

patch("runtime/include/cafe/runtime.h", [
    ("void build_dispatch_table();\n",
     "void build_dispatch_table();\n"
     "// A module's translated function, for indirect calls (port/patch_modules.py).\n"
     "void register_guest_function(uint32_t address, PPCFunc* function);\n"),
])

patch("CMakeLists.txt", [
    ("    include(${GAME_GENERATED_DIR}/sources.cmake)\n"
     "    add_library(game_generated OBJECT ${CAFE_GENERATED_SOURCES})\n",
     "    include(${GAME_GENERATED_DIR}/sources.cmake)\n"
     "    # port/patch_modules.py: more modules (their tables renamed by port/module_rename.py)\n"
     "    set(GAME_MODULE_DIRS \"\" CACHE STRING \"more cafe-recomp output folders (program modules)\")\n"
     "    set(GAME_ALL_SOURCES ${CAFE_GENERATED_SOURCES})\n"
     "    foreach(dir ${GAME_MODULE_DIRS})\n"
     "        include(${dir}/sources.cmake)\n"
     "        list(APPEND GAME_ALL_SOURCES ${CAFE_GENERATED_SOURCES})\n"
     "    endforeach()\n"
     "    add_library(game_generated OBJECT ${GAME_ALL_SOURCES})\n"),
])
