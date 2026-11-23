"""snd_user MIX drives the voices' TV device mix (pan, span, fader, aux), not only their volume envelope.

Super Mario Bros. The Lost Levels (NES Virtual Console) was silent: its one sound voice (a looping PCM16 ring
buffer) is set up only through MIX (MIXAssignChannel, MIXInitInputControl, MIXInitDeviceControl, MIXSetInput,
MIXUpdateSettings) and never gets an AXSetVoiceDeviceMix of its own. The runtime's MIX only modelled the input
level (VE); MIXInitDeviceControl / MIXSetInput / MIXSetDevice* were no-ops, so the voice's device mix stayed 0.

Now MIX keeps per voice the TV control (aux[3], pan, span, fader, lfe), computes the channel gains from pan and
span as the console's MIX does (tables in 0.1 dB: round(100 log10((127 - i) / 127))), and on every
MIXUpdateSettings writes the TV device mix (main bus + three aux buses, ramped over one frame) of the voices whose
control changed. The input level now really follows MIXSetInput. GamePad and Wii Remote mixes are left to the title
(the runtime plays the TV output). TV sound modes other than mono are mixed as stereo (the host output is stereo).
Model: Cemu's snd_user (MPL-2.0), rewritten. TTT2_MIX_DEVICES=0 = old behaviour (no device mix from MIX).
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
OS = os.path.join(ROOT, "runtime/src/os")


def load(name):
    return open(os.path.join(OS, name), encoding="utf-8").read()


def save(name, text):
    open(os.path.join(OS, name), "w", encoding="utf-8", newline="\n").write(text)


snd = load("snd_user.cpp")
if "patch_mix_devices" in snd:
    print("already: snd_user.cpp")
    sys.exit(0)

# ---- ax.h / ax.cpp: a host entry point for a voice's TV device mix
axh = load("ax.h")
axh = axh.replace(
    "void set_voice_ve(uint32_t vpb, uint16_t volume, int16_t delta);\n",
    "void set_voice_ve(uint32_t vpb, uint16_t volume, int16_t delta);\n\n"
    "// port/patch_mix_devices.py: a voice's TV device mix, [channel][bus] volume (0x8000 = 1.0) and delta per\n"
    "// 32 kHz sample, as AXSetVoiceDeviceMix(vpb, 0, 0, mix) takes it.\n"
    "void set_voice_tv_mix(uint32_t vpb, const uint16_t volume[6][4], const int16_t delta[6][4]);\n",
)
save("ax.h", axh)

ax = load("ax.cpp")
anchor = "void set_voice_ve(uint32_t vpb, uint16_t volume, int16_t delta) {\n"
assert anchor in ax, "ax.cpp anchor"
ax = ax.replace(
    anchor,
    "void set_voice_tv_mix(uint32_t vpb, const uint16_t volume[6][4], const int16_t delta[6][4]) {\n"
    "    be<uint16_t> mix[kTvChannels * kBuses * 2];\n"
    "    for (int c = 0; c < kTvChannels; ++c) {\n"
    "        for (int b = 0; b < kBuses; ++b) {\n"
    "            mix[(c * kBuses + b) * 2] = volume[c][b];\n"
    "            mix[(c * kBuses + b) * 2 + 1] = static_cast<uint16_t>(delta[c][b]);\n"
    "        }\n"
    "    }\n"
    "    AXSetVoiceDeviceMix(vpb, 0, 0, mix);\n"
    "}\n\n" + anchor,
    1,
)
save("ax.cpp", ax)

# ---- offline_services.cpp: drop the no-op MIX device exports
off = load("offline_services.cpp")
for name in ("MIXInitDeviceControl", "MIXSetDeviceAux", "MIXSetDeviceFader", "MIXSetInput", "MIXSetSoundMode"):
    line = "CAFE_EXPORT(snd_user, %s, no_op);\n" % name
    assert line in off, line
    off = off.replace(line, "")
save("offline_services.cpp", off)

# ---- snd_user.cpp: the MIX section, rewritten
start = snd.index("// ------------------------------------------------------------------ MIX")
end = snd.index("} // namespace cafe::os")
MIX = r'''// ------------------------------------------------------------------ MIX
// port/patch_mix_devices.py. The channel mixer drives a voice's volume
// envelope from its input level and its TV device mix from pan, span, fader
// and aux sends (all in 0.1 dB; -90.4 dB and below is silence). Titles
// assign voices, set levels and call MIXUpdateSettings every audio frame;
// a change ramps over one frame. Only the TV device is mixed by MIX (the
// runtime plays the TV output); GamePad/Remote controls are stored only.
// Model: Cemu's snd_user (MPL-2.0). TTT2_MIX_DEVICES=0: no device mixes.

namespace {

constexpr uint32_t kMixInputChanged = 0x10000000; // input level set
constexpr uint32_t kMixRamping = 0x20000000;      // VE ramping to the target
constexpr uint32_t kMixVolumeChanged = 0x40000000; // device control changed
constexpr uint32_t kMixDeviceRamping = 0x80000000; // device mix ramping to the target
constexpr uint32_t kMixMute = 0x8;
constexpr int kAuxBuses = 3;
enum SoundMode : uint32_t { kMono = 0, kStereo = 1, kSurround = 2, kDpl2 = 3, kSixChannels = 4 };

// MixControl (guest, 0x0E bytes): aux[3], pan, span, fader, lfe (s16 each).
struct Control {
    int16_t aux[kAuxBuses] = {-960, -960, -960};
    int16_t pan = 64, span = 127, fader = 0, lfe = -960;
};

struct MixChannel {
    uint32_t voice = 0;
    uint32_t mode = 0;
    int16_t input = 0;
    uint16_t volume = 0, target = 0;
    Control tv;
    uint32_t tv_mode = 0;
    int16_t tv_gain[6]{};
    uint16_t tv_volume[4][6]{}, tv_target[4][6]{}; // [bus][channel]
    Control other[6]; // GamePad 0-1, Remote 0-3: stored only
};

std::mutex g_mix_mutex;
MixChannel g_mix_channels[96];
bool g_mix_initialized = false;
uint32_t g_tv_sound_mode = kStereo;

bool mix_devices_enabled() {
    static const bool on = [] {
        const char* v = std::getenv("TTT2_MIX_DEVICES");
        return v == nullptr || v[0] != '0';
    }();
    return on;
}

// 0.1 dB steps to AX volume (0x8000 = 0 dB), as MIX's table has them.
uint16_t translate_volume(int32_t level) {
    if (level <= -904) return 0;
    if (level >= 60) return 0xFF64;
    if (level == 0) return 0x7FFF;
    return static_cast<uint16_t>(32768.0 * std::pow(10.0, level / 200.0));
}

// MIX's pan table: round(100 log10((127 - i) / 127)), the last entry silence.
int16_t pan_level(int32_t i) {
    i = std::clamp(i, 0, 127);
    if (i == 127) return -904;
    return static_cast<int16_t>(std::lround(100.0 * std::log10((127.0 - i) / 127.0)));
}

MixChannel* mix_channel(uint32_t voice) {
    const uint32_t index = voice ? uint32_t{*guest<be<uint32_t>>(voice)} : ~0u;
    return index < 96 ? &g_mix_channels[index] : nullptr;
}

void reset_channel(MixChannel& c) {
    c = MixChannel{};
    c.mode = kMixInputChanged | kMixVolumeChanged;
}

// Channel gains of the TV control (stereo layout: 0 left, 1 right, 4/5 span).
void tv_gains(MixChannel& c) {
    const int pan = std::clamp<int>(c.tv.pan, 0, 127), span = std::clamp<int>(c.tv.span, 0, 127);
    c.tv_gain[0] = pan_level(pan);
    c.tv_gain[1] = pan_level(127 - pan);
    c.tv_gain[2] = 0;
    c.tv_gain[3] = 0;
    c.tv_gain[4] = pan_level(127 - span);
    c.tv_gain[5] = pan_level(span);
}

void update_tv(MixChannel& c) {
    if (!mix_devices_enabled()) return;
    bool changed = false;
    if (c.tv_mode & kMixDeviceRamping) {
        std::memcpy(c.tv_volume, c.tv_target, sizeof c.tv_volume);
        c.tv_mode &= ~kMixDeviceRamping;
        changed = true;
    }
    if (c.tv_mode & kMixVolumeChanged) {
        const int32_t span = std::max<int32_t>(c.tv_gain[4], -120);
        const int32_t fader = c.tv.fader;
        const bool mono = g_tv_sound_mode == kMono;
        const int32_t left = mono ? 0 : c.tv_gain[0], right = mono ? 0 : c.tv_gain[1];
        std::memset(c.tv_target, 0, sizeof c.tv_target);
        c.tv_target[0][0] = translate_volume(span + left + fader);
        c.tv_target[0][1] = translate_volume(span + right + fader);
        for (int a = 0; a < kAuxBuses; ++a) {
            // Mode bit a: the aux send is pre-fader.
            const int32_t base = ((c.tv_mode >> a) & 1) ? c.tv.aux[a] : fader + c.tv.aux[a];
            c.tv_target[1 + a][0] = translate_volume(span + left + base);
            c.tv_target[1 + a][1] = translate_volume(span + right + base);
        }
        c.tv_mode = (c.tv_mode & ~kMixVolumeChanged) | kMixDeviceRamping;
        changed = true;
    }
    if (!changed) return;
    uint16_t volume[6][4];
    int16_t delta[6][4];
    for (int ch = 0; ch < 6; ++ch) {
        for (int b = 0; b < 4; ++b) {
            volume[ch][b] = c.tv_volume[b][ch];
            delta[ch][b] = static_cast<int16_t>(
                std::clamp((int32_t{c.tv_target[b][ch]} - int32_t{c.tv_volume[b][ch]}) / 96, -32768, 32767));
        }
    }
    set_voice_tv_mix(c.voice, volume, delta);
}

Control* device_control(MixChannel& c, uint32_t device, uint32_t index, uint32_t** mode) {
    static uint32_t ignored;
    *mode = &ignored;
    if (device == 0) {
        *mode = &c.tv_mode;
        return &c.tv;
    }
    if (device == 1 && index < 2) return &c.other[index];
    if (device == 2 && index < 4) return &c.other[2 + index];
    return nullptr;
}

void MIXInit() {
    std::lock_guard lock(g_mix_mutex);
    if (g_mix_initialized) return;
    for (MixChannel& c : g_mix_channels) reset_channel(c);
    g_tv_sound_mode = kStereo;
    g_mix_initialized = true;
}

void MIXQuit() {
    std::lock_guard lock(g_mix_mutex);
    g_mix_initialized = false;
}

void MIXAssignChannel(uint32_t voice) {
    std::lock_guard lock(g_mix_mutex);
    if (MixChannel* c = mix_channel(voice)) {
        reset_channel(*c);
        c->voice = voice;
    }
}

void MIXReleaseChannel(uint32_t voice) {
    std::lock_guard lock(g_mix_mutex);
    if (MixChannel* c = mix_channel(voice)) c->voice = 0;
}

void MIXInitInputControl(uint32_t voice, int16_t input, uint32_t mode) {
    std::lock_guard lock(g_mix_mutex);
    if (MixChannel* c = mix_channel(voice)) {
        c->mode = (mode & kMixMute) | kMixInputChanged;
        c->input = input;
    }
}

void MIXSetInput(uint32_t voice, int16_t input) {
    std::lock_guard lock(g_mix_mutex);
    if (MixChannel* c = mix_channel(voice)) {
        c->input = input;
        c->mode |= kMixInputChanged;
    }
}

void MIXInitDeviceControl(uint32_t voice, uint32_t device, uint32_t index, uint32_t control, uint32_t mode) {
    std::lock_guard lock(g_mix_mutex);
    MixChannel* c = mix_channel(voice);
    if (c == nullptr || control == 0) return;
    c->voice = voice;
    uint32_t* device_mode;
    Control* target = device_control(*c, device, index, &device_mode);
    if (target == nullptr) return;
    const auto* g = guest<be<int16_t>>(control);
    *target = Control{};
    for (int a = 0; a < kAuxBuses; ++a) target->aux[a] = g[a];
    target->pan = g[3];
    target->span = g[4];
    target->fader = g[5]; // lfe is not taken from the control (as the console's MIX)
    *device_mode = (mode & 0xF) | kMixVolumeChanged;
    if (device == 0) {
        std::memset(c->tv_volume, 0, sizeof c->tv_volume);
        std::memset(c->tv_target, 0, sizeof c->tv_target);
        tv_gains(*c);
        update_tv(*c);
    }
}

template <typename Set>
void set_device(uint32_t voice, uint32_t device, uint32_t index, Set set) {
    std::lock_guard lock(g_mix_mutex);
    MixChannel* c = mix_channel(voice);
    if (c == nullptr) return;
    uint32_t* mode;
    Control* control = device_control(*c, device, index, &mode);
    if (control == nullptr || !set(*control)) return;
    if (device == 0) tv_gains(*c);
    *mode |= kMixVolumeChanged;
}

void MIXSetDeviceFader(uint32_t voice, uint32_t device, uint32_t index, int16_t fader) {
    set_device(voice, device, index, [&](Control& c) { return std::exchange(c.fader, fader) != fader; });
}
void MIXSetDevicePan(uint32_t voice, uint32_t device, uint32_t index, int16_t pan) {
    set_device(voice, device, index, [&](Control& c) { return std::exchange(c.pan, pan) != pan; });
}
void MIXSetDeviceSPan(uint32_t voice, uint32_t device, uint32_t index, int16_t span) {
    set_device(voice, device, index, [&](Control& c) { return std::exchange(c.span, span) != span; });
}
void MIXSetDeviceLFE(uint32_t voice, uint32_t device, uint32_t index, int16_t lfe) {
    if (device != 0) return;
    set_device(voice, device, index, [&](Control& c) { return std::exchange(c.lfe, lfe) != lfe; });
}
void MIXSetDeviceAux(uint32_t voice, uint32_t device, uint32_t index, uint32_t aux, int16_t level) {
    if (aux >= static_cast<uint32_t>(kAuxBuses)) return;
    set_device(voice, device, index, [&](Control& c) { return std::exchange(c.aux[aux], level) != level; });
}

void set_tv_sound_mode(uint32_t mode) {
    std::lock_guard lock(g_mix_mutex);
    const uint32_t m = mode == kMono ? kMono : kStereo; // the host output is stereo
    if (m == g_tv_sound_mode) return;
    g_tv_sound_mode = m;
    for (MixChannel& c : g_mix_channels) {
        if (c.voice) c.tv_mode |= kMixVolumeChanged;
    }
}

void MIXSetSoundMode(uint32_t mode) { set_tv_sound_mode(mode); }
uint32_t MIXGetSoundMode() { return g_tv_sound_mode; }
void MIXSetDeviceSoundMode(uint32_t device, uint32_t mode) {
    if (device == 0) set_tv_sound_mode(mode);
}

void MIXUpdateSettings() {
    std::lock_guard lock(g_mix_mutex);
    if (!g_mix_initialized) return;
    for (MixChannel& c : g_mix_channels) {
        if (c.voice == 0) continue;
        bool settled = false;
        if (c.mode & kMixRamping) {
            c.volume = c.target;
            c.mode &= ~kMixRamping;
            settled = true;
        }
        if (c.mode & kMixInputChanged) {
            c.target = (c.mode & kMixMute) ? 0 : translate_volume(c.input);
            c.mode = (c.mode & ~kMixInputChanged) | kMixRamping;
            settled = true;
        }
        if (settled) {
            set_voice_ve(c.voice, c.volume, static_cast<int16_t>((int32_t{c.target} - int32_t{c.volume}) / 96));
        }
        update_tv(c);
    }
}

} // namespace

CAFE_EXPORT(snd_user, MIXInit, MIXInit);
CAFE_EXPORT(snd_user, MIXQuit, MIXQuit);
CAFE_EXPORT(snd_user, MIXAssignChannel, MIXAssignChannel);
CAFE_EXPORT(snd_user, MIXReleaseChannel, MIXReleaseChannel);
CAFE_EXPORT(snd_user, MIXInitInputControl, MIXInitInputControl);
CAFE_EXPORT(snd_user, MIXSetInput, MIXSetInput);
CAFE_EXPORT(snd_user, MIXInitDeviceControl, MIXInitDeviceControl);
CAFE_EXPORT(snd_user, MIXSetDeviceFader, MIXSetDeviceFader);
CAFE_EXPORT(snd_user, MIXSetDevicePan, MIXSetDevicePan);
CAFE_EXPORT(snd_user, MIXSetDeviceSPan, MIXSetDeviceSPan);
CAFE_EXPORT(snd_user, MIXSetDeviceLFE, MIXSetDeviceLFE);
CAFE_EXPORT(snd_user, MIXSetDeviceAux, MIXSetDeviceAux);
CAFE_EXPORT(snd_user, MIXSetSoundMode, MIXSetSoundMode);
CAFE_EXPORT(snd_user, MIXGetSoundMode, MIXGetSoundMode);
CAFE_EXPORT(snd_user, MIXUpdateSettings, MIXUpdateSettings);
CAFE_EXPORT(snd_user, MIXSetDeviceSoundMode, MIXSetDeviceSoundMode);

'''
snd = snd[:start] + MIX + snd[end:]
for inc in ("#include <algorithm>\n", "#include <cstdlib>\n", "#include <cstring>\n", "#include <utility>\n"):
    if inc not in snd:
        snd = snd.replace("#include <cmath>\n", "#include <cmath>\n" + inc, 1)
save("snd_user.cpp", snd)
print("patched: snd_user.cpp (MIX device mixes), ax.cpp/ax.h (set_voice_tv_mix), offline_services.cpp")
