#!/usr/bin/env python3
"""patch_more_os.py SMASH4_DIR : system functions Mario Kart 8, 3D World and Tennis Ultra Smash call that need the
runtime's own data (sound voices, frame heaps), and the newer library names sndcore2/snduser2 answered by snd_core/snd_user."""
import sys
root = sys.argv[1]


def edit(path, pairs):
    p = root + '/' + path
    s = open(p, encoding='utf-8').read()
    for old, new in pairs:
        if new in s:
            continue
        if old not in s:
            sys.exit('patch_more_os: text not found in %s: %r' % (path, old[:60]))
        s = s.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(s)


AX_NEW = r'''
// ---- added for Mario Kart 8 / 3D World / Tennis Ultra Smash (port/patch_more_os.py)
// The "Ex" offset calls give offsets relative to a sample address of their own; the voice keeps its first one.
uint64_t rebased(const Voice& v, uint32_t offset, uint32_t samples) {
    if (samples == 0 || samples == v.samples) return to_sample(v, offset);
    const int64_t bytes = int64_t{samples} - int64_t{v.samples};
    switch (v.format) {
    case kPcm16: return static_cast<uint64_t>(int64_t{offset} + bytes / 2);
    case kAdpcm: return to_sample(v, static_cast<uint32_t>(int64_t{offset} + bytes * 2));
    default: return static_cast<uint64_t>(int64_t{offset} + bytes);
    }
}
uint32_t AXAcquireVoiceEx(PPCContext& ctx, uint32_t priority, uint32_t drop_callback, uint32_t user) {
    return AXAcquireVoice(ctx, priority, drop_callback, user);
}
void AXSetVoiceLoop(uint32_t vpb, uint32_t loop) {
    std::lock_guard lock(g_ax_mutex);
    if (Voice* v = voice_of(vpb)) {
        v->loop = loop != 0;
        field<uint16_t>(vpb, 0x34 + 0x02) = static_cast<uint16_t>(loop != 0);
    }
}
void AXSetVoiceLoopOffsetEx(uint32_t vpb, uint32_t offset, uint32_t samples) {
    std::lock_guard lock(g_ax_mutex);
    if (Voice* v = voice_of(vpb)) {
        v->loop_start = rebased(*v, offset, samples);
        field<uint32_t>(vpb, 0x34 + 0x04) = from_sample(*v, v->loop_start);
    }
}
void AXSetVoiceLoopOffset(uint32_t vpb, uint32_t offset) { AXSetVoiceLoopOffsetEx(vpb, offset, 0); }
void AXSetVoiceEndOffsetEx(uint32_t vpb, uint32_t offset, uint32_t samples) {
    std::lock_guard lock(g_ax_mutex);
    if (Voice* v = voice_of(vpb)) {
        v->end = rebased(*v, offset, samples);
        field<uint32_t>(vpb, 0x34 + 0x08) = from_sample(*v, v->end);
    }
}
void AXSetVoiceEndOffset(uint32_t vpb, uint32_t offset) { AXSetVoiceEndOffsetEx(vpb, offset, 0); }
void AXSetVoiceCurrentOffsetEx(uint32_t vpb, uint32_t offset, uint32_t samples) {
    std::lock_guard lock(g_ax_mutex);
    if (Voice* v = voice_of(vpb)) {
        v->cursor = rebased(*v, offset, samples);
        v->phase = 0;
        publish_state(*v);
    }
}
void AXSetVoiceCurrentOffset(uint32_t vpb, uint32_t offset) { AXSetVoiceCurrentOffsetEx(vpb, offset, 0); }
uint32_t AXGetVoiceCurrentOffsetEx(uint32_t vpb, be<uint32_t>* offset, uint32_t samples) {
    std::lock_guard lock(g_ax_mutex);
    Voice* v = voice_of(vpb);
    if (v == nullptr || offset == nullptr) return 0xFFFFFFFFu;
    int64_t value = from_sample(*v, v->cursor);
    if (samples != 0 && samples != v->samples) {
        const int64_t bytes = int64_t{samples} - int64_t{v->samples};
        value -= v->format == kPcm16 ? bytes / 2 : v->format == kAdpcm ? bytes * 2 : bytes;
    }
    *offset = static_cast<uint32_t>(value);
    return 0;
}
uint32_t AXGetVoiceLoopCount(uint32_t vpb) {
    std::lock_guard lock(g_ax_mutex);
    Voice* v = voice_of(vpb);
    return v ? v->loop_count : 0;
}
uint32_t AXIsVoiceRunning(uint32_t vpb) {
    std::lock_guard lock(g_ax_mutex);
    Voice* v = voice_of(vpb);
    return v && v->running ? 1 : 0;
}
void AXSetVoiceSamplesAddr(uint32_t vpb, uint32_t samples) {
    std::lock_guard lock(g_ax_mutex);
    if (Voice* v = voice_of(vpb)) {
        v->samples = samples;
        field<uint32_t>(vpb, 0x34 + 0x10) = samples;
    }
}
void AXSetVoicePriority(uint32_t vpb, uint32_t priority) {
    std::lock_guard lock(g_ax_mutex);
    if (voice_of(vpb)) field<uint32_t>(vpb, 0x1C) = priority;
}
// Application frame callbacks: any number, each called once per audio frame after the two system ones.
int32_t AXRegisterAppFrameCallback(uint32_t callback) {
    std::lock_guard lock(g_ax_mutex);
    for (uint32_t& slot : g_app_frame_callbacks) {
        if (slot == callback) return 0;
    }
    for (uint32_t& slot : g_app_frame_callbacks) {
        if (slot == 0) {
            slot = callback;
            return 0;
        }
    }
    return -17; // too many callbacks
}
int32_t AXDeregisterAppFrameCallback(uint32_t callback) {
    std::lock_guard lock(g_ax_mutex);
    for (uint32_t& slot : g_app_frame_callbacks) {
        if (slot == callback) {
            slot = 0;
            return 0;
        }
    }
    return -18; // not registered
}
int32_t AXGetDeviceFinalMixCallback(uint32_t device, be<uint32_t>* callback) {
    if (device > 1 || callback == nullptr) return -1;
    std::lock_guard lock(g_ax_mutex);
    *callback = g_final_mix_callbacks[device];
    return 0;
}
CAFE_EXPORT(snd_core, AXAcquireVoiceEx, AXAcquireVoiceEx);
CAFE_EXPORT(snd_core, AXSetVoiceLoop, AXSetVoiceLoop);
CAFE_EXPORT(snd_core, AXSetVoiceLoopOffset, AXSetVoiceLoopOffset);
CAFE_EXPORT(snd_core, AXSetVoiceLoopOffsetEx, AXSetVoiceLoopOffsetEx);
CAFE_EXPORT(snd_core, AXSetVoiceEndOffset, AXSetVoiceEndOffset);
CAFE_EXPORT(snd_core, AXSetVoiceEndOffsetEx, AXSetVoiceEndOffsetEx);
CAFE_EXPORT(snd_core, AXSetVoiceCurrentOffset, AXSetVoiceCurrentOffset);
CAFE_EXPORT(snd_core, AXSetVoiceCurrentOffsetEx, AXSetVoiceCurrentOffsetEx);
CAFE_EXPORT(snd_core, AXGetVoiceCurrentOffsetEx, AXGetVoiceCurrentOffsetEx);
CAFE_EXPORT(snd_core, AXGetVoiceLoopCount, AXGetVoiceLoopCount);
CAFE_EXPORT(snd_core, AXIsVoiceRunning, AXIsVoiceRunning);
CAFE_EXPORT(snd_core, AXSetVoiceSamplesAddr, AXSetVoiceSamplesAddr);
CAFE_EXPORT(snd_core, AXSetVoicePriority, AXSetVoicePriority);
CAFE_EXPORT(snd_core, AXRegisterAppFrameCallback, AXRegisterAppFrameCallback);
CAFE_EXPORT(snd_core, AXDeregisterAppFrameCallback, AXDeregisterAppFrameCallback);
CAFE_EXPORT(snd_core, AXGetDeviceFinalMixCallback, AXGetDeviceFinalMixCallback);

CAFE_EXPORT(snd_core, AXInit, AXInit);'''

