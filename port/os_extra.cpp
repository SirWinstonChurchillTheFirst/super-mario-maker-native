// System functions the runtime (written for Tekken Tag 2 and Smash) lacks and other titles call.
// Each answers as a console would in the situation the port is in: offline, no amiibo, no Wii Remotes,
// GamePad lying still. Where something real is left out, a line says so once.

#include "cafe/export.h"
#include "cafe/vfs.h" // port/patch_fs_cwd.py
#include "cafe/guest.h"
#include "cafe/runtime.h"
#include "cafe/sysmem.h"
#include "os/kernel.h"
#include "gpu/gpu.h"

#include <map>
#include <zlib.h>

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <algorithm>
#include <unordered_map>
#include <vector>
#include <thread>
#ifdef _WIN32
#include <windows.h>
#else
#include <dlfcn.h>
#endif

namespace cafe::os {
namespace {

constexpr uint32_t kClosed = 0xA0A0CE00u; // the nn::Result the runtime gives for closed online services
constexpr uint32_t kNfpNoTag = 0xA1B10400u; // as os/offline_services.cpp

void once(std::atomic<bool>& said, const char* what) {
    if (!said.exchange(true)) std::fprintf(stderr, "port: %s\n", what);
}

void no_op() {}
int32_t zero() { return 0; }
int32_t one() { return 1; }
int32_t minus_one() { return -1; }
uint32_t closed() { return kClosed; }
uint32_t no_tag() { return kNfpNoTag; }

// ------------------------------------------------------------------ nn_fp, nn_ac, nn_act: offline
int32_t ac_close_status(be<uint32_t>* status) {
    if (status) *status = 0;
    return 0;
}

// ------------------------------------------------------------------ nn_save: no other title's saves
constexpr int32_t kFsNotFound = -6;
int32_t fs_not_found() { return kFsNotFound; }

// ------------------------------------------------------------------ zlib's one-call forms
int32_t z_compress2(uint8_t* dest, be<uint32_t>* dest_len, const uint8_t* source, uint32_t source_len, int32_t level) {
    uLongf size = *dest_len;
    const int result = ::compress2(dest, &size, source, source_len, level);
    *dest_len = static_cast<uint32_t>(size);
    return result;
}
uint32_t z_compress_bound(uint32_t source_len) { return static_cast<uint32_t>(::compressBound(source_len)); }
int32_t z_uncompress(uint8_t* dest, be<uint32_t>* dest_len, const uint8_t* source, uint32_t source_len) {
    uLongf size = *dest_len;
    const int result = ::uncompress(dest, &size, source, source_len);
    *dest_len = static_cast<uint32_t>(size);
    return result;
}

// ------------------------------------------------------------------ coreinit
// No environment variables are set on a retail console.
int32_t ENVGetEnvironmentVariable(const char*, char* buffer, uint32_t size) {
    if (buffer && size) buffer[0] = 0;
    return -1;
}

// MEMAllocator {functions, heap, param1, param2} for the default heap: its two functions go through the
// title's replaceable MEMAllocFromDefaultHeapEx / MEMFreeToDefaultHeap pointers, as the console's do.
uint32_t allocator_default_alloc(PPCContext& ctx, GuestAddress, uint32_t size) { return default_heap_alloc(ctx, size, 4); }
void allocator_default_free(PPCContext& ctx, GuestAddress, uint32_t block) { default_heap_free(ctx, block); }
void thunk_allocator_alloc(PPCContext& ctx, uint8_t*) { abi::invoke<allocator_default_alloc>(ctx); }
void thunk_allocator_free(PPCContext& ctx, uint8_t*) { abi::invoke<allocator_default_free>(ctx); }
void MEMInitAllocatorForDefaultHeap(be<uint32_t>* allocator) {
    static uint32_t functions = 0;
    if (functions == 0) {
        functions = system_alloc(8, 4);
        guest<be<uint32_t>>(functions)[0] = register_host_function(thunk_allocator_alloc, "allocator: default heap alloc");
        guest<be<uint32_t>>(functions)[1] = register_host_function(thunk_allocator_free, "allocator: default heap free");
    }
    allocator[0] = functions;
    allocator[1] = 0;
    allocator[2] = 0;
    allocator[3] = 0;
}

// ------------------------------------------------------------------ gx2: the profiler measures nothing
std::atomic<bool> g_said_perf{false};
void perf_no_op() { once(g_said_perf, "GX2Perf* (the GPU profiler) measures nothing"); }
int32_t perf_no_result() { return 0; }

// ------------------------------------------------------------------ sound: effects and the GamePad's virtual surround
// The runtime's mixer has no auxiliary buses, so effect callbacks (reverb, chorus, delay) are registered and never
// run: the sound plays dry. The AXFX effects therefore only need to exist.
std::atomic<bool> g_said_aux{false}, g_said_fx{false};
int32_t ax_register_aux(uint32_t, GuestAddress, GuestAddress) {
    once(g_said_aux, "AXRegisterAuxCallback: the mixer has no effect buses, sound plays without reverb/chorus/delay");
    return 0;
}
int32_t fx_mem_size() { return 0x100; }
int32_t fx_init() {
    once(g_said_fx, "AXFX effects (reverb, chorus, delay) are not computed");
    return 1;
}
int32_t fx_true() { return 1; }
int32_t ax_drc_vs_mode(be<uint32_t>* mode) {
    if (mode) *mode = 0; // virtual surround off
    return 0;
}
uint32_t g_fx_alloc = 0, g_fx_free = 0;
void fx_set_hooks(uint32_t alloc, uint32_t free) { g_fx_alloc = alloc; g_fx_free = free; }
void fx_get_hooks(be<uint32_t>* alloc, be<uint32_t>* free) {
    if (alloc) *alloc = g_fx_alloc;
    if (free) *free = g_fx_free;
}
// AXRmt*: see "Wii Remote speaker output of the mixer" further down.
int32_t rmt_samples_left() { return 40; }
int32_t rmt_get_samples(int32_t, uint32_t, int32_t samples) { return samples; }

} // namespace
} // namespace cafe::os

using namespace cafe::os;

CAFE_EXPORT(nn_fp, IsOnline__Q2_2nn2fpFv, zero);
CAFE_EXPORT(nn_fp, IsJoinable__Q2_2nn2fpFPCQ3_2nn2fp14FriendPresenceUL, zero);
CAFE_EXPORT(nn_fp, GetBlackListAccountId__Q2_2nn2fpFPA17_cPCUiUi, closed);
CAFE_EXPORT(nn_fp, GetFriendAccountId__Q2_2nn2fpFPA17_cPCUiUi, closed);
CAFE_EXPORT(nn_fp, GetFriendRequestAccountId__Q2_2nn2fpFPA17_cPCUiUi, closed);
CAFE_EXPORT(nn_ac, GetCloseStatus__Q2_2nn2acFPQ3_2nn2ac6Status, ac_close_status);
CAFE_EXPORT(nn_act, GetHostServerSettings__Q2_2nn3actFPcT1Uc, closed);

CAFE_EXPORT(nn_nfp, GetErrorCode__Q2_2nn3nfpFRCQ2_2nn6Result, zero);
CAFE_EXPORT(nn_nfp, GetNfpRomInfo__Q2_2nn3nfpFPQ3_2nn3nfp7RomInfo, no_tag);
CAFE_EXPORT(nn_nfp, MountRom__Q2_2nn3nfpFv, no_tag);
CAFE_EXPORT(nn_nfp, SetActivateEvent__Q2_2nn3nfpFP7OSEvent, zero);   // never signalled: no tag comes
CAFE_EXPORT(nn_nfp, SetDeactivateEvent__Q2_2nn3nfpFP7OSEvent, zero);

CAFE_EXPORT(nn_save, SAVEGetStatOtherApplication, fs_not_found);
CAFE_EXPORT(nn_save, SAVEOpenFileOtherApplication, fs_not_found);

CAFE_EXPORT(nsysnet, accept, minus_one);
CAFE_EXPORT(nsysnet, listen, minus_one);

CAFE_EXPORT(padscore, KPADDisableStickCrossClamp, no_op);
CAFE_EXPORT(padscore, WPADGetBatteryLevel, zero);
CAFE_EXPORT(padscore, WPADGetSpeakerVolume, zero);
CAFE_EXPORT(padscore, WPADIsSpeakerEnabled, zero);

CAFE_EXPORT(proc_ui, ProcUIIsRunning, one);
CAFE_EXPORT(sysapp, SYSLaunchSettings, no_op);
CAFE_EXPORT(coreinit, OSIsHomeButtonMenuEnabled, zero);
CAFE_EXPORT(coreinit, ENVGetEnvironmentVariable, ENVGetEnvironmentVariable);
CAFE_EXPORT(coreinit, MEMInitAllocatorForDefaultHeap, MEMInitAllocatorForDefaultHeap);

// The GamePad's motion sensor: its calibration and correction settings are accepted; the port's GamePad lies still.
CAFE_EXPORT(vpad, VPADDisableStickCrossClamp, no_op);
CAFE_EXPORT(vpad, VPADInitGyroAccReviseParam, no_op);
CAFE_EXPORT(vpad, VPADInitGyroDirReviseParam, no_op);
CAFE_EXPORT(vpad, VPADInitGyroZeroDriftMode, no_op);
CAFE_EXPORT(vpad, VPADInitGyroZeroPlayParam, no_op);
CAFE_EXPORT(vpad, VPADSetGyroAngle, no_op);
CAFE_EXPORT(vpad, VPADSetGyroDirReviseBase, no_op);
CAFE_EXPORT(vpad, VPADSetGyroDirReviseParam, no_op);
CAFE_EXPORT(vpad, VPADSetGyroDirection, no_op);
CAFE_EXPORT(vpad, VPADSetGyroDirectionMag, no_op);
CAFE_EXPORT(vpad, VPADSetGyroMagnification, no_op);
CAFE_EXPORT(vpad, VPADSetGyroZeroPlayParam, no_op);

CAFE_EXPORT(zlib125, compress2, z_compress2);
CAFE_EXPORT(zlib125, compressBound, z_compress_bound);
CAFE_EXPORT(zlib125, uncompress, z_uncompress);

CAFE_EXPORT(gx2, GX2PerfFrameEnd, perf_no_op);
CAFE_EXPORT(gx2, GX2PerfFrameStart, perf_no_op);
CAFE_EXPORT(gx2, GX2PerfFree, perf_no_op);
CAFE_EXPORT(gx2, GX2PerfGetResultByFrame, perf_no_result);
CAFE_EXPORT(gx2, GX2PerfInit, perf_no_op);
CAFE_EXPORT(gx2, GX2PerfMetricEnable, perf_no_result);
CAFE_EXPORT(gx2, GX2PerfMetricsClear, perf_no_op);
CAFE_EXPORT(gx2, GX2PerfPassEnd, perf_no_op);
CAFE_EXPORT(gx2, GX2PerfPassStart, perf_no_op);
CAFE_EXPORT(gx2, GX2PerfSetCollectionMethod, perf_no_op);
CAFE_EXPORT(gx2, GX2PerfTagEnable, perf_no_op);
CAFE_EXPORT(gx2, GX2PerfTagEnd, perf_no_op);
CAFE_EXPORT(gx2, GX2PerfTagStart, perf_no_op);

CAFE_EXPORT(gx2, GX2CheckSurfaceUseVsFormat, one); // every use/format pair the title asks about is drawable here
CAFE_EXPORT(gx2, GX2ResetGPU, no_op);

CAFE_EXPORT(snd_core, AXRegisterAuxCallback, ax_register_aux);
CAFE_EXPORT(snd_core, AXSetAuxReturnVolume, zero);
CAFE_EXPORT(snd_core, AXGetDRCVSMode, ax_drc_vs_mode);
CAFE_EXPORT(snd_core, AXSetDRCVSDownmixBalance, zero);
CAFE_EXPORT(snd_core, AXSetDRCVSLC, zero);
CAFE_EXPORT(snd_core, AXSetDRCVSSpeakerPosition, zero);
CAFE_EXPORT(snd_core, AXSetDRCVSSurroundDepth, zero);
CAFE_EXPORT(snd_core, AXSetDRCVSSurroundLevelGain, zero);
// The Wii Remote's speaker: no remote, no samples wanted.
CAFE_EXPORT(snd_core, AXRmtAdvancePtr, zero);
CAFE_EXPORT(snd_core, AXRmtGetSamples, rmt_get_samples);
CAFE_EXPORT(snd_core, AXRmtGetSamplesLeft, rmt_samples_left);
CAFE_EXPORT(snd_core, AXSetVoiceRmtOn, no_op);

CAFE_EXPORT(snd_user, AXFXSetHooks, fx_set_hooks);
CAFE_EXPORT(snd_user, AXFXGetHooks, fx_get_hooks);
CAFE_EXPORT(snd_user, AXFX2SetMemAllocFns, fx_set_hooks);
CAFE_EXPORT(snd_user, AXFX2GetMemAllocFns, fx_get_hooks);
CAFE_EXPORT(snd_user, AXFXMultiChChorusGetMemSize, fx_mem_size);
CAFE_EXPORT(snd_user, AXFXMultiChDelayGetMemSize, fx_mem_size);
CAFE_EXPORT(snd_user, AXFXMultiChReverbGetMemSize, fx_mem_size);
CAFE_EXPORT(snd_user, AXFXMultiChChorusInit, fx_init);
CAFE_EXPORT(snd_user, AXFXMultiChDelayInit, fx_init);
CAFE_EXPORT(snd_user, AXFXMultiChReverbInit, fx_init);
CAFE_EXPORT(snd_user, AXFXMultiChChorusShutdown, no_op);
CAFE_EXPORT(snd_user, AXFXMultiChDelayShutdown, no_op);
CAFE_EXPORT(snd_user, AXFXMultiChReverbShutdown, no_op);
CAFE_EXPORT(snd_user, AXFXMultiChChorusCallback, no_op);
CAFE_EXPORT(snd_user, AXFXMultiChDelayCallback, no_op);
CAFE_EXPORT(snd_user, AXFXMultiChReverbCallback, no_op);
CAFE_EXPORT(snd_user, AXFXMultiChChorusSettingsUpdateNoReset, fx_true);
CAFE_EXPORT(snd_user, AXFXMultiChDelaySettingsUpdateNoReset, fx_true);
CAFE_EXPORT(snd_user, AXFXMultiChReverbSettingsUpdateNoReset, fx_true);
CAFE_EXPORT(snd_user, AXFXChorusExpSettingsUpdate, fx_true);
CAFE_EXPORT(snd_user, AXFXDelayExpSettingsUpdate, fx_true);
CAFE_EXPORT(snd_user, AXFXReverbHiExpSettingsUpdate, fx_true);
// Per-device output settings the mixer does not have: the TV and GamePad get the plain stereo mix at full volume.
CAFE_EXPORT(snd_core, AXSetDeviceRemixMatrix, zero);
CAFE_EXPORT(snd_core, AXSetDeviceVolume, zero);
// The error viewer (the runtime prints errors and acknowledges them): settings of its look and sound.
CAFE_EXPORT(erreula, ErrEulaSetVersion__3RplFi, no_op);
CAFE_EXPORT(erreula, ErrEulaPlayAppearSE__3RplFb, no_op);
CAFE_EXPORT(erreula, ErrEulaJump__3RplFPCcUi, no_op);

