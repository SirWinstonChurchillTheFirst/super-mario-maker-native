// System functions the runtime (written for Tekken Tag 2 and Smash) lacks and other titles call.
// Each answers as a console would in the situation the port is in: offline, no amiibo, no Wii Remotes,
// GamePad lying still. Where something real is left out, a line says so once.

#include "cafe/export.h"
#include "cafe/guest.h"
#include "cafe/runtime.h"
#include "cafe/sysmem.h"
#include "os/kernel.h"
#include "gpu/gpu.h"

#include <map>
#include <zlib.h>

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <algorithm>
#include <unordered_map>
#include <vector>
#include <thread>

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
CAFE_EXPORT(snd_core, AXRmtGetSamples, zero);
CAFE_EXPORT(snd_core, AXRmtGetSamplesLeft, zero);
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
CAFE_EXPORT(snd_user, AXFXReverbStdExpSettingsUpdate, fx_true);
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
    if (out == nullptr || bytes < g_cwd.size() + 1) return -1;
    std::memcpy(out, g_cwd.c_str(), g_cwd.size() + 1);
    return 0;
}
int32_t fs_change_dir(GuestAddress, GuestAddress, const char* path, uint32_t) {
    if (path == nullptr) return -1;
    std::lock_guard lock(g_cwd_mutex);
    g_cwd = path;
    while (g_cwd.size() > 1 && g_cwd.back() == '/') g_cwd.pop_back();
    once(g_said_cwd, "FSChangeDir: remembered for FSGetCwd; relative paths are not resolved by the file layer");
    return 0;
}

void dc_store_range(uint32_t address, uint32_t size) { cafe::gpu::cpu_wrote(address, size); } // as DCFlushRange (patch_dcflush.py)
void get_stack_pointer(PPCContext& ctx) { ctx.r[3] = ctx.r[1]; }

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
CAFE_EXPORT(padscore, KPADRead, zero);
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
CAFE_EXPORT(padscore, KPADDisableMpls, no_op);
CAFE_EXPORT(padscore, KPADEnableMpls, no_op);
CAFE_EXPORT(padscore, KPADGetMplsWorkSize, kpad_mpls_work_size);
CAFE_EXPORT(padscore, KPADSetMplsWorkarea, no_op);
CAFE_EXPORT(padscore, WPADIsMplsAttached, wpad_mpls_attached);
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

CAFE_EXPORT(zlib125, compress, z_compress);

} // namespace
} // namespace cafe::os
