#!/usr/bin/env python3
"""Wii Remote emulation (KPAD/WPAD) for the runtime.

usage: patch_wiimote.py RUNTIME_DIR   (e.g. ~/wiiu/smash4/runtime)

Before: padscore knew only Wii U Pro Controllers; a title that wants Wii Remotes (Sochi 2014 lists them on its
player-count screen) saw none. After: with CAFE_WIIMOTE=1 the KPAD channels 0-3 are Wii Remotes (+ Nunchuk):
 - real Wii Remotes from the Linux kernel driver hid-wiimote (evdev devices "Nintendo Wii Remote*": buttons,
   accelerometer, IR pointer, Nunchuk) take the first channels (host/window.cpp, Linux only);
 - every other host pad emulates one (host pad -> Wii Remote held upright + Nunchuk):
     east/south/west/north = A / B / 1 / 2, D-pad = D-pad, start/back/guide = + / - / HOME,
     left stick = Nunchuk stick, LT = Z, LB = C, RB = shake the remote, R3 = shake the Nunchuk,
     right stick = IR pointer (on the screen while moved and 3 s after; else pointing away),
     RT held + right stick = tilt the remote.
CAFE_WIIMOTE_GAMEPAD=0: the first host pad no longer drives the GamePad as well (default 1: both).
CAFE_WIIMOTE_NO_EVDEV=1: ignore real remotes. CAFE_WIIMOTE_IR_FLIP=x|y|xy: mirror the real pointer.
KPADStatus layout checked against Sochi's SetInputFromKpadStatus (acc 0x0C, pos 0x20, ext type 0x5C,
pos valid 0x5E, Nunchuk stick 0x60 / acc 0x68 / variation 0x78, MotionPlus 0xB0).
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])


def sub(path, old, new, count=1):
    p = root / path
    text = p.read_text()
    if new in text:
        print(f"{path}: already patched")
        return
    if text.count(old) != count:
        sys.exit(f"{path}: expected {count}x {old[:60]!r}, found {text.count(old)}")
    p.write_text(text.replace(old, new))
    print(f"{path}: ok")


# ------------------------------------------------------------------ input.h
sub("include/cafe/input.h", """void set_pro_pad_state(int channel, const ProPadState& state);""",
    """void set_pro_pad_state(int channel, const ProPadState& state);

// port/patch_wiimote.py: Wii Remotes (+ Nunchuk) on the KPAD channels 0-3, with CAFE_WIIMOTE=1.
namespace wiimote {
constexpr int kChannels = 4;
// core buttons as KPAD/WPAD has them (Z and C are the Nunchuk's)
constexpr uint32_t kLeft = 0x0001, kRight = 0x0002, kDown = 0x0004, kUp = 0x0008, kPlus = 0x0010;
constexpr uint32_t kTwo = 0x0100, kOne = 0x0200, kB = 0x0400, kA = 0x0800, kMinus = 0x1000;
constexpr uint32_t kZ = 0x2000, kC = 0x4000, kHome = 0x8000;
} // namespace wiimote

struct WiimoteState {
    bool connected = false;
    bool nunchuk = false;
    uint32_t buttons = 0;                      // wiimote::k*
    float acc[3] = {0.0f, -1.0f, 0.0f};        // KPAD frame, in g: lying flat, pointing at the screen
    float nunchuk_acc[3] = {0.0f, -1.0f, 0.0f};
    float stick_x = 0.0f, stick_y = 0.0f;      // Nunchuk, -1..1, up positive
    bool pointer_valid = false;
    float pointer_x = 0.0f, pointer_y = 0.0f;  // -1..1, y down
};

