// A Wii U title on the cafe runtime, with nothing of any one game in it: like the runtime's
// smash_main.cpp without Smash's netplay, online sign-in, logo and overlay.
// usage: cafegame [UPDATE] BASE      (title folders with code/, content/, meta/)
// CAFE_RPX names the executable in code/ (default: the only .rpx there).

#include "cafe/export.h"
#include "cafe/generated.h"
#include "cafe/layout.h"
#include "cafe/runtime.h"
#include "cafe/sysmem.h"
#include "cafe/vfs.h"

#include "gpu/gpu.h"
#include "host/audio.h"
#include "host/display_settings.h"
#include "host/window.h"

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <string>
#include <thread>
#include <vector>

namespace cafe::os {
void init_heaps(uint32_t mem2_begin);
int run_main_thread(uint32_t entry, uint32_t argc, uint32_t argv, uint32_t stack_size,
                    uint32_t sda_base, uint32_t sda2_base);
void set_preinit_user(uint32_t function);
void set_font_folder(const std::filesystem::path& folder);
} // namespace cafe::os

namespace cafe::gpu::vk {
void early_guest_memory(); // port/patch_guest_dmabuf.py: TTT2_GUEST_DMABUF=1 (Linux)
}

// Program modules next to the title (port/modules.cpp sets it; null in ports without modules).
void (*cafegame_module_loader)(cafe::LoadedImage& title) = nullptr;

namespace {

void init_data_imports() {
    for (size_t i = 0; i < cafe_guest_import_count; ++i) {
        const cafe::GuestImport& import = cafe_guest_imports[i];
        if (!import.is_data) continue;
        // Linked to a translated module's own object (port/patch_modules.py): nothing to create.
        if (import.address < cafe::layout::kDataImportBase || import.address >= cafe::layout::kDataImportLimit) continue;
        if (const cafe::DataExport* data = cafe::find_data_export(import.module, import.name)) {
            data->initialize(import.address);
        } else {
            std::fprintf(stderr, "cafegame: warning: data import %s:%s is not provided\n", import.module,
                         import.name);
        }
    }
}

uint32_t guest_strdup(const char* text) {
    const uint32_t address = cafe::system_alloc(static_cast<uint32_t>(std::strlen(text) + 1));
    std::memcpy(cafe::guest_pointer(address), text, std::strlen(text) + 1);
    return address;
}

} // namespace

int main(int argc, char** argv) {
    using namespace cafe;
    if (argc != 2 && argc != 3) {
        std::fprintf(stderr, "usage: %s [UPDATE] BASE\n", argv[0]);
        return 2;
    }
    install_fault_handler();
    std::vector<std::filesystem::path> layers(argv + 1, argv + argc);
    vfs::open_game(layers);
    const std::filesystem::path here = std::filesystem::absolute(argv[0]).parent_path();
    if (const char* save = std::getenv("CAFE_SAVE_DIR")) {
        vfs::set_save_root(save);
    } else {
        vfs::set_save_root(here / "save");
    }
    std::string name;
    if (const char* given = std::getenv("CAFE_RPX")) {
        name = given;
    } else {
        for (const auto& entry : std::filesystem::directory_iterator(layers.front() / "code")) {
            if (entry.path().extension() == ".rpx") name = entry.path().filename().string();
        }
    }
    const auto rpx = vfs::read_whole("/vol/code/" + name);
    if (!rpx) fatal("the game folders have no code/%s", name.c_str());
    reserve_guest_memory();
    cafe::gpu::vk::early_guest_memory(); // before anything is loaded into guest memory
    init_system_heap();
    // The title's data imports from translated modules (port/patch_modules.py), as when it was translated.
    if (std::filesystem::exists(here / "data-imports.map")) {
#ifdef _WIN32
        _putenv_s("CAFE_DATA_IMPORT_MAP", (here / "data-imports.map").string().c_str());
#else
        ::setenv("CAFE_DATA_IMPORT_MAP", (here / "data-imports.map").string().c_str(), 1);
#endif
    }
    LoadedImage image = load_image(*rpx);
    build_dispatch_table();
    if (cafegame_module_loader) cafegame_module_loader(image);
    os::init_heaps(image.data_end);
    init_data_imports();
    os::set_preinit_user(image.preinit_user);
    os::set_font_folder(here / "fonts");
    gpu::set_cache_directory(here / "cache");
    host::display::set_file(here / "display.ini", "cafegame");
    std::fprintf(stderr, "cafegame: loaded %s, entry 0x%08X, %zu/%zu guest entries compiled\n", name.c_str(),
                 image.entry_point, cafe_program_info.compiled_entries, cafe_program_info.total_entries);

    const uint32_t guest_argv = system_alloc(8);
    *reinterpret_cast<uint32_t*>(guest_pointer(guest_argv)) = __builtin_bswap32(guest_strdup(name.c_str()));
    const auto run = [&] {
        return os::run_main_thread(image.entry_point, 1, guest_argv, image.stack_size, image.sda_base,
                                   image.sda2_base);
    };
    const char* gpu = std::getenv("TTT2_GPU");
    const bool headless = (gpu && std::strcmp(gpu, "null") == 0) || !host::open_window("cafegame");
    host::open_audio();
    if (headless) return run();
    std::atomic<bool> finished{false};
    int result = 0;
    std::thread title([&] {
        result = run();
        finished = true;
    });
    if (!host::run_event_loop([&] { return finished.load(); })) std::_Exit(0); // window closed
    title.join();
    return result;
}