edit('runtime/src/os/ax.cpp', [
    ('    uint16_t loop_pred_scale = 0;\n',
     '    uint32_t loop_count = 0; // times the voice went back to its loop start\n    uint16_t loop_pred_scale = 0;\n'),
    ('            v.cursor = v.loop_start;\n', '            v.cursor = v.loop_start;\n            ++v.loop_count;\n'),
    ('uint32_t g_frame_callback2 = 0;\n', 'uint32_t g_frame_callback2 = 0;\nuint32_t g_app_frame_callbacks[64]{};\n'),
    ('        uint32_t callback, callback2, final_mix[2];\n',
     '        uint32_t callback, callback2, final_mix[2], app_callbacks[64];\n'),
    ('            callback2 = g_frame_callback2;\n',
     '            callback2 = g_frame_callback2;\n            std::memcpy(app_callbacks, g_app_frame_callbacks, sizeof(app_callbacks));\n'),
    ('        if (callback2) call_guest(t->ctx, callback2, {});\n',
     '        if (callback2) call_guest(t->ctx, callback2, {});\n        for (uint32_t app : app_callbacks) {\n'
     '            if (app) call_guest(t->ctx, app, {});\n        }\n'),
    ('\nCAFE_EXPORT(snd_core, AXInit, AXInit);', AX_NEW),
])

HEAP_NEW = r'''// MEMCreateFrmHeapEx / MEMDestroyFrmHeap (port/patch_more_os.py): the heap's records live on the host side.
static uint32_t MEMCreateFrmHeapEx(GuestAddress start, uint32_t size, uint32_t) {
    std::lock_guard lock(g_heap_mutex);
    return create_frame_heap(start.value, size);
}
static GuestAddress MEMDestroyFrmHeap(GuestAddress heap) {
    std::lock_guard lock(g_heap_mutex);
    g_frame_heaps.erase(heap.value);
    return heap;
}
CAFE_EXPORT(coreinit, MEMCreateFrmHeapEx, MEMCreateFrmHeapEx);
CAFE_EXPORT(coreinit, MEMDestroyFrmHeap, MEMDestroyFrmHeap);
CAFE_EXPORT(coreinit, MEMFreeToFrmHeap, MEMFreeToFrmHeap);'''
edit('runtime/src/os/heap.cpp', [('CAFE_EXPORT(coreinit, MEMFreeToFrmHeap, MEMFreeToFrmHeap);', HEAP_NEW)])

ALIAS = r'''    const std::string_view m = module, n = name;
    // sndcore2 / snduser2 (newer titles' names for the sound libraries) are answered by snd_core / snd_user
    // (port/patch_more_os.py). Looked up by name on every call: a list walk, to be replaced if a title needs speed.
    if (m == "sndcore2" || m == "snduser2") {
        if (const cafe::Export* e = cafe::find_export(m == "sndcore2" ? "snd_core" : "snd_user", n)) {
            e->function(ctx, cafe::guest_base());
            return;
        }
    }
'''
edit('runtime/src/diagnostics.cpp', [('    const std::string_view m = module, n = name;\n', ALIAS),
                                      ('#include "cafe/generated.h"\n', '#include "cafe/export.h"\n#include "cafe/generated.h"\n')])
print('patch_more_os: done')