bool wiimote_mode(); // CAFE_WIIMOTE=1
void set_wiimote_state(int channel, const WiimoteState& state);""")

# ----------------------------------------------------------------- input.cpp
sub("src/os/input.cpp", """struct ProChannel {
    ProPadState host{};     // as the host has it""", """struct ProChannel {
    WiimoteState wiimote{}; // port/patch_wiimote.py: this channel is a Wii Remote (wiimote.connected)
    uint32_t wm_previous = 0;
    float wm_acc[3] = {0.0f, -1.0f, 0.0f}, wm_nunchuk_acc[3] = {0.0f, -1.0f, 0.0f}, wm_pos[2] = {0.0f, 0.0f};
    ProPadState host{};     // as the host has it""")

sub("src/os/input.cpp", """int32_t KPADReadEx(int32_t channel, KPADStatus* status, uint32_t count, be<int32_t>* error) {
    std::lock_guard lock(g_input_mutex);
    if (channel < 0 || channel >= pro::kChannels || !g_pro[channel].connected || status == nullptr || count == 0) {
        if (error) *error = kWpadNoController;
        return 0;
    }
    ProChannel& c = g_pro[channel];
    std::memset(status, 0, sizeof(KPADStatus));""", """// port/patch_wiimote.py: a Wii Remote's sample. Extension types: 0 remote, 1 + Nunchuk.
constexpr uint8_t kExtCore = 0, kExtNunchuk = 1;
uint8_t wiimote_type(const ProChannel& c) { return c.wiimote.nunchuk ? kExtNunchuk : kExtCore; }

void put_f(KPADStatus* s, size_t offset, float v) {
    *reinterpret_cast<be<float>*>(reinterpret_cast<uint8_t*>(s) + offset) = v;
}

void fill_wiimote(ProChannel& c, KPADStatus* status) {
    WiimoteState w = c.wiimote;
    if (&c == &g_pro[0]) {
        w.buttons |= script_wiimote_buttons(g_script_vpad);
        if (g_script_stick_on) {
            w.stick_x = g_script_stick[0];
            w.stick_y = g_script_stick[1];
        }
        float tx = 0.0f, ty = 0.0f; // a scripted touch ("t:touch=x/y/s") also points remote 0 there
        if (scripted_touch(tx, ty)) {
            w.pointer_valid = true;
            w.pointer_x = tx * 2.0f - 1.0f;
            w.pointer_y = ty * 2.0f - 1.0f;
        }
        static int phase = 0;
        if (g_script_vpad & (vpad::kR | vpad::kZR)) {
            ++phase;
            float* a = (g_script_vpad & vpad::kR) ? w.acc : w.nunchuk_acc;
            a[1] += 2.5f * std::sin(phase * 0.6f);
            a[2] += 1.5f * std::cos(phase * 0.6f);
        }
    }
    status->hold = w.buttons;
    status->trigger = w.buttons & ~c.wm_previous;
    status->release = c.wm_previous & ~w.buttons;
    c.wm_previous = w.buttons;
    const auto length = [](const float* v) { return std::sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]); };
    const float variation = std::sqrt((w.acc[0] - c.wm_acc[0]) * (w.acc[0] - c.wm_acc[0]) +
                                      (w.acc[1] - c.wm_acc[1]) * (w.acc[1] - c.wm_acc[1]) +
                                      (w.acc[2] - c.wm_acc[2]) * (w.acc[2] - c.wm_acc[2]));
    for (int i = 0; i < 3; ++i) put_f(status, 0x0C + 4 * i, w.acc[i]);
    put_f(status, 0x18, length(w.acc));
    put_f(status, 0x1C, variation);
    if (w.pointer_valid) {
        put_f(status, 0x20, w.pointer_x);
        put_f(status, 0x24, w.pointer_y);
        put_f(status, 0x28, w.pointer_x - c.wm_pos[0]);
        put_f(status, 0x2C, w.pointer_y - c.wm_pos[1]);
        put_f(status, 0x30, std::hypot(w.pointer_x - c.wm_pos[0], w.pointer_y - c.wm_pos[1]));
        put_f(status, 0x48, 1.0f); // distance to the sensor bar, metres
        c.wm_pos[0] = w.pointer_x;
        c.wm_pos[1] = w.pointer_y;
    }
    // horizon: the roll as a unit vector (x right, y down), from gravity in the x/y plane
    const float roll = std::hypot(w.acc[0], w.acc[1]);
    put_f(status, 0x34, roll > 0.0f ? -w.acc[1] / roll : 1.0f);
    put_f(status, 0x38, roll > 0.0f ? w.acc[0] / roll : 0.0f);
    const float vertical = std::hypot(w.acc[1], w.acc[2]);
    put_f(status, 0x54, vertical > 0.0f ? -w.acc[2] / vertical : 0.0f);
    put_f(status, 0x58, vertical > 0.0f ? -w.acc[1] / vertical : 1.0f);
    std::memcpy(c.wm_acc, w.acc, sizeof c.wm_acc);
    status->extension_type = wiimote_type(c);
    status->error = 0;
    status->pos_valid = w.pointer_valid ? 1 : 0;
    status->format = w.nunchuk ? 5 : 2; // NUNCHUK_ACC_DPD / CORE_ACC_DPD
    if (w.nunchuk) {
        put_f(status, 0x60, w.stick_x);
        put_f(status, 0x64, w.stick_y);
        for (int i = 0; i < 3; ++i) put_f(status, 0x68 + 4 * i, w.nunchuk_acc[i]);
        put_f(status, 0x74, length(w.nunchuk_acc));
        float v = 0.0f;
        for (int i = 0; i < 3; ++i) v += (w.nunchuk_acc[i] - c.wm_nunchuk_acc[i]) * (w.nunchuk_acc[i] - c.wm_nunchuk_acc[i]);
        put_f(status, 0x78, std::sqrt(v));
        std::memcpy(c.wm_nunchuk_acc, w.nunchuk_acc, sizeof c.wm_nunchuk_acc);
    }
}

int32_t KPADReadEx(int32_t channel, KPADStatus* status, uint32_t count, be<int32_t>* error) {
    std::lock_guard lock(g_input_mutex);
    if (channel < 0 || channel >= pro::kChannels || !g_pro[channel].connected || status == nullptr || count == 0) {
        if (error) *error = kWpadNoController;
        return 0;
    }
    ProChannel& c = g_pro[channel];
    std::memset(status, 0, sizeof(KPADStatus));
    if (c.wiimote.connected) { // port/patch_wiimote.py
        fill_wiimote(c, status);
        if (error) *error = 0;
        return 1;
    }""")

sub("src/os/input.cpp", """    if (type) *type = connected ? kExtProController : kNoDevice;
    return connected ? 0 : kWpadNoController;
}""", """    if (type) *type = !connected ? kNoDevice : g_pro[channel].wiimote.connected ? wiimote_type(g_pro[channel]) : kExtProController;
    return connected ? 0 : kWpadNoController;
}
int32_t KPADRead(int32_t channel, KPADStatus* status, uint32_t count) { // port/patch_wiimote.py
    return KPADReadEx(channel, status, count, nullptr);
}""")

sub("src/os/input.cpp", """#include <algorithm> // port/patch_touch_ui.py""", """#include <algorithm> // port/patch_touch_ui.py
#include <cmath>     // port/patch_wiimote.py""")

sub("src/os/input.cpp", """bool pro_controllers_in_use() {""", """// port/patch_wiimote.py
bool wiimote_mode() {
    static const bool on = [] {
        const char* v = std::getenv("CAFE_WIIMOTE");
        return v != nullptr && *v != '\\0' && *v != '0';
    }();
    return on;
}

void set_wiimote_state(int channel, const WiimoteState& state) {
    if (channel < 0 || channel >= wiimote::kChannels) return;
    std::lock_guard lock(g_input_mutex);
    ProChannel& c = g_pro[channel];
    const bool was = c.connected;
    const bool type_changed = was && c.wiimote.connected && state.connected && c.wiimote.nunchuk != state.nunchuk;
    c.wiimote = state;
    if (!state.connected) {
        c.dropped = false;
        if (was) g_pending_connects.push_back({channel, kWpadNoController});
        c.connected = false;
    } else if (!was && (!c.dropped || state.buttons != 0)) {
        c.connected = true;
        c.dropped = false;
        c.wm_previous = state.buttons;
        g_pending_connects.push_back({channel, 0});
    } else if (type_changed) { // a Nunchuk plugged in or out: the title probes again
        g_pending_connects.push_back({channel, 0});
    }
}

bool pro_controllers_in_use() {""")

sub("src/os/input.cpp", """void VPADInit() {}""", """// TTT2_INPUT_SCRIPT presses (taken in VPADRead) reach Wii Remote 0 too: A B X=1 Y=2, D-pad, + - HOME,
// ZL = Z, L = C, R = shake the remote, ZR = shake the Nunchuk; the scripted stick is the Nunchuk's.
uint32_t g_script_vpad = 0;
float g_script_stick[2] = {0.0f, 0.0f};
bool g_script_stick_on = false;

uint32_t script_wiimote_buttons(uint32_t v) {
    static const std::pair<uint32_t, uint32_t> kMap[] = {
        {vpad::kA, wiimote::kA}, {vpad::kB, wiimote::kB}, {vpad::kX, wiimote::kOne}, {vpad::kY, wiimote::kTwo},
        {vpad::kUp, wiimote::kUp}, {vpad::kDown, wiimote::kDown}, {vpad::kLeft, wiimote::kLeft},
        {vpad::kRight, wiimote::kRight}, {vpad::kPlus, wiimote::kPlus}, {vpad::kMinus, wiimote::kMinus},
        {vpad::kHome, wiimote::kHome}, {vpad::kZL, wiimote::kZ}, {vpad::kL, wiimote::kC},
    };
    uint32_t out = 0;
    for (const auto& [from, to] : kMap) out |= (v & from) ? to : 0;
    return out;
}

void VPADInit() {}""")

sub("src/os/input.cpp", """    const uint32_t hold = gate_start(pad.buttons | scripted_buttons());""",
    """    const uint32_t scripted = scripted_buttons(); // port/patch_wiimote.py: also Wii Remote 0's
    static const bool remote_only = std::getenv("TTT2_SCRIPT_REMOTE_ONLY") != nullptr; // script presses: remote 0 only
    const uint32_t hold = gate_start(pad.buttons | (remote_only ? 0u : scripted));
    g_script_vpad = scripted;
    g_script_stick_on = scripted_stick(g_script_stick[0], g_script_stick[1]);""")

sub("src/os/input.cpp", """        const bool touched = scripted_touch(tx, ty) || pad.touch;""",
    """        const bool touched = (!remote_only && scripted_touch(tx, ty)) || pad.touch; // port/patch_wiimote.py""")

sub("src/os/input.cpp", """CAFE_EXPORT(padscore, KPADReadEx, KPADReadEx);""", """CAFE_EXPORT(padscore, KPADReadEx, KPADReadEx);
CAFE_EXPORT(padscore, KPADRead, KPADRead); // port/patch_wiimote.py""")

# ---------------------------------------------------------------- window.cpp
sub("src/host/window.cpp", """void update_input() {
    update_virtual_pads();""", """// ------------------------------------------------- port/patch_wiimote.py
// A host pad as a Wii Remote held upright with a Nunchuk (see the patch's header for the buttons).
struct PadMotion {
    double shake_phase = 0.0, nunchuk_phase = 0.0;
    float tilt_x = 0.0f, tilt_y = 0.0f;
    float pointer_x = 0.0f, pointer_y = 0.0f;
    double pointer_until = 0.0; // the pointer stays on the screen this long after the stick moved
};
std::array<PadMotion, os::wiimote::kChannels> g_pad_motion;

os::WiimoteState wiimote_from_pad(SDL_Gamepad* pad, PadMotion& m, float dt) {
    os::WiimoteState w;
    w.connected = true;
    w.nunchuk = true;
    struct Map { SDL_GamepadButton button; uint32_t bit; };
    static constexpr Map kMap[] = {
        {SDL_GAMEPAD_BUTTON_EAST, os::wiimote::kA},       {SDL_GAMEPAD_BUTTON_SOUTH, os::wiimote::kB},
        {SDL_GAMEPAD_BUTTON_WEST, os::wiimote::kOne},     {SDL_GAMEPAD_BUTTON_NORTH, os::wiimote::kTwo},
        {SDL_GAMEPAD_BUTTON_DPAD_UP, os::wiimote::kUp},   {SDL_GAMEPAD_BUTTON_DPAD_DOWN, os::wiimote::kDown},
        {SDL_GAMEPAD_BUTTON_DPAD_LEFT, os::wiimote::kLeft}, {SDL_GAMEPAD_BUTTON_DPAD_RIGHT, os::wiimote::kRight},
        {SDL_GAMEPAD_BUTTON_START, os::wiimote::kPlus},   {SDL_GAMEPAD_BUTTON_BACK, os::wiimote::kMinus},
        {SDL_GAMEPAD_BUTTON_GUIDE, os::wiimote::kHome},   {SDL_GAMEPAD_BUTTON_LEFT_SHOULDER, os::wiimote::kC},
    };
    for (const Map& b : kMap) {
        if (SDL_GetGamepadButton(pad, b.button)) w.buttons |= b.bit;
    }
    if (axis(pad, SDL_GAMEPAD_AXIS_LEFT_TRIGGER) > 0.5f) w.buttons |= os::wiimote::kZ;
    w.stick_x = axis(pad, SDL_GAMEPAD_AXIS_LEFTX);
    w.stick_y = -axis(pad, SDL_GAMEPAD_AXIS_LEFTY);
    const float rx = axis(pad, SDL_GAMEPAD_AXIS_RIGHTX), ry = axis(pad, SDL_GAMEPAD_AXIS_RIGHTY);
    const bool tilting = axis(pad, SDL_GAMEPAD_AXIS_RIGHT_TRIGGER) > 0.5f;
    // tilt: eases towards the stick (a hand does not turn instantly); up = nose up, right = roll right
    const float ease = std::min(1.0f, dt * 12.0f);
    m.tilt_x += ((tilting ? rx : 0.0f) - m.tilt_x) * ease;
    m.tilt_y += ((tilting ? -ry : 0.0f) - m.tilt_y) * ease;
    const float roll = m.tilt_x * 1.3f, pitch = m.tilt_y * 1.3f; // up to ~75 degrees
    w.acc[0] = std::sin(roll) * std::cos(pitch);
    w.acc[1] = -std::cos(roll) * std::cos(pitch);
    w.acc[2] = std::sin(pitch);
    // the pointer: on the screen while the right stick is moved and 3 s after (else "pointing away", so menus
    // stay in D-pad mode); the stick's position is the pointer's
    const double now = SDL_GetTicks() / 1000.0;
    if (!tilting && (rx != 0.0f || ry != 0.0f)) {
        m.pointer_x = rx;
        m.pointer_y = ry;
        m.pointer_until = now + 3.0;
    }
    w.pointer_valid = now < m.pointer_until;
    w.pointer_x = m.pointer_x;
    w.pointer_y = m.pointer_y;
    // shaking: ~6 swings a second, 2.5 g up/down and back/forth
    if (SDL_GetGamepadButton(pad, SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER)) {
        m.shake_phase += dt * 6.0 * 2.0 * 3.14159265;
        w.acc[1] += 2.5f * static_cast<float>(std::sin(m.shake_phase));
        w.acc[2] += 1.5f * static_cast<float>(std::cos(m.shake_phase));
    } else {
        m.shake_phase = 0.0;
    }
    if (SDL_GetGamepadButton(pad, SDL_GAMEPAD_BUTTON_RIGHT_STICK)) {
        m.nunchuk_phase += dt * 6.0 * 2.0 * 3.14159265;
        w.nunchuk_acc[1] += 2.5f * static_cast<float>(std::sin(m.nunchuk_phase));
        w.nunchuk_acc[2] += 1.5f * static_cast<float>(std::cos(m.nunchuk_phase));
    } else {
        m.nunchuk_phase = 0.0;
    }
    return w;
}

#ifdef __linux__
// Real Wii Remotes through the kernel driver hid-wiimote: it makes one evdev device per part
// ("Nintendo Wii Remote", "... Accelerometer", "... IR", "... Nunchuk"), the same uniq (address) on all.
// The accelerometer and IR camera only run while their device is open.
struct RealRemote {
    std::string uniq;
    int keys = -1, accel = -1, ir = -1, nunchuk = -1;
    os::WiimoteState state;
    float ir_x[4] = {1023, 1023, 1023, 1023}, ir_y[4] = {1023, 1023, 1023, 1023};
    float acc_raw[3] = {0, 0, 100}, nunchuk_raw[3] = {0, 0, 100};
};
std::vector<RealRemote> g_real_remotes;

void close_remote(RealRemote& r) {
    for (int* fd : {&r.keys, &r.accel, &r.ir, &r.nunchuk}) {
        if (*fd >= 0) close(*fd);
        *fd = -1;
    }
}

void scan_real_remotes() {
    static const bool off = std::getenv("CAFE_WIIMOTE_NO_EVDEV") != nullptr;
    static double next_scan = 0.0;
    const double now = SDL_GetTicks() / 1000.0;
    if (off || now < next_scan) return;
    next_scan = now + 2.0;
    DIR* dir = opendir("/dev/input");
    if (dir == nullptr) return;
    std::vector<std::string> seen_paths;
    while (dirent* e = readdir(dir)) {
        if (std::strncmp(e->d_name, "event", 5) != 0) continue;
        const std::string path = std::string("/dev/input/") + e->d_name;
        bool known = false; // a device already held: its path is behind one of our descriptors
        for (const RealRemote& x : g_real_remotes) {
            for (int fd : {x.keys, x.accel, x.ir, x.nunchuk}) {
                char link[64] = {};
                if (fd >= 0 && readlink(("/proc/self/fd/" + std::to_string(fd)).c_str(), link, sizeof link - 1) > 0)
                    known = known || path == link;
            }
        }
        if (known) continue;
        const int fd = open(path.c_str(), O_RDONLY | O_NONBLOCK | O_CLOEXEC);
        if (fd < 0) continue;
        char name[128] = {}, uniq[64] = {};
        ioctl(fd, EVIOCGNAME(sizeof name - 1), name);
        if (ioctl(fd, EVIOCGUNIQ(sizeof uniq - 1), uniq) < 0 || uniq[0] == '\\0') ioctl(fd, EVIOCGPHYS(sizeof uniq - 1), uniq);
        const std::string n = name;
        if (n.rfind("Nintendo Wii Remote", 0) != 0 || n.find("Pro Controller") != std::string::npos ||
            n.find("Balance") != std::string::npos || n.find("Classic") != std::string::npos ||
            n.find("Motion Plus") != std::string::npos) {
            close(fd);
            continue;
        }
        RealRemote* r = nullptr;
        for (RealRemote& x : g_real_remotes) r = x.uniq == uniq ? &x : r;
        if (r == nullptr) {
            g_real_remotes.push_back({uniq});
            r = &g_real_remotes.back();
        }
        int* slot = n == "Nintendo Wii Remote" ? &r->keys : n.find("Accelerometer") != std::string::npos ? &r->accel
                  : n.find(" IR") != std::string::npos ? &r->ir : n.find("Nunchuk") != std::string::npos ? &r->nunchuk : nullptr;
        if (slot == nullptr || *slot >= 0) {
            close(fd);
            continue;
        }
        *slot = fd;
        std::fprintf(stderr, "ttt2: wiimote: %s (%s) = %s\\n", name, uniq, path.c_str());
    }
    closedir(dir);
}

// Reads what the remotes sent; a remote whose main device went away is dropped.
void read_real_remotes() {
    scan_real_remotes();
    for (RealRemote& r : g_real_remotes) {
        os::WiimoteState& w = r.state;
        auto drain = [&](int& fd, auto&& on_event) {
            if (fd < 0) return;
            input_event ev[64];
            for (;;) {
                const ssize_t n = read(fd, ev, sizeof ev);
                if (n < 0 && errno == ENODEV) { close(fd); fd = -1; return; }
                if (n <= 0) return;
                for (ssize_t i = 0; i < n / static_cast<ssize_t>(sizeof(input_event)); ++i) on_event(ev[i]);
            }
        };
        drain(r.keys, [&](const input_event& e) {
            if (e.type != EV_KEY) return;
            uint32_t bit = 0;
            switch (e.code) {
            case KEY_LEFT: bit = os::wiimote::kLeft; break;
            case KEY_RIGHT: bit = os::wiimote::kRight; break;
            case KEY_UP: bit = os::wiimote::kUp; break;
            case KEY_DOWN: bit = os::wiimote::kDown; break;
            case KEY_NEXT: bit = os::wiimote::kPlus; break;
            case KEY_PREVIOUS: bit = os::wiimote::kMinus; break;
            case BTN_1: bit = os::wiimote::kOne; break;
            case BTN_2: bit = os::wiimote::kTwo; break;
            case BTN_A: bit = os::wiimote::kA; break;
            case BTN_B: bit = os::wiimote::kB; break;
            case BTN_MODE: bit = os::wiimote::kHome; break;
            default: return;
            }
            if (e.value) w.buttons |= bit;
            else w.buttons &= ~bit;
        });
        drain(r.accel, [&](const input_event& e) {
            if (e.type == EV_ABS && e.code >= ABS_RX && e.code <= ABS_RZ) r.acc_raw[e.code - ABS_RX] = static_cast<float>(e.value);
        });
        drain(r.nunchuk, [&](const input_event& e) {
            if (e.type == EV_ABS && e.code >= ABS_RX && e.code <= ABS_RZ) r.nunchuk_raw[e.code - ABS_RX] = static_cast<float>(e.value);
            if (e.type == EV_ABS && e.code == ABS_HAT0X) w.stick_x = std::clamp(e.value / 100.0f, -1.0f, 1.0f);
            if (e.type == EV_ABS && e.code == ABS_HAT0Y) w.stick_y = std::clamp(e.value / 100.0f, -1.0f, 1.0f);
            if (e.type == EV_KEY && (e.code == BTN_C || e.code == BTN_Z)) {
                const uint32_t bit = e.code == BTN_C ? os::wiimote::kC : os::wiimote::kZ;
                if (e.value) w.buttons |= bit;
                else w.buttons &= ~bit;
            }
        });
        drain(r.ir, [&](const input_event& e) {
            if (e.type != EV_ABS || e.code < ABS_HAT0X || e.code > ABS_HAT3Y) return;
            const int k = (e.code - ABS_HAT0X) / 2;
            ((e.code - ABS_HAT0X) % 2 ? r.ir_y : r.ir_x)[k] = static_cast<float>(e.value);
        });
        // sensor axes (x left, y forward, z up; ~100 per g) -> KPAD frame (as Nintendo's KPAD converts them)
        constexpr float kPerG = 100.0f;
        w.acc[0] = -r.acc_raw[0] / kPerG;
        w.acc[1] = -r.acc_raw[2] / kPerG;
        w.acc[2] = r.acc_raw[1] / kPerG;
        w.nunchuk = r.nunchuk >= 0;
        if (!w.nunchuk) w.buttons &= ~(os::wiimote::kC | os::wiimote::kZ);
        w.nunchuk_acc[0] = -r.nunchuk_raw[0] / kPerG;
        w.nunchuk_acc[1] = -r.nunchuk_raw[2] / kPerG;
        w.nunchuk_acc[2] = r.nunchuk_raw[1] / kPerG;
        // pointer: the middle of the first two dots the camera sees (1024x768; 1023 = none)
        float sx = 0, sy = 0;
        int dots = 0;
        for (int k = 0; k < 4 && dots < 2; ++k) {
            if (r.ir_x[k] >= 1023 || r.ir_y[k] >= 1023) continue;
            sx += r.ir_x[k];
            sy += r.ir_y[k];
            ++dots;
        }
        static const char* flip = std::getenv("CAFE_WIIMOTE_IR_FLIP");
        w.pointer_valid = dots > 0;
        if (dots > 0) {
            w.pointer_x = (512.0f - sx / dots) / 512.0f; // the camera sees the bar move the other way
            w.pointer_y = (sy / dots - 384.0f) / 384.0f;
            if (flip && std::strchr(flip, 'x')) w.pointer_x = -w.pointer_x;
            if (flip && std::strchr(flip, 'y')) w.pointer_y = -w.pointer_y;
        }
        w.connected = r.keys >= 0;
        if (!w.connected) close_remote(r);
    }
    std::erase_if(g_real_remotes, [](const RealRemote& r) { return r.keys < 0 && r.accel < 0 && r.ir < 0 && r.nunchuk < 0; });
}
#endif

// Real remotes first, then host pads by slot. Returns which host pads became remotes.
void update_wiimotes(const SDL_JoystickID* ids, int count, std::vector<SDL_JoystickID>& as_remote) {
    static auto last = std::chrono::steady_clock::now();
    const auto now = std::chrono::steady_clock::now();
    const float dt = std::clamp(std::chrono::duration<float>(now - last).count(), 0.0f, 0.1f);
    last = now;
    std::array<os::WiimoteState, os::wiimote::kChannels> states{};
    int channel = 0;
#ifdef __linux__
    read_real_remotes();
    for (const RealRemote& r : g_real_remotes) {
        if (channel < os::wiimote::kChannels && r.state.connected) states[channel++] = r.state;
    }
#endif
    const int real = channel;
    for (size_t slot = 0; slot < g_pad_slots.size() && channel < os::wiimote::kChannels; ++slot) {
        const SDL_JoystickID id = g_pad_slots[slot];
        if (id == 0 || id == kGuestSlot || std::find(ids, ids + count, id) == ids + count) continue;
        SDL_Gamepad* pad = SDL_GetGamepadFromID(id);
        if (pad == nullptr) continue;
        const char* name = SDL_GetGamepadName(pad);
        if (real > 0 && name && std::strstr(name, "Wii Remote")) continue; // read directly above
        states[channel] = wiimote_from_pad(pad, g_pad_motion[channel], dt);
        ++channel;
        as_remote.push_back(id);
    }
    static const bool scripted = std::getenv("TTT2_INPUT_SCRIPT") != nullptr;
    if (channel == 0 && scripted) { // unattended runs: remote 0 exists for the script (os/input.cpp)
        states[0].connected = true;
        states[0].nunchuk = true; // its pointer: "t:touch=x/y/s" (os/input.cpp)
    }
    for (int c = 0; c < os::wiimote::kChannels; ++c) os::set_wiimote_state(c, states[c]);
}

void update_input() {
    update_virtual_pads();""")

sub("src/host/window.cpp", """    const bool pros = os::pro_controllers_in_use();
    int count = 0;
    SDL_JoystickID* ids = SDL_GetGamepads(&count);
    if (pros) assign_pad_slots(ids, count);""", """    const bool wiimotes = os::wiimote_mode(); // port/patch_wiimote.py
    const bool pros = os::pro_controllers_in_use() && !wiimotes;
    int count = 0;
    SDL_JoystickID* ids = SDL_GetGamepads(&count);
    if (pros || wiimotes) assign_pad_slots(ids, count);
    std::vector<SDL_JoystickID> as_remote;
    static const bool remote_drives_gamepad = [] {
        const char* v = std::getenv("CAFE_WIIMOTE_GAMEPAD");
        return v == nullptr || *v != '0';
    }();
    if (wiimotes) update_wiimotes(ids, count, as_remote);""")

sub("src/host/window.cpp", """        if (pad == nullptr) continue;
        if (pros) {""", """        if (pad == nullptr) continue;
        if (wiimotes && std::find(as_remote.begin(), as_remote.end(), ids[i]) != as_remote.end() &&
            (!remote_drives_gamepad || ids[i] != g_pad_slots[0])) continue; // port/patch_wiimote.py
        if (wiimotes && SDL_GetGamepadName(pad) && std::strstr(SDL_GetGamepadName(pad), "Wii Remote")) continue;
        if (pros) {""")

sub("src/host/window.cpp", """#include <SDL3/SDL_vulkan.h>
""", """#include <SDL3/SDL_vulkan.h>

#ifdef __linux__ // port/patch_wiimote.py: real Wii Remotes through evdev
#include <dirent.h>
#include <fcntl.h>
#include <linux/input.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <cerrno>
#endif
""")