// ====================================================================================================
// Second batch (Mario Kart 8, Super Mario 3D World, Mario Tennis Ultra Smash).
namespace cafe::os {
namespace {

void forward(PPCContext& ctx, const char* module, const char* name) {
    const Export* e = find_export(module, name);
    if (e == nullptr) fatal("port: %s:%s, which another function is built on, is missing", module, name);
    e->function(ctx, guest_base());
}
void fast_mutex_try_lock(PPCContext& ctx) { forward(ctx, "coreinit", "OSTryLockMutex"); }

// OSRendezvous: three words, one per core. A core that waits sets its word and stays until every core in
// the mask has set its own.
void rendezvous_init(be<uint32_t>* r) {
    if (r) r[0] = r[1] = r[2] = 0;
}
int32_t rendezvous_wait(PPCContext& ctx, GuestAddress r, uint32_t mask) {
    if (r.value == 0) return 0;
    forward(ctx, "coreinit", "OSGetCoreId");
    const uint32_t core = ctx.r[3] < 3 ? ctx.r[3] : 0;
    ctx.r[3] = r.value;
    auto* words = guest<std::atomic<uint32_t>>(r.value);
    words[core].store(__builtin_bswap32(1));
    for (;;) {
        bool all = true;
        for (uint32_t i = 0; i < 3; ++i) {
            if ((mask & (1u << i)) && words[i].load() == 0) all = false;
        }
        if (all) return 1;
        std::this_thread::yield();
    }
}

std::atomic<bool> g_said_query{false}, g_said_gamma{false};
// Occlusion queries are not run: a conditional draw is always drawn, a counted query never reports.
void query_no_op() { once(g_said_query, "GX2 occlusion queries are not run (conditional draws are always drawn)"); }
void gamma_no_op() { once(g_said_gamma, "GX2SetTVGamma/GX2SetDRCGamma: the picture keeps the default gamma"); }

// GX2Get*ShaderGPRs / StackEntries: from the shader's own SQ_PGM_RESOURCES register (first register of each kind).
uint32_t shader_resources(GuestAddress shader) { return shader.value ? uint32_t{*guest<be<uint32_t>>(shader.value)} : 0; }
uint32_t shader_gprs(GuestAddress shader) { return shader_resources(shader) & 0xFF; }
uint32_t shader_stack(GuestAddress shader) { return (shader_resources(shader) >> 8) & 0xFF; }

// GX2DepthBuffer: surface 0x74 bytes, view 0x0C, Hi-Z 0x08, then clear depth (float) at 0x88 and stencil at 0x8C.
void set_clear_depth_stencil(GuestAddress buffer, float depth, uint32_t stencil) {
    if (buffer.value == 0) return;
    uint32_t bits;
    std::memcpy(&bits, &depth, 4);
    *guest<be<uint32_t>>(buffer.value + 0x88) = bits;
    *guest<be<uint32_t>>(buffer.value + 0x8C) = stencil & 0xFF;
}

int32_t wpad_mpls_attached(uint32_t, be<uint32_t>* attached, uint32_t) {
    if (attached) *attached = 0;
    return 0;
}
uint32_t kpad_mpls_work_size() { return 0x5FE0; }

uint32_t fp_empty_list(be<uint32_t>*, be<uint32_t>* count) {
    if (count) *count = 0;
    return 0;
}
uint32_t ac_connect_result(be<uint32_t>* result) {
    if (result) *result = kClosed;
    return 0;
}
int32_t ax_get_aux_callback(uint32_t, uint32_t, uint32_t, be<uint32_t>* callback, be<uint32_t>* context) {
    if (callback) *callback = 0;
    if (context) *context = 0;
    return 0;
}
int32_t z_compress(uint8_t* dest, be<uint32_t>* dest_len, const uint8_t* source, uint32_t source_len) {
    uLongf n = *dest_len;
    const int r = ::compress(dest, &n, source, source_len);
    *dest_len = static_cast<uint32_t>(n);
    return r;
}


// The working directory: a title starts in "/" (Tennis Ultra Smash joins it with "vol/content/..."). FSChangeDir is remembered and reported by FSGetCwd;
// the file layer itself takes absolute paths only, so a title that then opens relative paths gets "not found"
// from it (said once here).
std::mutex g_cwd_mutex;
std::string g_cwd = "/";
std::atomic<bool> g_said_cwd{false};
int32_t fs_get_cwd(GuestAddress, GuestAddress, char* out, uint32_t bytes, uint32_t) {
    std::lock_guard lock(g_cwd_mutex);
    // with a trailing '/', as the console gives it (Color Splash appends "sound/..." to it directly)
    const std::string cwd = g_cwd.back() == '/' ? g_cwd : g_cwd + "/";
    if (out == nullptr || bytes < cwd.size() + 1) return -1;
    std::memcpy(out, cwd.c_str(), cwd.size() + 1);
    return 0;
}
int32_t fs_change_dir(GuestAddress, GuestAddress, const char* path, uint32_t) {
    if (path == nullptr) return -1;
    std::lock_guard lock(g_cwd_mutex);
    g_cwd = path;
    while (g_cwd.size() > 1 && g_cwd.back() == '/') g_cwd.pop_back();
    vfs::set_cwd(g_cwd); // port/patch_fs_cwd.py: relative paths are below it
    if (std::getenv("TTT2_TRACE_FS")) std::fprintf(stderr, "fs: chdir %s\n", g_cwd.c_str());
    once(g_said_cwd, "FSChangeDir: relative paths are now resolved below it");
    return 0;
}

void dc_store_range(uint32_t address, uint32_t size) { cafe::gpu::cpu_wrote(address, size); } // as DCFlushRange (patch_dcflush.py)
void get_stack_pointer(PPCContext& ctx) { ctx.r[3] = ctx.r[1]; }

// MEMHeapHeader fields after the tag, as on hardware (port/patch_heap_headers.py does it for expanded/frame heaps):
// 0x04 link, 0x0C child list {head, tail, u16 count, u16 link offset 4}, 0x18 dataStart, 0x1C dataEnd. Paper Mario
// Color Splash finds the owner of a pointer from these (its free() otherwise leaks the block and its object handles
// stay valid after delete -> null virtual call after "A" on the title).
void write_heap_header(uint32_t handle, uint32_t data_start, uint32_t data_end) {
    for (uint32_t o = 0x04; o < 0x18; o += 4) *guest<be<uint32_t>>(handle + o) = 0;
    *guest<be<uint16_t>>(handle + 0x16) = 4;
    *guest<be<uint32_t>>(handle + 0x18) = data_start;
    *guest<be<uint32_t>>(handle + 0x1C) = data_end;
}

// Block heaps (MEMInitBlockHeap ...: Super Mario Bros. The Lost Levels' Virtual Console shell, Super Mario 3D World
// imports them). First fit over a list of free ranges kept on the host side; the handle is the title's heap record.
struct BlockHeap {
    std::map<uint32_t, uint32_t> free;  // start -> size
    std::map<uint32_t, uint32_t> used;  // start -> size
};
std::mutex g_block_mutex;
std::unordered_map<uint32_t, BlockHeap> g_block_heaps;
BlockHeap& block_heap(uint32_t handle) {
    const auto it = g_block_heaps.find(handle);
    if (it == g_block_heaps.end()) fatal("port: 0x%08X is not a block heap", handle);
    return it->second;
}
uint32_t block_init(uint32_t record, uint32_t start, uint32_t end, uint32_t, uint32_t, uint32_t) {
    if (record == 0 || end <= start) return 0;
    std::lock_guard lock(g_block_mutex);
    BlockHeap heap;
    heap.free[start] = end - start;
    g_block_heaps[record] = std::move(heap);
    *guest<be<uint32_t>>(record) = 0x424C4B48; // "BLKH"
    write_heap_header(record, start, end);
    return record;
}
uint32_t block_alloc(uint32_t handle, uint32_t size, int32_t alignment) {
    std::lock_guard lock(g_block_mutex);
    BlockHeap& heap = block_heap(handle);
    if (size == 0) size = 1;
    const bool from_end = alignment < 0;
    uint32_t a = static_cast<uint32_t>(from_end ? -alignment : alignment);
    if (a < 4) a = 4;
    size = (size + 3) & ~3u;
    const auto take = [&](std::map<uint32_t, uint32_t>::iterator it, uint32_t at) {
        const uint32_t start = it->first, length = it->second;
        heap.free.erase(it);
        if (at > start) heap.free[start] = at - start;
        if (at + size < start + length) heap.free[at + size] = start + length - (at + size);
        heap.used[at] = size;
        return at;
    };
    if (!from_end) {
        for (auto it = heap.free.begin(); it != heap.free.end(); ++it) {
            const uint32_t at = (it->first + a - 1) & ~(a - 1);
            if (at >= it->first && at + size <= it->first + it->second) return take(it, at);
        }
    } else {
        for (auto it = heap.free.end(); it != heap.free.begin();) {
            --it;
            if (it->second < size) continue;
            const uint32_t at = (it->first + it->second - size) & ~(a - 1);
            if (at >= it->first) return take(it, at);
        }
    }
    return 0;
}
void block_free(uint32_t handle, uint32_t address) {
    if (address == 0) return;
    std::lock_guard lock(g_block_mutex);
    BlockHeap& heap = block_heap(handle);
    const auto it = heap.used.find(address);
    if (it == heap.used.end()) fatal("port: MEMFreeToBlockHeap: 0x%08X was not allocated from heap 0x%08X", address, handle);
    uint32_t start = it->first, size = it->second;
    heap.used.erase(it);
    auto next = heap.free.lower_bound(start);
    if (next != heap.free.end() && start + size == next->first) {
        size += next->second;
        next = heap.free.erase(next);
    }
    if (next != heap.free.begin()) {
        auto prev = std::prev(next);
        if (prev->first + prev->second == start) {
            prev->second += size;
            return;
        }
    }
    heap.free[start] = size;
}
uint32_t block_destroy(uint32_t handle) {
    std::lock_guard lock(g_block_mutex);
    g_block_heaps.erase(handle);
    return handle;
}
uint32_t block_total_free(uint32_t handle) {
    std::lock_guard lock(g_block_mutex);
    uint32_t total = 0;
    for (const auto& [start, size] : block_heap(handle).free) total += size;
    return total;
}
uint32_t block_largest_free(uint32_t handle, int32_t) {
    std::lock_guard lock(g_block_mutex);
    uint32_t best = 0;
    for (const auto& [start, size] : block_heap(handle).free) best = std::max(best, size);
    return best;
}
// OSDynLoad_GetLoaderHeapStatistics (Super Mario Maker prints it at start): nothing is loaded at run time here, so the
// loader's heaps are reported as unused with room to spare.
uint32_t loader_heap_statistics(uint32_t stats) {
    if (stats == 0) return 0xBAD10001u;
    const uint32_t values[6] = {0, 0, 8u << 20, 8u << 20, 0, 0}; // code used, -, code free, code largest free, data used, -
    for (int i = 0; i < 6; ++i) *guest<be<uint32_t>>(stats + i * 4) = values[i];
    return 0;
}
// OSSetExceptionCallback(Ex): the title's own handler for CPU exceptions (crash screens). The runtime stops with its
// own report on a guest fault and never calls it; said once. Returns "no previous handler".
uint32_t set_exception_callback(uint32_t, uint32_t, uint32_t) {
    static std::atomic<bool> said{false};
    once(said, "OSSetExceptionCallback: the title's exception handler is kept but never called");
    return 0;
}
// GX2GetLastFrame(target, texture): the picture shown last, as a texture (Super Mario Maker asks at start). The
// runtime's scan buffer description is used (as GX2GetCurrentScanBuffer gives it); like there, the displayed frame is
// not written back to guest memory, so the texture's contents are not the real picture. Said once.
void get_last_frame(PPCContext& ctx) {
    static std::atomic<bool> said{false};
    once(said, "GX2GetLastFrame: describes the scan buffer; its pixels are not the shown picture");
    const uint32_t texture = ctx.r[4];
    if (texture == 0) return;
    forward(ctx, "gx2", "GX2GetCurrentScanBuffer"); // fills the surface part (a colour buffer and a texture begin alike)
    const uint32_t view[5] = {0, 1, 0, 1, 0x00010203};  // first mip, mips, first slice, slices, component map
    for (int i = 0; i < 5; ++i) *guest<be<uint32_t>>(texture + 0x74 + i * 4) = view[i];
    ctx.r[3] = texture;
    forward(ctx, "gx2", "GX2InitTextureRegs");
}
// GX2PatchDisplayList(list, type, byte offset, shader) (port/os_extra.cpp, 22 Nov evening): points the "set shader" commands a display list holds at that
// offset to another shader's program (Super Mario Maker). As decaf: only the program address is patched, word 2 of
// the SET_CONTEXT_REG packet at the offset (SQ_PGM_START_*, address >> 8; the runtime's GX2Set...Shader writes the same
// layout). Only the shader's program pointer is read: Maker passes a pointer arranged so that just that field is right
// (its other words are stack contents). Types as decaf's GX2PatchShaderType: 1 fetch, 2 vertex, 3 vertex before
// geometry, 4 geometry, 5 pixel. Program pointer (or the GX2R buffer when it is 0) at the struct offsets of gx2/types.h.
void patch_display_list(PPCContext& ctx) {
    const uint32_t list = ctx.r[3], type = ctx.r[4], offset = ctx.r[5], shader = ctx.r[6];
    const auto word = [](uint32_t a) { return static_cast<uint32_t>(*guest<be<uint32_t>>(a)); };
    uint32_t data_off = 0, gx2r_off = 0;
    switch (type) {
    case 1: data_off = 0x0C; break;                    // GX2FetchShader.data
    case 2: data_off = 0xD4; gx2r_off = 0x130; break;  // GX2VertexShader.data / gx2rData.buffer
    case 5: data_off = 0xA8; gx2r_off = 0xE4; break;   // GX2PixelShader.data / gx2rData.buffer
    case 3: data_off = 0x58; gx2r_off = 0xBC; break;   // GX2GeometryShader.vertexShaderData / gx2rVertexShaderData
    case 4: data_off = 0x50; gx2r_off = 0xAC; break;   // GX2GeometryShader.data / gx2rData
    default: fatal("port: GX2PatchDisplayList: shader type %u", type);
    }
    uint32_t address = shader ? word(shader + data_off) : 0;
    if (address == 0 && shader && gx2r_off) address = word(shader + gx2r_off);
    static std::atomic<int> shown{0};
    if (std::getenv("PORT_TRACE_PATCH") && shown.fetch_add(1) < 12) {
        std::fprintf(stderr, "port: GX2PatchDisplayList(list 0x%08X, type %u, offset 0x%X): program 0x%08X, packet %08X %08X %08X\n",
                     list, type, offset, address, word(list + offset), word(list + offset + 4), word(list + offset + 8));
    }
    if (list == 0 || address == 0) fatal("port: GX2PatchDisplayList: type %u, list 0x%08X, program 0x%08X", type, list, address);
    *guest<be<uint32_t>>(list + offset + 8) = address >> 8;
}
// GX2CopyDisplayList(list, bytes): the list's commands are put into the current command buffer; the runtime's
// GX2CallDisplayList has the same effect on what is drawn.
void copy_display_list(PPCContext& ctx) { forward(ctx, "gx2", "GX2CallDisplayList"); }
uint32_t block_tracking_left(uint32_t) { return 0x10000; } // the host-side lists do not run out
uint32_t block_add_tracking(uint32_t, uint32_t, uint32_t) { return 0; }

// Unit heaps (blocks of one size). The records live on the host side; the handle is the heap's start address.
struct UnitHeap {
    std::vector<uint32_t> free;
    uint32_t block = 0;
};
std::mutex g_unit_mutex;
std::unordered_map<uint32_t, UnitHeap> g_unit_heaps;
constexpr uint32_t kUnitHeader = 0x40;
uint32_t unit_align(uint32_t v, uint32_t a) { return (v + a - 1) & ~(a - 1); }
uint32_t unit_create(GuestAddress start, uint32_t size, uint32_t block, int32_t alignment, uint32_t) {
    const uint32_t a = alignment < 4 ? 4 : static_cast<uint32_t>(alignment);
    const uint32_t first = unit_align(start.value + kUnitHeader, a);
    const uint32_t step = unit_align(block, a);
    if (start.value == 0 || step == 0 || first + step > start.value + size) return 0;
    UnitHeap heap;
    heap.block = step;
    for (uint32_t at = first; at + step <= start.value + size; at += step) heap.free.push_back(at);
    std::reverse(heap.free.begin(), heap.free.end()); // lowest address handed out first
    *guest<be<uint32_t>>(start.value) = 0x554E5448; // "UNTH"
    write_heap_header(start.value, first, start.value + size);
    std::lock_guard lock(g_unit_mutex);
    g_unit_heaps[start.value] = std::move(heap);
    return start.value;
}
uint32_t unit_alloc(uint32_t handle) {
    std::lock_guard lock(g_unit_mutex);
    const auto it = g_unit_heaps.find(handle);
    if (it == g_unit_heaps.end()) fatal("port: 0x%08X is not a unit heap", handle);
    if (it->second.free.empty()) return 0;
    const uint32_t block = it->second.free.back();
    it->second.free.pop_back();
    return block;
}
void unit_free(uint32_t handle, uint32_t block) {
    if (block == 0) return;
    std::lock_guard lock(g_unit_mutex);
    const auto it = g_unit_heaps.find(handle);
    if (it == g_unit_heaps.end()) fatal("port: 0x%08X is not a unit heap", handle);
    it->second.free.push_back(block);
}
uint32_t unit_destroy(uint32_t handle) {
    std::lock_guard lock(g_unit_mutex);
    g_unit_heaps.erase(handle);
    return handle;
}
uint32_t unit_count_free(uint32_t handle) {
    std::lock_guard lock(g_unit_mutex);
    const auto it = g_unit_heaps.find(handle);
    return it == g_unit_heaps.end() ? 0 : static_cast<uint32_t>(it->second.free.size());
}
uint32_t unit_calc_size(uint32_t block, uint32_t count, int32_t alignment) {
    const uint32_t a = alignment < 4 ? 4 : static_cast<uint32_t>(alignment);
    return kUnitHeader + a + unit_align(block, a) * count;
}

// MP task queues (coreinit's multi-core job lists), after the layout in the wut headers: MPTaskQueue 0x50 bytes
// (+0x04 state, +0x08 tasks, +0x0C ready, +0x10 running, +0x18 finished, +0x24 queue index, +0x30 queue size,
// +0x38 task pointer array, +0x3C its capacity), MPTask 0x2C bytes (+0x04 queue, +0x08 state, +0x0C function,
// +0x10/+0x14 its two arguments, +0x18 result, +0x1C core, +0x20 duration). One host lock stands in for the
// queue's spin lock. Durations are not measured (left 0).
enum : uint32_t { kMpTaskInit = 1, kMpTaskReady = 2, kMpTaskRunning = 4, kMpTaskFinished = 8 };
enum : uint32_t { kMpQInit = 1, kMpQReady = 2, kMpQStopping = 4, kMpQStopped = 8, kMpQFinished = 16 };
std::mutex g_mp_mutex;
be<uint32_t>& mpw(uint32_t object, uint32_t offset) { return *guest<be<uint32_t>>(object + offset); }
void mp_init_task(GuestAddress task, uint32_t function, uint32_t arg1, uint32_t arg2) {
    std::memset(guest<uint8_t>(task.value), 0, 0x2C);
    mpw(task.value, 0x00) = task.value;
    mpw(task.value, 0x08) = kMpTaskInit;
    mpw(task.value, 0x0C) = function;
    mpw(task.value, 0x10) = arg1;
    mpw(task.value, 0x14) = arg2;
    mpw(task.value, 0x1C) = 3; // no core yet
}
void mp_init_queue(GuestAddress q, uint32_t tasks, uint32_t capacity) {
    std::memset(guest<uint8_t>(q.value), 0, 0x50);
    mpw(q.value, 0x00) = q.value;
    mpw(q.value, 0x04) = kMpQInit;
    mpw(q.value, 0x38) = tasks;
    mpw(q.value, 0x3C) = capacity;
}
uint32_t mp_term_queue(GuestAddress q) {
    std::lock_guard lock(g_mp_mutex);
    mpw(q.value, 0x04) = kMpQFinished;
    return 1;
}
uint32_t mp_queue_info(GuestAddress q, be<uint32_t>* info) {
    std::lock_guard lock(g_mp_mutex);
    info[0] = mpw(q.value, 0x04);
    info[1] = mpw(q.value, 0x08);
    info[2] = mpw(q.value, 0x0C);
    info[3] = mpw(q.value, 0x10);
    info[4] = mpw(q.value, 0x18);
    return 1;
}
uint32_t mp_start_queue(GuestAddress q) {
    std::lock_guard lock(g_mp_mutex);
    const uint32_t state = mpw(q.value, 0x04);
    if (state != kMpQInit && state != kMpQStopped) return 0;
    mpw(q.value, 0x04) = kMpQReady;
    return 1;
}
uint32_t mp_stop_queue(GuestAddress q) {
    std::lock_guard lock(g_mp_mutex);
    if (mpw(q.value, 0x04) != kMpQReady) return 0;
    mpw(q.value, 0x04) = mpw(q.value, 0x10) == 0 ? kMpQStopped : kMpQStopping;
    return 1;
}
uint32_t mp_reset_queue(GuestAddress q) {
    std::lock_guard lock(g_mp_mutex);
    const uint32_t state = mpw(q.value, 0x04);
    if (state != kMpQFinished && state != kMpQStopped) return 0;
    const uint32_t size = mpw(q.value, 0x30), array = mpw(q.value, 0x38);
    mpw(q.value, 0x04) = kMpQInit;
    mpw(q.value, 0x08) = size;
    mpw(q.value, 0x0C) = size;
    mpw(q.value, 0x10) = 0;
    mpw(q.value, 0x18) = 0;
    mpw(q.value, 0x24) = 0;
    for (uint32_t i = 0; i < size; ++i) {
        const uint32_t task = mpw(array, i * 4);
        mpw(task, 0x08) = kMpTaskReady;
        mpw(task, 0x18) = 0;
    }
    return 1;
}
uint32_t mp_run_tasks(PPCContext& ctx, GuestAddress q, uint32_t count) {
    // Takes up to `count` tasks at a time and keeps going while the queue is ready and holds tasks (as decaf's
    // coreinit does): Tennis Ultra Smash's workers call this once per wake-up and expect the queue drained.
    forward(ctx, "coreinit", "OSGetCoreId");
    const uint32_t core = ctx.r[3];
    bool all_ok = true;
    std::vector<uint32_t> batch;
    for (;;) {
        batch.clear();
        {
            std::lock_guard lock(g_mp_mutex);
            if (mpw(q.value, 0x04) != kMpQReady) break;
            const uint32_t index = mpw(q.value, 0x24), size = mpw(q.value, 0x30);
            const uint32_t take = std::min(count, size > index ? size - index : 0);
            if (take == 0) break;
            for (uint32_t i = 0; i < take; ++i) {
                const uint32_t task = mpw(mpw(q.value, 0x38), (index + i) * 4);
                mpw(task, 0x08) = kMpTaskRunning;
                mpw(task, 0x1C) = core;
                batch.push_back(task);
            }
            mpw(q.value, 0x24) = index + take;
            mpw(q.value, 0x0C) = mpw(q.value, 0x0C) - take;
            mpw(q.value, 0x10) = mpw(q.value, 0x10) + take;
        }
        for (uint32_t task : batch) {
            const uint32_t result = call_guest(ctx, mpw(task, 0x0C), {mpw(task, 0x10), mpw(task, 0x14)});
            std::lock_guard lock(g_mp_mutex);
            mpw(task, 0x18) = result;
            mpw(task, 0x08) = kMpTaskFinished;
            mpw(q.value, 0x10) = mpw(q.value, 0x10) - 1;
            mpw(q.value, 0x18) = mpw(q.value, 0x18) + 1;
            if (mpw(q.value, 0x04) == kMpQStopping && mpw(q.value, 0x10) == 0) mpw(q.value, 0x04) = kMpQStopped;
            if (mpw(q.value, 0x08) == mpw(q.value, 0x18)) mpw(q.value, 0x04) = kMpQFinished;
        }
    }
    return all_ok;
}

// mvplayer.rpl is a module of Mario Kart 8 itself (its movie player, for Mario Kart TV clips); the port translates
// only the main program so far, so there is no player. The title writes settings straight into the object Create
// returns, so Create hands out one zeroed block (64 KB, the real size is not known) that nothing reads: clips do
// not play. If the title calls through a function pointer in it, that is a null call and the run stops there.
std::atomic<bool> g_said_mv{false};
uint32_t g_mv_object = 0;
uint32_t mv_create() {
    once(g_said_mv, "mvplayer (Mario Kart 8's own movie module) is not translated: a blank player object, clips do not play");
    if (g_mv_object == 0) {
        g_mv_object = system_alloc(0x10000, 64);
        std::memset(guest<uint8_t>(g_mv_object), 0, 0x10000);
    }
    return g_mv_object;
}

// OSVReport(format, va_list): the text is printed as written, its arguments are not filled in.
void os_vreport(const char* format) {
    if (format) std::fprintf(stderr, "[guest, arguments not filled in] %s%s", format,
                             std::strchr(format, 10) ? "" : "\n");
}

// nn::act "Ex" forms for an account slot: the port has one account, so they answer as the plain forms do.
uint32_t act_simple_address_ex(PPCContext& ctx, GuestAddress out, uint32_t) {
    forward(ctx, "nn_act", "GetSimpleAddressId__Q2_2nn3actFv");
    if (out.value) *guest<be<uint32_t>>(out.value) = ctx.r[3];
    return 0;
}
void act_persistent_id_ex(PPCContext& ctx) { forward(ctx, "nn_act", "GetPersistentId__Q2_2nn3actFv"); }
// The temp volume: plenty of room, nothing to remove (TEMPCreateAndInitTempDir gives fresh directories).
uint64_t temp_free_space() { return uint64_t{4} << 30; }
std::atomic<bool> g_said_account{false};
void launch_account() { once(g_said_account, "SYSLaunchAccount: the console's account settings do not exist here"); }

CAFE_EXPORT(coreinit, OSFastMutex_TryLock, fast_mutex_try_lock);
CAFE_EXPORT(coreinit, OSGetStackPointer, get_stack_pointer);
CAFE_EXPORT(coreinit, OSVReport, os_vreport);
#ifndef CAFE_PORT_MODULES // a build with the translated module (port/modules.cpp) binds these to it instead
CAFE_EXPORT(mvplayer, Create__8MVPlayerSFv, mv_create);
CAFE_EXPORT(mvplayer, Destroy__8MVPlayerSFP8MVPlayer, no_op);
CAFE_EXPORT(mvplayer, Shutdown__8MVPlayerSFv, no_op);
CAFE_EXPORT(mvplayer, Draw__6MVViewFv, no_op);
#endif
CAFE_EXPORT(coreinit, MPInitTask, mp_init_task);
CAFE_EXPORT(coreinit, MPInitTaskQ, mp_init_queue);
CAFE_EXPORT(coreinit, MPTermTaskQ, mp_term_queue);
CAFE_EXPORT(coreinit, MPGetTaskQInfo, mp_queue_info);
CAFE_EXPORT(coreinit, MPStartTaskQ, mp_start_queue);
CAFE_EXPORT(coreinit, MPStopTaskQ, mp_stop_queue);
CAFE_EXPORT(coreinit, MPResetTaskQ, mp_reset_queue);
CAFE_EXPORT(coreinit, MPRunTasksFromTaskQ, mp_run_tasks);
CAFE_EXPORT(coreinit, OSDynLoad_GetLoaderHeapStatistics, loader_heap_statistics);
CAFE_EXPORT(coreinit, OSSetExceptionCallbackEx, set_exception_callback);
CAFE_EXPORT(coreinit, OSSetExceptionCallback, set_exception_callback);
CAFE_EXPORT(gx2, GX2GetLastFrame, get_last_frame);
CAFE_EXPORT(gx2, GX2PatchDisplayList, patch_display_list);
CAFE_EXPORT(gx2, GX2CopyDisplayList, copy_display_list);
CAFE_EXPORT(coreinit, MEMInitBlockHeap, block_init);
CAFE_EXPORT(coreinit, MEMAllocFromBlockHeapEx, block_alloc);
CAFE_EXPORT(coreinit, MEMFreeToBlockHeap, block_free);
CAFE_EXPORT(coreinit, MEMDestroyBlockHeap, block_destroy);
CAFE_EXPORT(coreinit, MEMGetTotalFreeSizeForBlockHeap, block_total_free);
CAFE_EXPORT(coreinit, MEMGetAllocatableSizeForBlockHeapEx, block_largest_free);
CAFE_EXPORT(coreinit, MEMGetTrackingLeftInBlockHeap, block_tracking_left);
CAFE_EXPORT(coreinit, MEMAddBlockHeapTracking, block_add_tracking);
CAFE_EXPORT(coreinit, MEMCreateUnitHeapEx, unit_create);
CAFE_EXPORT(coreinit, MEMAllocFromUnitHeap, unit_alloc);
CAFE_EXPORT(coreinit, MEMFreeToUnitHeap, unit_free);
CAFE_EXPORT(coreinit, MEMDestroyUnitHeap, unit_destroy);
CAFE_EXPORT(coreinit, MEMCountFreeBlockForUnitHeap, unit_count_free);
CAFE_EXPORT(coreinit, MEMCalcHeapSizeForUnitHeap, unit_calc_size);
// No Wii Remote: nothing to read. No amiibo settings applet. No peer to receive from.
// KPADRead: input.cpp (port/patch_wiimote.py)
CAFE_EXPORT(nn_nfp, InitializeAmiiboSettingsArgsIn__Q2_2nn3nfpFPQ3_2nn3nfp20AmiiboSettingsArgsIn, no_tag);
CAFE_EXPORT(nn_nfp, SwitchToAmiiboSettings__Q2_2nn3nfpFRCQ3_2nn3nfp20AmiiboSettingsArgsIn, no_tag);
CAFE_EXPORT(nsysnet, recvfrom_ex, minus_one);
CAFE_EXPORT(coreinit, FSGetCwd, fs_get_cwd);
CAFE_EXPORT(coreinit, FSChangeDir, fs_change_dir);
CAFE_EXPORT(nn_act, GetSimpleAddressIdEx__Q2_2nn3actFPUiUc, act_simple_address_ex);
CAFE_EXPORT(nn_act, GetPersistentIdEx__Q2_2nn3actFUc, act_persistent_id_ex);
CAFE_EXPORT(nn_temp, TEMPGetFreeSpaceSize, temp_free_space);
CAFE_EXPORT(nn_temp, TEMPRemove, zero);
CAFE_EXPORT(sysapp, SYSLaunchAccount, launch_account);
CAFE_EXPORT(coreinit, OSInitRendezvous, rendezvous_init);
CAFE_EXPORT(coreinit, OSWaitRendezvous, rendezvous_wait);
CAFE_EXPORT(coreinit, LCHardwareIsAvailable, zero); // no locked cache: titles then use ordinary memory
CAFE_EXPORT(coreinit, OSIsAddressRangeDCValid, one);
CAFE_EXPORT(coreinit, OSIsEnabledOverlayArena, zero);
CAFE_EXPORT(coreinit, IMIsAPDEnabledBySysSettings, zero); // auto power-down is off
CAFE_EXPORT(coreinit, OSEnableForegroundExit, no_op);
CAFE_EXPORT(coreinit, DCStoreRange, dc_store_range);
CAFE_EXPORT(proc_ui, ProcUIInShutdown, zero);

CAFE_EXPORT(gx2, GX2GetVertexShaderGPRs, shader_gprs);
CAFE_EXPORT(gx2, GX2GetVertexShaderStackEntries, shader_stack);
CAFE_EXPORT(gx2, GX2GetGeometryShaderGPRs, shader_gprs);
CAFE_EXPORT(gx2, GX2GetGeometryShaderStackEntries, shader_stack);
CAFE_EXPORT(gx2, GX2GetPixelShaderGPRs, shader_gprs);
CAFE_EXPORT(gx2, GX2GetPixelShaderStackEntries, shader_stack);
CAFE_EXPORT(gx2, GX2SetClearDepthStencil, set_clear_depth_stencil);
CAFE_EXPORT(gx2, GX2SetTVGamma, gamma_no_op);
CAFE_EXPORT(gx2, GX2SetDRCGamma, gamma_no_op);
CAFE_EXPORT(gx2, GX2QueryBegin, query_no_op);
CAFE_EXPORT(gx2, GX2QueryEnd, query_no_op);
CAFE_EXPORT(gx2, GX2QueryBeginConditionalRender, query_no_op);
CAFE_EXPORT(gx2, GX2QueryEndConditionalRender, query_no_op);

// Wii MotionPlus: no Wii Remote, so none attached.
// Super Mario Maker's batch (19 Nov): MotionPlus / gyro corrections of controllers that are not there, settings with
// nothing behind them here. IMGetTimeBeforeAPD: auto power-down is off, an hour is always left.
uint32_t maker_time_before_apd(uint32_t seconds) { if (seconds) *guest<be<uint32_t>>(seconds) = 3600; return 0; }
CAFE_EXPORT(padscore, KPADDisableMplsDirRevise, no_op);
CAFE_EXPORT(padscore, KPADDisableMplsDpdRevise, no_op);
CAFE_EXPORT(padscore, KPADEnableMplsDirRevise, no_op);
CAFE_EXPORT(padscore, KPADEnableMplsDpdRevise, no_op);
CAFE_EXPORT(padscore, KPADGetMplsZeroDriftMode, zero);
CAFE_EXPORT(padscore, KPADSetMplsDirReviseBase, no_op);
CAFE_EXPORT(padscore, KPADSetMplsDirReviseParam, no_op);
CAFE_EXPORT(padscore, KPADSetMplsDirection, no_op);
CAFE_EXPORT(padscore, KPADSetMplsDpdReviseParam, no_op);
CAFE_EXPORT(padscore, KPADSetMplsZeroDriftMode, no_op);
CAFE_EXPORT(padscore, WPADEnableWiiRemote, no_op);
CAFE_EXPORT(vpad, VPADDisableGyroDirRevise, no_op);
CAFE_EXPORT(vpad, VPADEnableGyroDirRevise, no_op);
CAFE_EXPORT(vpad, VPADGetGyroZeroDriftMode, zero);
CAFE_EXPORT(vpad, VPADSetGyroZeroDriftMode, no_op);
CAFE_EXPORT(coreinit, IMGetTimeBeforeAPD, maker_time_before_apd);
CAFE_EXPORT(coreinit, LCGetDMAQueueLength, zero);
CAFE_EXPORT(coreinit, OSGetMainCoreId, one);
CAFE_EXPORT(snd_core, AXRegisterExceedCallback, zero);
CAFE_EXPORT(gx2, GX2SetAAMode, no_op);          // the renderer takes the sample count from each surface
CAFE_EXPORT(gx2, GX2SetHiStencilInfo, no_op);   // hierarchical stencil is an optimisation of the console's GPU
// KPADDisableMpls: input.cpp (port/patch_wiimote_mpls.py)
// KPADEnableMpls: input.cpp (port/patch_wiimote_mpls.py)
CAFE_EXPORT(padscore, KPADGetMplsWorkSize, kpad_mpls_work_size);
CAFE_EXPORT(padscore, KPADSetMplsWorkarea, no_op);
// WPADIsMplsAttached: input.cpp (port/patch_wiimote_mpls.py)
CAFE_EXPORT(vpad, VPADSetStickOrigin, no_op);
CAFE_EXPORT(vpad, VPADSetGyroAccReviseParam, no_op);
CAFE_EXPORT(vpadbase, VPADBASEGetHeadphoneStatus, zero);

// Offline: no connection, no friends, no network account.
CAFE_EXPORT(nn_ac, Connect__Q2_2nn2acFv, closed);
CAFE_EXPORT(nn_ac, GetConnectResult__Q2_2nn2acFPQ2_2nn6Result, ac_connect_result);
CAFE_EXPORT(nn_act, IsNetworkAccountEx__Q2_2nn3actFUc, zero);
CAFE_EXPORT(nn_fp, GetFriendListAll__Q2_2nn2fpFPUiT1UiT3, fp_empty_list);
CAFE_EXPORT(nn_fp, GetFriendRequestList__Q2_2nn2fpFPUiT1UiT3, fp_empty_list);
CAFE_EXPORT(nn_fp, GetFriendProfile__Q2_2nn2fpFPQ3_2nn2fp7ProfilePCUiUi, closed);
CAFE_EXPORT(nn_fp, GetMyAccountId__Q2_2nn2fpFPc, closed);
CAFE_EXPORT(nn_fp, GetMyPreference__Q2_2nn2fpFPQ3_2nn2fp10Preference, closed);
CAFE_EXPORT(nn_fp, GetMyPresence__Q2_2nn2fpFPQ3_2nn2fp10MyPresence, closed);
CAFE_EXPORT(nn_fp, GetMyProfile__Q2_2nn2fpFPQ3_2nn2fp7Profile, closed);
CAFE_EXPORT(nn_fp, IsFriendRequestAllowed__Q2_2nn2fpFv, zero);
CAFE_EXPORT(nn_fp, UpdateGameModeDescription__Q2_2nn2fpFPCw, closed);

// Sound settings the mixer does not have (profiling, compressor, upsampler choice, GamePad virtual surround,
// Wii Remote filters): accepted.
CAFE_EXPORT(snd_core, AXUserBegin, zero);
CAFE_EXPORT(snd_core, AXUserEnd, zero);
CAFE_EXPORT(snd_core, AXUserIsProtected, zero);
CAFE_EXPORT(snd_core, AXInitProfile, zero);
CAFE_EXPORT(snd_core, AXGetSwapProfile, zero);
CAFE_EXPORT(snd_core, AXSetDefaultMixerSelect, zero);
CAFE_EXPORT(snd_core, AXSetVoiceMixerSelect, zero);
CAFE_EXPORT(snd_core, AXSetDeviceCompressor, zero);
CAFE_EXPORT(snd_core, AXSetDeviceLinearUpsampler, zero);
CAFE_EXPORT(snd_core, AXSetDeviceUpsampleStage, zero);
CAFE_EXPORT(snd_core, AXGetDeviceUpsampleStage, zero);
CAFE_EXPORT(snd_core, AXSetDRCVSOutputGain, zero);
CAFE_EXPORT(snd_core, AXSetMaxVoices, zero);
CAFE_EXPORT(snd_core, AXSetMode, no_op);
CAFE_EXPORT(snd_core, AXSetPpcLoadLimit, zero);
CAFE_EXPORT(snd_core, AXSetVoiceRmtIIR, no_op);
CAFE_EXPORT(snd_core, AXSetVoiceRmtIIRCoefs, no_op);
CAFE_EXPORT(snd_core, DRCVS_Process, zero);
CAFE_EXPORT(snd_core, DRCVS_SetOutputMode, zero);
CAFE_EXPORT(snd_core, AXGetAuxCallback, ax_get_aux_callback);

// AXDecodeAdpcmData(data, adpcm state, samples, out): DSP-ADPCM to PCM16 (Super Mario Maker, entering the editor).
// data starts at a frame (8 bytes: predictor/scale header, 14 nibbles); the state's predictor/scale and history
// are updated as the voice's would be.
struct AdpcmState {
    be<int16_t> coefs[16];
    be<uint16_t> gain;
    be<uint16_t> pred_scale;
    be<int16_t> yn1;
    be<int16_t> yn2;
};
void ax_decode_adpcm_data(const uint8_t* data, AdpcmState* state, uint32_t samples, be<int16_t>* out) {
    if (data == nullptr || state == nullptr || out == nullptr) return;
    int32_t yn1 = static_cast<int16_t>(state->yn1), yn2 = static_cast<int16_t>(state->yn2);
    uint32_t ps = state->pred_scale;
    for (uint32_t i = 0; i < samples; ++i) {
        const uint32_t frame = i / 14, pos = i % 14;
        if (pos == 0) ps = data[frame * 8];
        const uint8_t byte = data[frame * 8 + 1 + pos / 2];
        int32_t nibble = (pos & 1) ? (byte & 0xF) : (byte >> 4);
        if (nibble >= 8) nibble -= 16;
        const int32_t c1 = static_cast<int16_t>(state->coefs[((ps >> 4) & 7) * 2]);
        const int32_t c2 = static_cast<int16_t>(state->coefs[((ps >> 4) & 7) * 2 + 1]);
        int32_t v = ((nibble * (1 << (ps & 0xF))) * 2048 + 1024 + c1 * yn1 + c2 * yn2) >> 11;
        v = std::clamp(v, -32768, 32767);
        out[i] = static_cast<int16_t>(v);
        yn2 = yn1;
        yn1 = v;
    }
    state->pred_scale = static_cast<uint16_t>(ps);
    state->yn1 = static_cast<int16_t>(yn1);
    state->yn2 = static_cast<int16_t>(yn2);
}
CAFE_EXPORT(snd_core, AXDecodeAdpcmData, ax_decode_adpcm_data);

// ------------------------------------------------------------------ Mario & Sonic Sochi 2014 (and others): offline stubs
// Motion Plus / gyro calibration settings and the like: accepted, no effect.
CAFE_EXPORT(padscore, WPADSetAutoSleepTime, no_op);
CAFE_EXPORT(padscore, KPADDisableMplsAccRevise, no_op);
CAFE_EXPORT(padscore, KPADDisableMplsZeroPlay, no_op);
CAFE_EXPORT(padscore, KPADEnableAimingMode, no_op);
CAFE_EXPORT(padscore, KPADEnableMplsAccRevise, no_op);
CAFE_EXPORT(padscore, KPADEnableMplsZeroPlay, no_op);
// KPADGetMplsStatus: input.cpp (port/patch_wiimote_mpls.py)
CAFE_EXPORT(padscore, KPADIsEnableMplsAccRevise, zero);
CAFE_EXPORT(padscore, KPADIsEnableMplsDirRevise, zero);
CAFE_EXPORT(padscore, KPADIsEnableMplsDpdRevise, zero);
CAFE_EXPORT(padscore, KPADIsEnableMplsZeroDrift, zero);
CAFE_EXPORT(padscore, KPADIsEnableMplsZeroPlay, zero);
// KPADResetMpls: input.cpp (port/patch_wiimote_mpls.py)
CAFE_EXPORT(padscore, KPADSetMplsAccReviseParam, no_op);
CAFE_EXPORT(padscore, KPADSetMplsAngle, no_op);
CAFE_EXPORT(padscore, KPADSetMplsZeroPlayParam, no_op);
CAFE_EXPORT(padscore, KPADStartMplsCalibration, zero);
CAFE_EXPORT(padscore, KPADStopMplsCalibration, no_op);
// KPADWorkMplsCalibration: input.cpp (port/patch_wiimote_mpls.py)
CAFE_EXPORT(vpad, VPADDisableGyroAccRevise, no_op);
CAFE_EXPORT(vpad, VPADDisableGyroZeroPlay, no_op);
CAFE_EXPORT(vpad, VPADEnableGyroAccRevise, no_op);
CAFE_EXPORT(vpad, VPADEnableGyroZeroPlay, no_op);
CAFE_EXPORT(vpad, VPADIsEnableGyroAccRevise, zero);
CAFE_EXPORT(vpad, VPADIsEnableGyroDirRevise, zero);
CAFE_EXPORT(vpad, VPADIsEnableGyroZeroDrift, zero);
CAFE_EXPORT(vpad, VPADIsEnableGyroZeroPlay, zero);
// The reverb effect of the expanded standard set: the mixer has no effect buses (as AXRegisterAuxCallback above).
CAFE_EXPORT(snd_core, AXPrepareEfxData, zero);
// Threads: no cancellation points, never suspended by anyone else.
CAFE_EXPORT(coreinit, OSCancelThread, no_op);
CAFE_EXPORT(coreinit, OSTestThreadCancel, no_op);
// OSIsThreadSuspended: the thread's suspend count (OSThread +0x328, os/kernel.h kSuspend) above zero. Sochi 2014's
// font cache waits for its worker to suspend itself (a constant 0 made it spin forever).
int32_t os_is_thread_suspended(uint32_t thread) {
    if (thread == 0) return 0;
    return static_cast<int32_t>(*reinterpret_cast<be<int32_t>*>(guest_pointer(thread + 0x328))) > 0 ? 1 : 0;
}
CAFE_EXPORT(coreinit, OSIsThreadSuspended, os_is_thread_suspended);
CAFE_EXPORT(coreinit, OSReleaseForeground, no_op);
CAFE_EXPORT(sysapp, SYSRelaunchTitle, no_op);
CAFE_EXPORT(coreinit, FSCancelCommand, no_op);
CAFE_EXPORT(coreinit, FSGetErrorCodeForViewer, zero);
void dc_store_range_no_sync(uint32_t address, uint32_t size) { gpu::cpu_wrote(address, size); }
CAFE_EXPORT(coreinit, DCStoreRangeNoSync, dc_store_range_no_sync);
// FSSetUserData / FSGetUserData: a word the title keeps with a command block.
std::mutex g_fs_user_mutex;
std::unordered_map<uint32_t, uint32_t> g_fs_user;
void fs_set_user_data(uint32_t block, uint32_t data) {
    std::lock_guard lock(g_fs_user_mutex);
    g_fs_user[block] = data;
}
uint32_t fs_get_user_data(uint32_t block) {
    std::lock_guard lock(g_fs_user_mutex);
    const auto it = g_fs_user.find(block);
    return it == g_fs_user.end() ? 0 : it->second;
}
CAFE_EXPORT(coreinit, FSSetUserData, fs_set_user_data);
CAFE_EXPORT(coreinit, FSGetUserData, fs_get_user_data);
// Accounts / friends / Mii wrapping: offline.
CAFE_EXPORT(nn_acp, ACPMiiWrap, zero);
CAFE_EXPORT(nn_acp, ACPMiiUnwrap, zero);
CAFE_EXPORT(nn_act, GetTransferableId__Q2_2nn3actFUi, zero);
int32_t act_utc_offset(be<int64_t>* offset, uint8_t* sign) {
    if (offset) *offset = 0;
    if (sign) *sign = 0;
    return 0;
}
CAFE_EXPORT(nn_act, GetUtcOffsetEx__Q2_2nn3actFPLUc, act_utc_offset);
CAFE_EXPORT(nn_fp, AddFriendAsync__Q2_2nn2fpFPCcPFQ2_2nn6ResultPv_vPv, closed);
CAFE_EXPORT(nn_fp, AddFriendAsync__Q2_2nn2fpFUiPFQ2_2nn6ResultPv_vPv, closed);
CAFE_EXPORT(gx2, GX2PerfGetNumPasses, one);
// OSGetSystemMessageQueue: the queue the system posts HOME-button / foreground messages to. Nothing is ever posted
// (no system around the title); an empty queue laid out as os/sync.cpp's OSInitMessageQueue does.
uint32_t os_get_system_message_queue() {
    static const uint32_t queue = [] {
        const uint32_t q = system_alloc(0x3C + 16 * 16, 16);
        std::memset(guest_pointer(q), 0, 0x3C + 16 * 16);
        *reinterpret_cast<be<uint32_t>*>(guest_pointer(q)) = 0x6D536751u; // 'mSgQ'
        *reinterpret_cast<be<uint32_t>*>(guest_pointer(q + 0x2C)) = q + 0x3C; // message array
        *reinterpret_cast<be<uint32_t>*>(guest_pointer(q + 0x30)) = 16u;      // capacity
        return q;
    }();
    return queue;
}
CAFE_EXPORT(coreinit, OSGetSystemMessageQueue, os_get_system_message_queue);

// ------------------------------------------------------------------ Paper Mario Color Splash: offline stubs
CAFE_EXPORT(coreinit, OSDynLoad_AddNotifyCallback, zero); // modules never load or unload behind the title's back
CAFE_EXPORT(coreinit, OSDynLoad_GetNumberOfRPLs, zero);
CAFE_EXPORT(padscore, WPADDisableBluetooth, no_op);
CAFE_EXPORT(sysapp, SYSSwitchToBrowserForViewer, no_op);
CAFE_EXPORT(gx2, GX2SetDefaultAllocator, no_op); // GX2's own allocations come from the runtime
int32_t im_get_apd_period(be<uint32_t>* period) {
    if (period) *period = 0; // auto power-down off
    return 0;
}
CAFE_EXPORT(coreinit, IMGetAPDPeriod, im_get_apd_period);
std::mutex g_atomic64_mutex;
uint64_t os_swap_atomic64(be<uint64_t>* value, uint64_t swap) {
    std::lock_guard lock(g_atomic64_mutex);
    const uint64_t old = *value;
    *value = swap;
    return old;
}
CAFE_EXPORT(coreinit, OSSwapAtomic64, os_swap_atomic64);

// ------------------------------------------------------------------ lzma920 (LZMA SDK 9.20 decoder API) over liblzma
// The guest keeps a CLzmaDec / CLzma2Dec (32-bit): prop lc/lp/pb/dicSize at 0-15, probs 16, dic 20, buf 24, range 28,
// code 32, dicPos 36, dicBufSize 40. The decoding state lives in a liblzma raw decoder per guest struct; the guest
// fields read here are dic, dicPos (and dicBufSize), and dicPos is written back.
struct XzStream {
    const uint8_t* next_in; size_t avail_in; uint64_t total_in;
    uint8_t* next_out; size_t avail_out; uint64_t total_out;
    const void* allocator; void* internal;
    void* reserved_ptr[4]; uint64_t seek_pos, reserved_int2; size_t reserved_int3, reserved_int4; int reserved_enum[2];
};
struct XzLzmaOptions {
    uint32_t dict_size; const uint8_t* preset_dict; uint32_t preset_dict_size; uint32_t lc, lp, pb;
    int mode; uint32_t nice_len; int mf; uint32_t depth; uint32_t ext_flags, ext_size_low, ext_size_high;
    uint32_t reserved_int[5]; int reserved_enum[4]; void* reserved_ptr[2];
};
struct XzFilter { uint64_t id; void* options; };
struct Xz {
    int (*raw_decoder)(XzStream*, const XzFilter*) = nullptr;
    int (*code)(XzStream*, int) = nullptr;
    void (*end)(XzStream*) = nullptr;
};
const Xz& xz() {
    static const Xz x = [] {
        Xz r;
#ifdef _WIN32
        HMODULE m = LoadLibraryA("liblzma-5.dll");
        const auto sym = [&](const char* n) { return m ? reinterpret_cast<void*>(GetProcAddress(m, n)) : nullptr; };
#else
        void* m = dlopen("liblzma.so.5", RTLD_NOW);
        const auto sym = [&](const char* n) { return m ? dlsym(m, n) : nullptr; };
#endif
        r.raw_decoder = reinterpret_cast<int (*)(XzStream*, const XzFilter*)>(sym("lzma_raw_decoder"));
        r.code = reinterpret_cast<int (*)(XzStream*, int)>(sym("lzma_code"));
        r.end = reinterpret_cast<void (*)(XzStream*)>(sym("lzma_end"));
        std::fprintf(stderr, "port: lzma920 over liblzma: %s\n", r.code ? "loaded" : "liblzma NOT found");
        return r;
    }();
    return x;
}
struct LzmaState {
    bool lzma2 = false;
    XzLzmaOptions options{};
    XzStream stream{};
    bool open = false;
};
std::mutex g_lzma_mutex;
std::unordered_map<uint32_t, LzmaState> g_lzma;
void lzma_restart(LzmaState& s) {
    if (s.open && xz().end) xz().end(&s.stream);
    s.stream = XzStream{};
    XzFilter filters[2] = {{s.lzma2 ? 0x21ull : 0x4000000000000001ull, &s.options}, {UINT64_MAX, nullptr}};
    s.open = xz().raw_decoder && xz().raw_decoder(&s.stream, filters) == 0;
}
int32_t lzma_alloc_probs(uint32_t p, const uint8_t* props, uint32_t size, uint32_t) {
    if (size < 5 || props == nullptr) return 4; // SZ_ERROR_UNSUPPORTED
    std::lock_guard lock(g_lzma_mutex);
    LzmaState& s = g_lzma[p];
    s.lzma2 = false;
    uint32_t d = props[0];
    s.options = XzLzmaOptions{};
    s.options.lc = d % 9; d /= 9;
    s.options.lp = d % 5;
    s.options.pb = d / 5;
    s.options.dict_size = std::max<uint32_t>(4096, props[1] | (props[2] << 8) | (props[3] << 16) | (uint32_t{props[4]} << 24));
    lzma_restart(s);
    return s.open ? 0 : 2; // SZ_ERROR_MEM
}
int32_t lzma2_alloc_probs(uint32_t p, uint32_t prop, uint32_t) {
    if ((prop & 0xFF) > 40) return 4;
    std::lock_guard lock(g_lzma_mutex);
    LzmaState& s = g_lzma[p];
    s.lzma2 = true;
    s.options = XzLzmaOptions{};
    const uint32_t b = prop & 0xFF;
    s.options.dict_size = b == 40 ? 0xFFFFFFFFu : (2u | (b & 1)) << (b / 2 + 11);
    s.options.lc = 3;
    s.options.pb = 2;
    lzma_restart(s);
    return s.open ? 0 : 2;
}
void lzma_init(uint32_t p) {
    std::lock_guard lock(g_lzma_mutex);
    if (auto it = g_lzma.find(p); it != g_lzma.end()) lzma_restart(it->second);
}
void lzma_free_probs(uint32_t p, uint32_t) {
    std::lock_guard lock(g_lzma_mutex);
    if (auto it = g_lzma.find(p); it != g_lzma.end()) {
        if (it->second.open && xz().end) xz().end(&it->second.stream);
        g_lzma.erase(it);
    }
}
int32_t lzma_decode_to_dic(uint32_t p, uint32_t dic_limit, const uint8_t* src, be<uint32_t>* src_len, uint32_t finish,
                           be<uint32_t>* status) {
    std::lock_guard lock(g_lzma_mutex);
    const auto it = g_lzma.find(p);
    const uint32_t in = src_len ? static_cast<uint32_t>(*src_len) : 0;
    if (it == g_lzma.end() || !it->second.open || xz().code == nullptr) {
        if (src_len) *src_len = 0;
        return 1; // SZ_ERROR_DATA
    }
    LzmaState& s = it->second;
    const uint32_t dic = *reinterpret_cast<be<uint32_t>*>(guest_pointer(p + 20));
    const uint32_t pos = *reinterpret_cast<be<uint32_t>*>(guest_pointer(p + 36));
    s.stream.next_in = src;
    s.stream.avail_in = in;
    s.stream.next_out = guest_pointer(dic + pos);
    s.stream.avail_out = dic_limit > pos ? dic_limit - pos : 0;
    const int r = xz().code(&s.stream, 0);
    const uint32_t produced = static_cast<uint32_t>((dic_limit > pos ? dic_limit - pos : 0) - s.stream.avail_out);
    *reinterpret_cast<be<uint32_t>*>(guest_pointer(p + 36)) = pos + produced;
    if (src_len) *src_len = in - static_cast<uint32_t>(s.stream.avail_in);
    uint32_t st = 2; // LZMA_STATUS_NOT_FINISHED
    if (r == 1) st = 1; // finished with mark
    else if (s.stream.avail_out != 0 && s.stream.avail_in == 0) st = 3; // needs more input
    (void)finish;
    if (status) *status = st;
    return (r == 0 || r == 1 || r == 10) ? 0 : 1;
}
CAFE_EXPORT(lzma920, LzmaDec_AllocateProbs, lzma_alloc_probs);
CAFE_EXPORT(lzma920, LzmaDec_Init, lzma_init);
CAFE_EXPORT(lzma920, LzmaDec_FreeProbs, lzma_free_probs);
CAFE_EXPORT(lzma920, LzmaDec_DecodeToDic, lzma_decode_to_dic);
CAFE_EXPORT(lzma920, Lzma2Dec_AllocateProbs, lzma2_alloc_probs);
CAFE_EXPORT(lzma920, Lzma2Dec_Init, lzma_init);
CAFE_EXPORT(lzma920, Lzma2Dec_DecodeToDic, lzma_decode_to_dic);

CAFE_EXPORT(zlib125, compress, z_compress);


// ---------------------------------------------------------------- Paper Mario Color Splash (23 Nov)
int32_t fs_rewind_dir(uint32_t, uint32_t, uint32_t, uint32_t) { return 0; }
void gx2_no_op_cs() {}
// GX2QueryGetOcclusionResult(query, u64* result): no occlusion queries run; report everything as visible.
uint32_t gx2_query_occlusion(uint32_t, be<uint32_t>* result) {
    if (result) { result[0] = 0; result[1] = 0x00100000; }
    return 1;
}
int32_t ax_voice_protected(uint32_t) { return 0; }
// nn::boss (SpotPass): no network; Initialize and settings succeed, tasks are never registered.
int32_t boss_ok() { return 0; }
int32_t boss_task_result(uint32_t, be<uint32_t>* out) {
    if (out) *out = 0;
    return 0;
}
// h264 (H264DEC*): the decoder library as titles drive it (decaf-emu's h264 for the layouts). No video decoder is
// built in yet, so every decoded frame is BLACK: the stream's SPS gives the picture size, Execute fills the title's
// NV12 frame buffer (pitch = width rounded up to 256) with black and calls the title's output callback with one
// H264DecodeResult (status 100) per call, as the console does. Titles that only knew "decoder missing" crashed in
// their own error path (Paper Mario Color Splash after "A" on the title: opening movie). CAFE_H264=0: old behaviour
// (every call fails).
// Real pictures where the system has FFmpeg's libavcodec (Batocera does; loaded at run time, nothing linked): the
// stream is decoded and converted to NV12. Without it (or CAFE_H264_DECODE=0) frames stay black.
struct H264State {
    uint32_t output_fn = 0, user_memory = 0, output_per_frame = 0;
    uint32_t stream = 0, stream_length = 0;
    double timestamp = 0;
    uint32_t width = 0, height = 0;
    uint32_t result = 0, output = 0, results = 0; // guest structs for the callback
    void* codec = nullptr; // AVCodecContext*
    void* frame = nullptr; // AVFrame*
    void* packet = nullptr; // AVPacket*
    bool codec_failed = false;
    std::vector<uint8_t> input;
    std::vector<double> pending; // timestamps of sent pictures not yet output (output order = rising time)
};
struct AvCodecApi {
    bool ok = false;
    void* (*find_decoder)(int) = nullptr;
    void* (*alloc_context3)(const void*) = nullptr;
    int (*open2)(void*, const void*, void**) = nullptr;
    int (*send_packet)(void*, const void*) = nullptr;
    int (*receive_frame)(void*, void*) = nullptr;
    void (*flush_buffers)(void*) = nullptr;
    void (*free_context)(void**) = nullptr;
    void* (*packet_alloc)() = nullptr;
    void* (*frame_alloc)() = nullptr;
    void (*frame_free)(void**) = nullptr;
    void (*packet_free)(void**) = nullptr;
};
AvCodecApi& avcodec_api() {
    static AvCodecApi api = [] {
        AvCodecApi a;
        const char* v = std::getenv("CAFE_H264_DECODE");
        if (v != nullptr && std::strcmp(v, "0") == 0) return a;
        // libavcodec majors with their libavutil: 61/59 (FFmpeg 7), 60/58 (6), 59/57 (5), 58/56 (4)
        const int pairs[4][2] = {{61, 59}, {60, 58}, {59, 57}, {58, 56}};
        for (const auto& p : pairs) {
#ifdef _WIN32
            char codec_name[32], util_name[32];
            std::snprintf(codec_name, sizeof codec_name, "avcodec-%d.dll", p[0]);
            std::snprintf(util_name, sizeof util_name, "avutil-%d.dll", p[1]);
            HMODULE codec = LoadLibraryA(codec_name);
            HMODULE util = codec ? LoadLibraryA(util_name) : nullptr;
            const auto sym = [](HMODULE m, const char* n) { return reinterpret_cast<void*>(GetProcAddress(m, n)); };
#else
            char codec_name[32], util_name[32];
            std::snprintf(codec_name, sizeof codec_name, "libavcodec.so.%d", p[0]);
            std::snprintf(util_name, sizeof util_name, "libavutil.so.%d", p[1]);
            void* codec = dlopen(codec_name, RTLD_NOW | RTLD_LOCAL);
            void* util = codec ? dlopen(util_name, RTLD_NOW | RTLD_LOCAL) : nullptr;
            const auto sym = [](void* m, const char* n) { return dlsym(m, n); };
#endif
            if (codec == nullptr || util == nullptr) continue;
            a.find_decoder = reinterpret_cast<void* (*)(int)>(sym(codec, "avcodec_find_decoder"));
            a.alloc_context3 = reinterpret_cast<void* (*)(const void*)>(sym(codec, "avcodec_alloc_context3"));
            a.open2 = reinterpret_cast<int (*)(void*, const void*, void**)>(sym(codec, "avcodec_open2"));
            a.send_packet = reinterpret_cast<int (*)(void*, const void*)>(sym(codec, "avcodec_send_packet"));
            a.receive_frame = reinterpret_cast<int (*)(void*, void*)>(sym(codec, "avcodec_receive_frame"));
            a.flush_buffers = reinterpret_cast<void (*)(void*)>(sym(codec, "avcodec_flush_buffers"));
            a.free_context = reinterpret_cast<void (*)(void**)>(sym(codec, "avcodec_free_context"));
            a.packet_alloc = reinterpret_cast<void* (*)()>(sym(codec, "av_packet_alloc"));
            a.packet_free = reinterpret_cast<void (*)(void**)>(sym(codec, "av_packet_free"));
            a.frame_alloc = reinterpret_cast<void* (*)()>(sym(util, "av_frame_alloc"));
            a.frame_free = reinterpret_cast<void (*)(void**)>(sym(util, "av_frame_free"));
            a.ok = a.find_decoder && a.alloc_context3 && a.open2 && a.send_packet && a.receive_frame && a.flush_buffers &&
                   a.free_context && a.packet_alloc && a.packet_free && a.frame_alloc && a.frame_free;
            if (a.ok) {
                std::fprintf(stderr, "port: h264: decoding with %s\n", codec_name);
                return a;
            }
        }
        std::fprintf(stderr, "port: h264: no libavcodec found: movie frames are black (sound plays)\n");
        return a;
    }();
    return api;
}
void h264_free_codec(struct H264State& s) {
    AvCodecApi& av = avcodec_api();
    if (s.codec) av.free_context(&s.codec);
    if (s.frame) av.frame_free(&s.frame);
    if (s.packet) av.packet_free(&s.packet);
    s.codec = s.frame = s.packet = nullptr;
}
bool h264_open_codec(struct H264State& s) {
    AvCodecApi& av = avcodec_api();
    if (!av.ok || s.codec_failed) return false;
    if (s.codec) return true;
    const void* decoder = av.find_decoder(27); // AV_CODEC_ID_H264
    s.codec = decoder ? av.alloc_context3(decoder) : nullptr;
    if (s.codec == nullptr || av.open2(s.codec, decoder, nullptr) < 0) {
        std::fprintf(stderr, "port: h264: libavcodec could not open its H.264 decoder: black frames\n");
        h264_free_codec(s);
        s.codec_failed = true;
        return false;
    }
    s.frame = av.frame_alloc();
    s.packet = av.packet_alloc();
    return s.frame && s.packet;
}
// AVFrame fields used (same offsets in FFmpeg 4-7): data[8] at 0, linesize[8] at 64, width 104, height 108, format 116.
void h264_frame_to_nv12(const uint8_t* f, uint8_t* out, uint32_t pitch, uint32_t& width, uint32_t& height) {
    const uint8_t* const* data = reinterpret_cast<const uint8_t* const*>(f);
    const int* linesize = reinterpret_cast<const int*>(f + 64);
    const int w = *reinterpret_cast<const int*>(f + 104), h = *reinterpret_cast<const int*>(f + 108);
    const int format = *reinterpret_cast<const int*>(f + 116);
    width = static_cast<uint32_t>(w);
    height = static_cast<uint32_t>(h);
    pitch = (width + 255) & ~255u;
    for (int y = 0; y < h; ++y) std::memcpy(out + static_cast<size_t>(y) * pitch, data[0] + static_cast<ptrdiff_t>(y) * linesize[0], w);
    uint8_t* uv = out + static_cast<size_t>(pitch) * h;
    if (format == 23) { // NV12
        for (int y = 0; y < h / 2; ++y) std::memcpy(uv + static_cast<size_t>(y) * pitch, data[1] + static_cast<ptrdiff_t>(y) * linesize[1], w);
    } else if (format == 0 || format == 12) { // YUV420P / YUVJ420P
        for (int y = 0; y < h / 2; ++y) {
            const uint8_t* u = data[1] + static_cast<ptrdiff_t>(y) * linesize[1];
            const uint8_t* v = data[2] + static_cast<ptrdiff_t>(y) * linesize[2];
            uint8_t* row = uv + static_cast<size_t>(y) * pitch;
            for (int x = 0; x < w / 2; ++x) {
                row[2 * x] = u[x];
                row[2 * x + 1] = v[x];
            }
        }
    } else {
        std::memset(uv, 128, static_cast<size_t>(pitch) * (h / 2));
        static std::atomic<bool> said{false};
        if (!said.exchange(true)) std::fprintf(stderr, "port: h264: decoder gives pixel format %d: colours left out\n", format);
    }
}
std::mutex g_h264_mutex;
std::unordered_map<uint32_t, H264State> g_h264;
uint32_t g_h264_max_width = 1280, g_h264_max_height = 720;

bool h264_enabled() {
    static const bool on = [] {
        const char* v = std::getenv("CAFE_H264");
        return v == nullptr || std::strcmp(v, "0") != 0;
    }();
    return on;
}
void h264_said(const char* what) {
    static std::atomic<bool> said{false};
    if (!said.exchange(true)) std::fprintf(stderr, "port: h264: %s\n", what);
}

// Bit reader over an RBSP (emulation-prevention bytes removed).
struct H264Bits {
    std::vector<uint8_t> data;
    size_t bit = 0;
    bool bad = false;
    uint32_t u(int n) {
        uint32_t v = 0;
        for (int i = 0; i < n; ++i) {
            if (bit >= data.size() * 8) {
                bad = true;
                return 0;
            }
            v = (v << 1) | ((data[bit >> 3] >> (7 - (bit & 7))) & 1);
            ++bit;
        }
        return v;
    }
    uint32_t ue() {
        int zeros = 0;
        while (u(1) == 0 && !bad && zeros < 32) ++zeros;
        if (bad || zeros >= 32) {
            bad = true;
            return 0;
        }
        return (1u << zeros) - 1 + u(zeros);
    }
    int32_t se() {
        const uint32_t k = ue();
        return (k & 1) ? static_cast<int32_t>((k + 1) / 2) : -static_cast<int32_t>(k / 2);
    }
};

// Picture size from the first sequence parameter set in an Annex-B stream; false if there is none.
bool h264_sps_size(const uint8_t* p, uint32_t length, uint32_t& width, uint32_t& height) {
    for (uint32_t i = 0; i + 4 < length; ++i) {
        if (!(p[i] == 0 && p[i + 1] == 0 && p[i + 2] == 1) || (p[i + 3] & 0x1F) != 7) continue;
        H264Bits b;
        uint32_t zeros = 0;
        for (uint32_t k = i + 4; k < length && b.data.size() < 512; ++k) {
            if (zeros >= 2 && p[k] == 3) {
                zeros = 0;
                continue;
            }
            if (zeros >= 2 && p[k] <= 1) break; // next start code
            zeros = p[k] == 0 ? zeros + 1 : 0;
            b.data.push_back(p[k]);
        }
        const uint32_t profile = b.u(8);
        b.u(16); // constraint flags, level
        b.ue();  // seq_parameter_set_id
        uint32_t chroma = 1;
        if (profile == 100 || profile == 110 || profile == 122 || profile == 244 || profile == 44 || profile == 83 ||
            profile == 86 || profile == 118 || profile == 128 || profile == 138 || profile == 139 || profile == 134) {
            chroma = b.ue();
            if (chroma == 3) b.u(1);
            b.ue();
            b.ue();
            b.u(1);
            if (b.u(1)) { // scaling matrices
                for (int list = 0; list < (chroma == 3 ? 12 : 8); ++list) {
                    if (!b.u(1)) continue;
                    const int size = list < 6 ? 16 : 64;
                    int last = 8, next = 8;
                    for (int j = 0; j < size; ++j) {
                        if (next != 0) next = (last + b.se() + 256) % 256;
                        last = next == 0 ? last : next;
                    }
                }
            }
        }
        b.ue(); // log2_max_frame_num_minus4
        const uint32_t poc_type = b.ue();
        if (poc_type == 0) {
            b.ue();
        } else if (poc_type == 1) {
            b.u(1);
            b.se();
            b.se();
            const uint32_t n = b.ue();
            for (uint32_t k = 0; k < n && k < 256; ++k) b.se();
        }
        b.ue();  // max_num_ref_frames
        b.u(1);  // gaps_in_frame_num_value_allowed_flag
        const uint32_t mbs_w = b.ue() + 1, map_h = b.ue() + 1;
        const uint32_t frame_mbs_only = b.u(1);
        if (!frame_mbs_only) b.u(1);
        b.u(1); // direct_8x8_inference_flag
        uint32_t crop_l = 0, crop_r = 0, crop_t = 0, crop_b = 0;
        if (b.u(1)) {
            crop_l = b.ue();
            crop_r = b.ue();
            crop_t = b.ue();
            crop_b = b.ue();
        }
        if (b.bad) return false;
        const uint32_t unit_x = chroma == 0 || chroma == 3 ? 1 : 2;
        const uint32_t unit_y = (chroma == 1 ? 2 : 1) * (2 - frame_mbs_only);
        width = mbs_w * 16 - (crop_l + crop_r) * unit_x;
        height = map_h * 16 * (2 - frame_mbs_only) - (crop_t + crop_b) * unit_y;
        return width > 0 && height > 0 && width <= 4096 && height <= 4096;
    }
    return false;
}

constexpr int32_t kH264Ok = 0, kH264Generic = 0x1000000, kH264Param = 0x1010000;

int32_t h264_memory_requirement(int32_t, int32_t, int32_t max_w, int32_t max_h, be<uint32_t>* out) {
    if (!h264_enabled()) return -1;
    if (out == nullptr || max_w < 64 || max_h < 64 || max_w > 2800 || max_h > 1408) return kH264Param;
    g_h264_max_width = static_cast<uint32_t>(max_w);
    g_h264_max_height = static_cast<uint32_t>(max_h);
    *out = 0x100000u;
    return kH264Ok;
}
int32_t h264_check_mem(uint32_t memory, uint32_t) { return !h264_enabled() ? -1 : memory ? kH264Ok : kH264Param; }
int32_t h264_init_param(int32_t size, uint32_t memory) {
    if (!h264_enabled()) return -1;
    if (memory == 0 || size <= 0) return kH264Param;
    std::lock_guard lock(g_h264_mutex);
    H264State& s = g_h264[memory];
    s = H264State{};
    s.width = g_h264_max_width;
    s.height = g_h264_max_height;
    return kH264Ok;
}
H264State* h264_state(uint32_t memory) {
    const auto it = g_h264.find(memory);
    return it == g_h264.end() ? nullptr : &it->second;
}
int32_t h264_set_param(uint32_t memory, int32_t parameter, uint32_t value) {
    if (!h264_enabled()) return -1;
    std::lock_guard lock(g_h264_mutex);
    H264State* s = h264_state(memory);
    if (s == nullptr) return kH264Param;
    if (parameter == 1) s->output_fn = value;
    else if (parameter == 0x20000002) s->output_per_frame = value ? *guest<uint8_t>(value) : 0;
    else if (parameter == 0x70000001) s->user_memory = value;
    return kH264Ok;
}
int32_t h264_set_output_fn(uint32_t memory, uint32_t fn) {
    if (!h264_enabled()) return -1;
    std::lock_guard lock(g_h264_mutex);
    H264State* s = h264_state(memory);
    if (s == nullptr) return kH264Param;
    s->output_fn = fn;
    return kH264Ok;
}
int32_t h264_set_per_frame(uint32_t memory, uint32_t value) {
    if (!h264_enabled()) return -1;
    std::lock_guard lock(g_h264_mutex);
    H264State* s = h264_state(memory);
    if (s == nullptr) return kH264Param;
    s->output_per_frame = value;
    return kH264Ok;
}
int32_t h264_set_user_memory(uint32_t memory, uint32_t value) {
    if (!h264_enabled()) return -1;
    std::lock_guard lock(g_h264_mutex);
    H264State* s = h264_state(memory);
    if (s == nullptr) return kH264Param;
    s->user_memory = value ? static_cast<uint32_t>(*guest<be<uint32_t>>(value)) : 0; // a pointer TO the value (Cemu; Color Splash passes &this)
    return kH264Ok;
}
int32_t h264_ok_if_known(uint32_t memory) {
    if (!h264_enabled()) return -1;
    std::lock_guard lock(g_h264_mutex);
    return h264_state(memory) ? kH264Ok : kH264Param;
}
int32_t h264_close(uint32_t memory) {
    if (!h264_enabled()) return -1;
    std::lock_guard lock(g_h264_mutex);
    if (H264State* s = h264_state(memory)) h264_free_codec(*s);
    g_h264.erase(memory);
    return kH264Ok;
}
void h264_set_bitstream(PPCContext& ctx) {
    const uint32_t memory = ctx.r[3], buffer = ctx.r[4], length = ctx.r[5];
    const double timestamp = ctx.f[1].ps0;
    if (!h264_enabled()) {
        ctx.r[3] = static_cast<uint32_t>(-1);
        return;
    }
    std::lock_guard lock(g_h264_mutex);
    H264State* s = h264_state(memory);
    if (s == nullptr || buffer == 0 || length < 4) {
        ctx.r[3] = static_cast<uint32_t>(kH264Param);
        return;
    }
    s->stream = buffer;
    s->stream_length = length;
    s->timestamp = timestamp;
    ctx.r[3] = kH264Ok;
}
// Fills the result structs for one output picture and calls the title's output function (outside the lock).
void h264_output(PPCContext& ctx, H264State* s, uint32_t frame, uint32_t width, uint32_t height, double timestamp) {
    uint32_t fn = 0, output = 0;
    {
        std::lock_guard lock(g_h264_mutex);
        const uint32_t pitch = (width + 255) & ~255u;
        if (s->result == 0) {
            s->result = system_alloc(0x78, 8);
            s->results = system_alloc(4, 4);
            s->output = system_alloc(0x0C, 4);
        }
        std::memset(guest<uint8_t>(s->result), 0, 0x78);
        const auto put = [](uint32_t a, uint32_t v) { *guest<be<uint32_t>>(a) = v; };
        put(s->result + 0x00, 100);
        uint64_t bits;
        std::memcpy(&bits, &timestamp, 8);
        put(s->result + 0x08, static_cast<uint32_t>(bits >> 32));
        put(s->result + 0x0C, static_cast<uint32_t>(bits));
        put(s->result + 0x10, width);
        put(s->result + 0x14, height);
        put(s->result + 0x18, pitch);
        put(s->result + 0x44, frame);
        put(s->results, s->result);
        put(s->output + 0x00, 1);
        put(s->output + 0x04, s->results);
        put(s->output + 0x08, s->user_memory);
        fn = s->output_fn;
        output = s->output;
    }
    if (fn != 0) call_guest(ctx, fn, {output});
}
void h264_execute(PPCContext& ctx) {
    const uint32_t memory = ctx.r[3], frame = ctx.r[4];
    if (!h264_enabled()) {
        ctx.r[3] = static_cast<uint32_t>(-1);
        return;
    }
    H264State* s = nullptr;
    bool decode = false;
    {
        std::lock_guard lock(g_h264_mutex);
        s = h264_state(memory);
        if (s == nullptr || frame == 0) {
            ctx.r[3] = static_cast<uint32_t>(kH264Param);
            return;
        }
        if (s->stream_length == 0) {
            ctx.r[3] = static_cast<uint32_t>(kH264Generic);
            return;
        }
        uint32_t w = 0, h = 0;
        if (h264_sps_size(guest<uint8_t>(s->stream), s->stream_length, w, h)) {
            s->width = w;
            s->height = h;
        }
        decode = h264_open_codec(*s);
        if (decode) {
            s->input.assign(guest<uint8_t>(s->stream), guest<uint8_t>(s->stream) + s->stream_length);
            s->input.resize(s->stream_length + 64, 0); // AV_INPUT_BUFFER_PADDING_SIZE
        }
        s->stream_length = 0;
    }
    if (!decode) {
        h264_said("no video decoder: movie frames are black (sound plays)");
        const uint32_t pitch = (s->width + 255) & ~255u;
        std::memset(guest<uint8_t>(frame), 16, static_cast<size_t>(pitch) * s->height);
        std::memset(guest<uint8_t>(frame + pitch * s->height), 128, static_cast<size_t>(pitch) * (s->height / 2));
        h264_output(ctx, s, frame, s->width, s->height, s->timestamp);
        ctx.r[3] = 0x80 | 100; // "100% of a frame decoded"
        return;
    }
    AvCodecApi& av = avcodec_api();
    // AVPacket: data at +24, size at +32 (FFmpeg 4-7).
    uint8_t* packet = static_cast<uint8_t*>(s->packet);
    uint8_t* data = s->input.data();
    const int size = static_cast<int>(s->input.size() - 64);
    std::memcpy(packet + 24, &data, sizeof data);
    std::memcpy(packet + 32, &size, sizeof size);
    s->pending.push_back(s->timestamp);
    std::sort(s->pending.begin(), s->pending.end());
    const int sent = av.send_packet(s->codec, s->packet);
    if (sent < 0) {
        static std::atomic<int> said{0};
        if (said.fetch_add(1) < 3) std::fprintf(stderr, "port: h264: libavcodec refused a packet (%d)\n", sent);
    }
    std::memset(packet + 24, 0, sizeof data);
    std::memset(packet + 32, 0, sizeof size);
    while (av.receive_frame(s->codec, s->frame) >= 0) {
        uint32_t w = 0, h = 0;
        h264_frame_to_nv12(static_cast<const uint8_t*>(s->frame), guest<uint8_t>(frame), 0, w, h);
        double t = s->timestamp;
        if (!s->pending.empty()) {
            t = s->pending.front();
            s->pending.erase(s->pending.begin());
        }
        h264_output(ctx, s, frame, w, h, t);
    }
    if (s->pending.size() > 64) s->pending.erase(s->pending.begin(), s->pending.begin() + 32);
    ctx.r[3] = 0x80 | 100;
}
int32_t h264_end(uint32_t memory) {
    if (!h264_enabled()) return -1;
    std::lock_guard lock(g_h264_mutex);
    H264State* s = h264_state(memory);
    if (s == nullptr) return kH264Param;
    if (s->codec) avcodec_api().flush_buffers(s->codec);
    s->pending.clear();
    return kH264Ok;
}
// H264DECGetImageSize(stream, length, offset, &width, &height)
int32_t h264_get_image_size(uint32_t stream, uint32_t length, uint32_t offset, be<uint32_t>* width, be<uint32_t>* height) {
    if (!h264_enabled()) return -1;
    if (stream == 0 || width == nullptr || height == nullptr || offset >= length) return kH264Param;
    uint32_t w = 0, h = 0;
    if (!h264_sps_size(guest<uint8_t>(stream + offset), length - offset, w, h)) return kH264Generic;
    *width = w;
    *height = h;
    return kH264Ok;
}
// ---- Mario Party 10 (23 Nov): the system functions it imports that nothing provided yet.
// MP tasks one at a time (decaf's coreinit): Enque adds a ready task, Deque takes the next one, RunTask runs it.
uint32_t mp_enque_task(GuestAddress q, GuestAddress task) {
    std::lock_guard lock(g_mp_mutex);
    const uint32_t size = mpw(q.value, 0x30), capacity = mpw(q.value, 0x3C);
    if (size >= capacity) return 0;
    mpw(mpw(q.value, 0x38), size * 4) = task.value;
    mpw(q.value, 0x30) = size + 1;
    mpw(q.value, 0x08) = mpw(q.value, 0x08) + 1;
    mpw(q.value, 0x0C) = mpw(q.value, 0x0C) + 1;
    mpw(task.value, 0x04) = q.value;
    mpw(task.value, 0x08) = kMpTaskReady;
    if (mpw(q.value, 0x04) == kMpQFinished) mpw(q.value, 0x04) = kMpQReady;
    return 1;
}
uint32_t mp_deque_task(GuestAddress q) {
    std::lock_guard lock(g_mp_mutex);
    const uint32_t index = mpw(q.value, 0x24), size = mpw(q.value, 0x30);
    if (index >= size) return 0;
    const uint32_t task = mpw(mpw(q.value, 0x38), index * 4);
    mpw(q.value, 0x24) = index + 1;
    mpw(q.value, 0x0C) = mpw(q.value, 0x0C) - 1;
    return task;
}
uint32_t mp_run_task(PPCContext& ctx, GuestAddress task) {
    forward(ctx, "coreinit", "OSGetCoreId");
    const uint32_t core = ctx.r[3];
    uint32_t q = 0;
    {
        std::lock_guard lock(g_mp_mutex);
        if (mpw(task.value, 0x08) != kMpTaskReady) return 0;
        q = mpw(task.value, 0x04);
        mpw(task.value, 0x08) = kMpTaskRunning;
        mpw(task.value, 0x1C) = core;
        if (q) mpw(q, 0x10) = mpw(q, 0x10) + 1;
    }
    const uint32_t result = call_guest(ctx, mpw(task.value, 0x0C), {mpw(task.value, 0x10), mpw(task.value, 0x14)});
    std::lock_guard lock(g_mp_mutex);
    mpw(task.value, 0x18) = result;
    mpw(task.value, 0x08) = kMpTaskFinished;
    if (q) {
        mpw(q, 0x10) = mpw(q, 0x10) - 1;
        mpw(q, 0x18) = mpw(q, 0x18) + 1;
        if (mpw(q, 0x04) == kMpQStopping && mpw(q, 0x10) == 0) mpw(q, 0x04) = kMpQStopped;
        if (mpw(q, 0x08) == mpw(q, 0x18)) mpw(q, 0x04) = kMpQFinished;
    }
    return 1;
}
// MPWaitTaskQWithTimeout(queue, state mask, OSTime timeout in r5:r6): polls until the queue's state is in the mask.
void mp_wait_queue_timeout(PPCContext& ctx) {
    const uint32_t q = ctx.r[3], mask = ctx.r[4];
    const uint64_t ticks = (uint64_t{ctx.r[5]} << 32) | ctx.r[6];
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::microseconds(ticks / 62);
    for (;;) {
        {
            std::lock_guard lock(g_mp_mutex);
            if (mpw(q, 0x04) & mask) {
                ctx.r[3] = 1;
                return;
            }
        }
        if (std::chrono::steady_clock::now() >= deadline) {
            ctx.r[3] = 0;
            return;
        }
        std::this_thread::sleep_for(std::chrono::microseconds(200));
    }
}
// Camera (the GamePad's): not present.
int32_t cam_init(uint32_t, uint32_t, be<int32_t>* error) {
    if (error) *error = -1;
    return -1;
}
int32_t cam_fail() { return -1; }
uint32_t fs_client_num() { return 1; }
int32_t im_time_before_dimming(be<uint32_t>* seconds) {
    if (seconds) *seconds = 300;
    return 0;
}
int32_t im_dim_enabled(be<uint32_t>* enabled) {
    if (enabled) *enabled = 0;
    return 0;
}
int32_t mp10_ok() { return 0; }
uint32_t mp10_true() { return 1; }
void mp10_nothing() {}
int32_t os_semaphore_count(GuestAddress semaphore) { return *guest<be<int32_t>>(semaphore.value + 0x0C); }
uint32_t os_thread_name(GuestAddress thread) { return thread.value ? static_cast<uint32_t>(*guest<be<uint32_t>>(thread.value + 0x5C0)) : 0; }
uint32_t os_is_main_core(PPCContext& ctx) {
    forward(ctx, "coreinit", "OSGetCoreId");
    return ctx.r[3] == 1 ? 1 : 0;
}
// GX2SetClearDepth / GX2SetClearStencil: the values GX2DepthBuffer keeps for its clears (+0x88 depth, +0x8C stencil).
void gx2_set_clear_depth(PPCContext& ctx) {
    if (ctx.r[3] == 0) return;
    const float depth = static_cast<float>(ctx.f[1].ps0);
    uint32_t bits;
    std::memcpy(&bits, &depth, 4);
    *guest<be<uint32_t>>(ctx.r[3] + 0x88) = bits;
}
void gx2_set_clear_stencil(uint32_t buffer, uint32_t value) {
    if (buffer) *guest<be<uint32_t>>(buffer + 0x8C) = value;
}
// h264 helpers for streams: where the first decode unit starts / how long one is (black-frame decoder above).
int32_t h264_find_start(uint32_t buffer, uint32_t length, be<uint32_t>* offset) {
    if (buffer == 0 || offset == nullptr) return kH264Param;
    const uint8_t* p = guest<uint8_t>(buffer);
    for (uint32_t i = 0; i + 3 < length; ++i) {
        if (p[i] == 0 && p[i + 1] == 0 && p[i + 2] == 1) {
            *offset = i > 0 && p[i - 1] == 0 ? i - 1 : i;
            return kH264Ok;
        }
    }
    return kH264Generic;
}
int32_t h264_decunit_length(uint32_t, uint32_t buffer, uint32_t length, uint32_t offset, be<uint32_t>* out) {
    if (buffer == 0 || out == nullptr || offset >= length) return kH264Param;
    *out = length - offset;
    return kH264Ok;
}
int32_t nfc_no_tag() { return -0x1385; }
int32_t act_device_hash(be<uint32_t>* hash) {
    if (hash) {
        hash[0] = 0x4E415449; // "NATI"
        hash[1] = 0x56450001;
    }
    return 0;
}
int32_t nfp_amiibo_settings() { return static_cast<int32_t>(0xA1B10400u); }
int32_t kpad_acc_param(uint32_t, be<uint32_t>* play, be<uint32_t>* sensitivity) {
    if (play) *play = 0;
    if (sensitivity) *sensitivity = 0x3F800000u; // 1.0
    return 0;
}
// Wii Remote speaker (port/patch_wpad_speaker.py): accepted for connected remotes, its sound is not played.
// WPADControlSpeaker answers through its callback (channel, 0) as the remote would after the command.
bool wpad_connected(PPCContext& ctx, uint32_t channel) {
    const uint32_t r3 = ctx.r[3], r4 = ctx.r[4];
    ctx.r[3] = channel;
    ctx.r[4] = 0;
    forward(ctx, "padscore", "WPADProbe");
    const bool ok = ctx.r[3] == 0;
    ctx.r[3] = r3;
    ctx.r[4] = r4;
    return ok;
}
void wpad_control_speaker(PPCContext& ctx) {
    const uint32_t channel = ctx.r[3], callback = ctx.r[5];
    static const bool trace = std::getenv("TTT2_TRACE_WIIMOTE") != nullptr;
    if (trace) std::fprintf(stderr, "wiimote: WPADControlSpeaker(%u, cmd %u, callback 0x%08X) lr 0x%08X\n", channel, ctx.r[4], callback, ctx.lr);
    if (!wpad_connected(ctx, channel)) {
        ctx.r[3] = static_cast<uint32_t>(-1);
        return;
    }
    if (callback != 0) call_guest(ctx, callback, {channel, 0});
    ctx.r[3] = 0;
}
void wpad_can_send_stream(PPCContext& ctx) { ctx.r[3] = wpad_connected(ctx, ctx.r[3]) ? 1 : 0; }
void wpad_send_stream(PPCContext& ctx) { ctx.r[3] = wpad_connected(ctx, ctx.r[3]) ? 0 : static_cast<uint32_t>(-1); }
// Wii Remote speaker output of the mixer (AXRmt*): always one 40-sample block of silence ready. Mario Party 10's
// nw::snd only drives the remote speakers (WPADControlSpeaker ...) while samples are ready, and counts a remote as a
// player only once its speaker is set up. The samples are not filled (the remote's sound is not played).
} // namespace
CAFE_EXPORT(coreinit, FSRewindDir, fs_rewind_dir);
CAFE_EXPORT(padscore, WPADControlSpeaker, wpad_control_speaker);
CAFE_EXPORT(padscore, WPADCanSendStreamData, wpad_can_send_stream);
CAFE_EXPORT(padscore, WPADSendStreamData, wpad_send_stream);
CAFE_EXPORT(coreinit, MPEnqueTask, mp_enque_task);
CAFE_EXPORT(coreinit, MPDequeTask, mp_deque_task);
CAFE_EXPORT(coreinit, MPRunTask, mp_run_task);
CAFE_EXPORT(coreinit, MPWaitTaskQWithTimeout, mp_wait_queue_timeout);
CAFE_EXPORT(camera, CAMInit, cam_init);
CAFE_EXPORT(camera, CAMExit, mp10_nothing);
CAFE_EXPORT(camera, CAMOpen, cam_fail);
CAFE_EXPORT(camera, CAMClose, cam_fail);
CAFE_EXPORT(camera, CAMGetMemReq, cam_fail);
CAFE_EXPORT(camera, CAMSubmitTargetSurface, cam_fail);
CAFE_EXPORT(coreinit, FSGetClientNum, fs_client_num);
CAFE_EXPORT(coreinit, IMGetTimeBeforeDimming, im_time_before_dimming);
CAFE_EXPORT(coreinit, IMIsDimEnabled, im_dim_enabled);
CAFE_EXPORT(coreinit, MCP_SetSysProdSettings, mp10_ok);
CAFE_EXPORT(coreinit, MEMDumpHeap, mp10_nothing);
CAFE_EXPORT(coreinit, OSGetSemaphoreCount, os_semaphore_count);
CAFE_EXPORT(coreinit, OSGetShutdownReason, mp10_ok);
CAFE_EXPORT(coreinit, OSGetThreadName, os_thread_name);
CAFE_EXPORT(coreinit, OSIsMainCore, os_is_main_core);
CAFE_EXPORT(gx2, GX2DebugCaptureStart, mp10_nothing);
CAFE_EXPORT(gx2, GX2DebugCaptureEnd, mp10_nothing);
CAFE_EXPORT(gx2, GX2DebugCaptureFrames, mp10_nothing);
CAFE_EXPORT(gx2, GX2GetMiscParam, mp10_ok);
CAFE_EXPORT(gx2, GX2SetMiscParam, mp10_true);
CAFE_EXPORT(gx2, GX2GetPerfMetricType, mp10_ok);
CAFE_EXPORT(gx2, GX2PerfGetResultByTagId, mp10_ok);
CAFE_EXPORT(gx2, GX2PerfTagEnableAll, mp10_nothing);
CAFE_EXPORT(gx2, GX2RGetDebugOptions, mp10_ok);
CAFE_EXPORT(gx2, GX2RSetDebugOptions, mp10_nothing);
CAFE_EXPORT(gx2, GX2SetDebugMode, mp10_nothing);
CAFE_EXPORT(gx2, GX2TempDumpResources, mp10_nothing);
CAFE_EXPORT(gx2, GX2TempGetResourceCount, mp10_ok);
CAFE_EXPORT(gx2, GX2SetClearDepth, gx2_set_clear_depth);
CAFE_EXPORT(gx2, GX2SetClearStencil, gx2_set_clear_stencil);
CAFE_EXPORT(h264, H264DECFindDecstartpoint, h264_find_start);
CAFE_EXPORT(h264, H264DECCheckDecunitLength, h264_decunit_length);
CAFE_EXPORT(nfc, NFCGetTagInfo, nfc_no_tag);
CAFE_EXPORT(nn_act, GetDeviceHash__Q2_2nn3actFPUL, act_device_hash);
CAFE_EXPORT(nn_nfp, GetAmiiboSettingsResult__Q2_2nn3nfpFPQ3_2nn3nfp20AmiiboSettingsResultRC15SysArgDataBlock, nfp_amiibo_settings);
CAFE_EXPORT(nn_nfp, SwitchToAmiiboSettings__Q2_2nn3nfpFRCQ3_2nn3nfp20AmiiboSettingsArgsInPCcUi, nfp_amiibo_settings);
CAFE_EXPORT(padscore, KPADGetAccParam, kpad_acc_param);
CAFE_EXPORT(proc_ui, ProcUISetBucketStorage, mp10_nothing);
CAFE_EXPORT(vpad, VPADSetSensorBar, mp10_nothing);
CAFE_EXPORT(h264, H264DECMemoryRequirement, h264_memory_requirement);
CAFE_EXPORT(h264, H264DECCheckMemSegmentation, h264_check_mem);
CAFE_EXPORT(h264, H264DECInitParam, h264_init_param);
CAFE_EXPORT(h264, H264DECSetParam, h264_set_param);
CAFE_EXPORT(h264, H264DECSetParam_FPTR_OUTPUT, h264_set_output_fn);
CAFE_EXPORT(h264, H264DECSetParam_OUTPUT_PER_FRAME, h264_set_per_frame);
CAFE_EXPORT(h264, H264DECSetParam_USER_MEMORY, h264_set_user_memory);
CAFE_EXPORT(h264, H264DECOpen, h264_ok_if_known);
CAFE_EXPORT(h264, H264DECBegin, h264_ok_if_known);
CAFE_EXPORT(h264, H264DECSetBitstream, h264_set_bitstream);
CAFE_EXPORT(h264, H264DECExecute, h264_execute);
CAFE_EXPORT(h264, H264DECFlush, h264_end);
CAFE_EXPORT(h264, H264DECEnd, h264_end);
CAFE_EXPORT(h264, H264DECClose, h264_close);
CAFE_EXPORT(h264, H264DECGetImageSize, h264_get_image_size);
CAFE_EXPORT(gx2, GX2InitHiStencilInfoRegs, gx2_no_op_cs);
CAFE_EXPORT(gx2, GX2QueryGetOcclusionResult, gx2_query_occlusion);
CAFE_EXPORT(snd_core, AXSetVoiceVeDelta, gx2_no_op_cs);
CAFE_EXPORT(snd_core, AXVoiceIsProtected, ax_voice_protected);
CAFE_EXPORT(snd_user, AXFXReverbStdExpSettingsUpdate, fx_true);
CAFE_EXPORT(nn_boss, Initialize__Q2_2nn4bossFv, boss_ok);
CAFE_EXPORT(nn_boss, Finalize__Q2_2nn4bossFv, boss_ok);
CAFE_EXPORT(nn_boss, __ct__Q3_2nn4boss17PlayReportSettingFv, boss_ok);
CAFE_EXPORT(nn_boss, __dt__Q3_2nn4boss17PlayReportSettingFv, boss_ok);
CAFE_EXPORT(nn_boss, Initialize__Q3_2nn4boss17PlayReportSettingFPvUi, boss_ok);
CAFE_EXPORT(nn_boss, Set__Q3_2nn4boss17PlayReportSettingFPCcUi, boss_ok);
CAFE_EXPORT(nn_boss, __ct__Q3_2nn4boss4TaskFv, boss_ok);
CAFE_EXPORT(nn_boss, __dt__Q3_2nn4boss4TaskFv, boss_ok);
CAFE_EXPORT(nn_boss, Initialize__Q3_2nn4boss4TaskFPCc, boss_ok);
CAFE_EXPORT(nn_boss, IsRegistered__Q3_2nn4boss4TaskCFv, boss_ok);
CAFE_EXPORT(nn_boss, Register__Q3_2nn4boss4TaskFRQ3_2nn4boss11TaskSetting, boss_ok);
CAFE_EXPORT(nn_boss, Unregister__Q3_2nn4boss4TaskFv, boss_ok);
CAFE_EXPORT(nn_boss, StartScheduling__Q3_2nn4boss4TaskFb, boss_ok);
CAFE_EXPORT(nn_boss, GetTurnState__Q3_2nn4boss4TaskCFPUi, boss_task_result);
CAFE_EXPORT(nn_boss, GetResult__Q3_2nn4boss4TaskCFPUi, boss_task_result);
CAFE_EXPORT(nn_boss, GetHttpStatusCode__Q3_2nn4boss4TaskCFPUi, boss_task_result);
CAFE_EXPORT(nn_boss, GetContentLength__Q3_2nn4boss4TaskCFPUi, boss_task_result);
CAFE_EXPORT(nn_boss, GetProcessedLength__Q3_2nn4boss4TaskCFPUi, boss_task_result);
} // namespace cafe::os
