"""Game modules loaded at OSDynLoad_Acquire (Mario Party 10: 91 minigame/board RPLs, port/modules_dyn.cpp).

- runtime.h: cafe::GameModuleHooks / g_game_module_hooks (set by the port; null = no game modules) and
  g_dispatch_extra_entries (room in the indirect-call table for module functions registered after the title).
- dynload.cpp: OSDynLoad_Acquire / FindExport / Release first ask the hooks (outside the kernel lock, because Acquire
  runs the module's entry point, which is guest code); everything else stays as before (system libraries).
- dispatch.cpp: the table is sized with g_dispatch_extra_entries (default 0x40000 = as before).
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")


def patch(rel, pairs):
    path = os.path.join(ROOT, rel)
    text = open(path, encoding="utf-8").read()
    if "patch_dynload_modules" in text:
        print("already:", rel)
        return
    for old, new in pairs:
        if text.count(old) != 1:
            sys.exit(f"{rel}: anchor not found once: {old[:70]!r}")
        text = text.replace(old, new)
    open(path, "w", encoding="utf-8", newline="").write(text)
    print("patched:", rel)


patch("runtime/include/cafe/runtime.h", [
    ("void register_guest_function(uint32_t address, PPCFunc* function);\n",
     "void register_guest_function(uint32_t address, PPCFunc* function);\n"
     "// port/patch_dynload_modules.py: extra room in the indirect-call table (set before main, e.g. by a\n"
     "// static initializer of a port with many modules).\n"
     "extern size_t g_dispatch_extra_entries;\n"
     "// Game modules the port loads when the title asks OSDynLoad for them (null = none).\n"
     "struct GameModuleHooks {\n"
     "    // true: name is a game module; it is loaded (entry run on first use) and *handle set.\n"
     "    bool (*acquire)(const char* name, uint32_t* handle);\n"
     "    // -1: not a game module's handle; 0: found (*address set); 1: no such export.\n"
     "    int (*find_export)(uint32_t handle, bool is_data, const char* name, uint32_t* address);\n"
     "    // true: handle was a game module's.\n"
     "    bool (*release)(uint32_t handle);\n"
     "};\n"
     "extern const GameModuleHooks* g_game_module_hooks;\n"),
])

patch("runtime/src/dispatch.cpp", [
    ("// port/patch_modules.py: a translated module's functions (it is loaded after the title).\n",
     "size_t g_dispatch_extra_entries = 0x40000; // port/patch_dynload_modules.py\n"
     "\n"
     "// port/patch_modules.py: a translated module's functions (it is loaded after the title).\n"),
    ("    const size_t wanted = (cafe_guest_function_count + cafe_guest_import_count + 0x40000) * 2; // + modules\n",
     "    const size_t wanted = (cafe_guest_function_count + cafe_guest_import_count + g_dispatch_extra_entries) * 2; // + modules\n"),
])

patch("runtime/src/os/dynload.cpp", [
    ("namespace cafe::os {\nnamespace {\n",
     "namespace cafe {\n"
     "const GameModuleHooks* g_game_module_hooks = nullptr; // port/patch_dynload_modules.py\n"
     "}\n"
     "\n"
     "namespace cafe::os {\nnamespace {\n"),
    ("uint32_t OSDynLoad_Acquire(uint32_t name, be<uint32_t>* handle) {\n"
     "    KernelLock lock(kernel_mutex());\n",
     "uint32_t OSDynLoad_Acquire(uint32_t name, be<uint32_t>* handle) {\n"
     "    if (g_game_module_hooks != nullptr && name != 0) { // port/patch_dynload_modules.py\n"
     "        uint32_t h = 0;\n"
     "        const std::string wanted(guest_string(name));\n"
     "        if (g_game_module_hooks->acquire(wanted.c_str(), &h)) {\n"
     "            if (handle) *handle = h;\n"
     "            return 0;\n"
     "        }\n"
     "    }\n"
     "    KernelLock lock(kernel_mutex());\n"),
    ("uint32_t OSDynLoad_FindExport(uint32_t handle, uint32_t is_data, uint32_t name, be<uint32_t>* address) {\n"
     "    KernelLock lock(kernel_mutex());\n",
     "uint32_t OSDynLoad_FindExport(uint32_t handle, uint32_t is_data, uint32_t name, be<uint32_t>* address) {\n"
     "    if (g_game_module_hooks != nullptr && name != 0) { // port/patch_dynload_modules.py\n"
     "        uint32_t a = 0;\n"
     "        const std::string wanted(guest_string(name));\n"
     "        const int r = g_game_module_hooks->find_export(handle, is_data != 0, wanted.c_str(), &a);\n"
     "        if (r == 0) {\n"
     "            if (address) *address = a;\n"
     "            return 0;\n"
     "        }\n"
     "        if (r == 1) return 0xBAD10001u; // OSDynLoad: export not found\n"
     "    }\n"
     "    KernelLock lock(kernel_mutex());\n"),
    ("void OSDynLoad_Release(uint32_t) {}\n",
     "void OSDynLoad_Release(uint32_t handle) {\n"
     "    if (g_game_module_hooks != nullptr) g_game_module_hooks->release(handle); // port/patch_dynload_modules.py\n"
     "}\n"),
])
