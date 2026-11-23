#!/usr/bin/env python3
"""Wii MotionPlus for the emulated Wii Remotes (after patch_wiimote.py).

usage: patch_wiimote_mpls.py RUNTIME_DIR

Before: Sochi 2014 said "Das Wii MotionPlus-Zubehoer wurde von der Wii-Fernbedienung getrennt" after the player count:
it switches MotionPlus on (KPADEnableMpls(chan, mode 4 / 5 / 7)) and wants the KPAD extension type to become
5 (MotionPlus) / 6 (MotionPlus + Nunchuk) / 7 (+ Classic) and KPADGetMplsStatus to return the mode.
After: every Wii Remote has a MotionPlus (CAFE_WIIMOTE_MPLUS=0: none). KPADStatus 0xB0 = angular velocity
(rev/s), angle (rev), attitude (3 axis vectors) - from the host: a pad's tilt (RT + right stick) and shake, a real
remote's accelerometer and, if the kernel shows one, its "Motion Plus" device (CAFE_WIIMOTE_GYRO_UNITS = driver
units per degree/s, default 248; not checked against a real remote yet).
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


sub("include/cafe/input.h", """    bool pointer_valid = false;
    float pointer_x = 0.0f, pointer_y = 0.0f;  // -1..1, y down
};""", """    bool pointer_valid = false;
    float pointer_x = 0.0f, pointer_y = 0.0f;  // -1..1, y down
    // port/patch_wiimote_mpls.py: MotionPlus
    bool motion_plus = true;
    float roll = 0.0f, pitch = 0.0f;          // the remote's attitude, radians (roll right, nose up positive)
    float gyro[3] = {0.0f, 0.0f, 0.0f};       // rev/s about x (pitch), y (yaw), z (roll)
};""")

sub("src/os/input.cpp", """    WiimoteState wiimote{}; // port/patch_wiimote.py: this channel is a Wii Remote (wiimote.connected)""",
    """    WiimoteState wiimote{}; // port/patch_wiimote.py: this channel is a Wii Remote (wiimote.connected)
    uint8_t mpls_mode = 0;  // port/patch_wiimote_mpls.py: KPADEnableMpls' mode (4 alone, 5 Nunchuk, 7 Classic)
    float mp_angle[3] = {0.0f, 0.0f, 0.0f};
    std::chrono::steady_clock::time_point mp_last{};""")

sub("src/os/input.cpp", """uint8_t wiimote_type(const ProChannel& c) { return c.wiimote.nunchuk ? kExtNunchuk : kExtCore; }""",
    """uint8_t wiimote_type(const ProChannel& c) {
    if (c.wiimote.motion_plus && c.mpls_mode != 0) { // port/patch_wiimote_mpls.py: 5 MotionPlus, 6 + Nunchuk, 7 + Classic
        if (c.mpls_mode == 7) return 7;
        return c.mpls_mode == 5 && c.wiimote.nunchuk ? 6 : 5;
    }
    return c.wiimote.nunchuk ? kExtNunchuk : kExtCore;
}""")

sub("src/os/input.cpp", """    status->format = w.nunchuk ? 5 : 2; // NUNCHUK_ACC_DPD / CORE_ACC_DPD
    if (w.nunchuk) {""", """    status->format = w.nunchuk ? 5 : 2; // NUNCHUK_ACC_DPD / CORE_ACC_DPD
    if (status->extension_type >= 5 && status->extension_type <= 7) { // port/patch_wiimote_mpls.py
        const auto now = std::chrono::steady_clock::now();
        const float dt = c.mp_last == std::chrono::steady_clock::time_point{} ? 0.0f
                       : std::clamp(std::chrono::duration<float>(now - c.mp_last).count(), 0.0f, 0.1f);
        c.mp_last = now;
        for (int i = 0; i < 3; ++i) {
            c.mp_angle[i] += w.gyro[i] * dt;
            put_f(status, 0xB0 + 4 * i, w.gyro[i]);
            put_f(status, 0xBC + 4 * i, c.mp_angle[i]);
        }
        // attitude M = Rx(pitch) * Rz(-roll): its columns are the remote's x, y, z axes on the KPAD frame
        const float cp = std::cos(w.pitch), sp = std::sin(w.pitch), cr = std::cos(w.roll), sr = std::sin(w.roll);
        const float m[3][3] = {{cr, sr, 0.0f}, {-cp * sr, cp * cr, -sp}, {-sp * sr, sp * cr, cp}};
        for (int axis = 0; axis < 3; ++axis) {
            for (int k = 0; k < 3; ++k) put_f(status, 0xC8 + 12 * axis + 4 * k, m[k][axis]);
        }
    }
    if (w.nunchuk && (status->extension_type == kExtNunchuk || status->extension_type == 6)) {""")

sub("src/os/input.cpp", """int32_t KPADRead(int32_t channel, KPADStatus* status, uint32_t count) { // port/patch_wiimote.py""",
    """// port/patch_wiimote_mpls.py: MotionPlus on and off, and its state
void KPADEnableMpls(int32_t channel, uint32_t mode) {
    if (channel < 0 || channel >= wiimote::kChannels) return;
    std::lock_guard lock(g_input_mutex);
    static const bool trace = std::getenv("TTT2_TRACE_WIIMOTE") != nullptr;
    if (trace) std::fprintf(stderr, "wiimote: KPADEnableMpls(%d, %u)\\n", channel, mode);
    g_pro[channel].mpls_mode = static_cast<uint8_t>(mode);
    for (float& a : g_pro[channel].mp_angle) a = 0.0f;
}
void KPADDisableMpls(int32_t channel) { KPADEnableMpls(channel, 0); }
uint32_t KPADGetMplsStatus(int32_t channel) {
    if (channel < 0 || channel >= wiimote::kChannels) return 0;
    std::lock_guard lock(g_input_mutex);
    const ProChannel& c = g_pro[channel];
    return c.connected && c.wiimote.connected && c.wiimote.motion_plus ? c.mpls_mode : 0;
}
void KPADResetMpls(int32_t channel) {
    if (channel < 0 || channel >= wiimote::kChannels) return;
    std::lock_guard lock(g_input_mutex);
    for (float& a : g_pro[channel].mp_angle) a = 0.0f;
}
int32_t WPADIsMplsAttached(int32_t channel, be<uint32_t>* attached, uint32_t) {
    std::lock_guard lock(g_input_mutex);
    const bool on = channel >= 0 && channel < wiimote::kChannels && g_pro[channel].connected &&
                    g_pro[channel].wiimote.connected && g_pro[channel].wiimote.motion_plus;
    if (attached) *attached = on ? 1 : 0;
    return on ? 0 : kWpadNoController;
}
float KPADWorkMplsCalibration(int32_t) { return 0.0f; } // what is left to do: none (Sochi waits for |x| < 0.0001)

int32_t KPADRead(int32_t channel, KPADStatus* status, uint32_t count) { // port/patch_wiimote.py""")

sub("src/os/input.cpp", """CAFE_EXPORT(padscore, KPADRead, KPADRead); // port/patch_wiimote.py""",
    """CAFE_EXPORT(padscore, KPADRead, KPADRead); // port/patch_wiimote.py
CAFE_EXPORT(padscore, KPADEnableMpls, KPADEnableMpls); // port/patch_wiimote_mpls.py
CAFE_EXPORT(padscore, KPADDisableMpls, KPADDisableMpls);
CAFE_EXPORT(padscore, KPADGetMplsStatus, KPADGetMplsStatus);
CAFE_EXPORT(padscore, KPADResetMpls, KPADResetMpls);
CAFE_EXPORT(padscore, WPADIsMplsAttached, WPADIsMplsAttached);
CAFE_EXPORT(padscore, KPADWorkMplsCalibration, KPADWorkMplsCalibration);""")

# ------------------------------------------------------------- host side
sub("src/host/window.cpp", """    float pointer_x = 0.0f, pointer_y = 0.0f;
    double pointer_until = 0.0; // the pointer stays on the screen this long after the stick moved
};""", """    float pointer_x = 0.0f, pointer_y = 0.0f;
    double pointer_until = 0.0; // the pointer stays on the screen this long after the stick moved
    float last_roll = 0.0f, last_pitch = 0.0f; // port/patch_wiimote_mpls.py
};

// port/patch_wiimote_mpls.py: MotionPlus switch and the attitude from gravity (a remote at rest)
bool wiimote_mplus() {
    static const bool on = [] {
        const char* v = std::getenv("CAFE_WIIMOTE_MPLUS");
        return v == nullptr || *v != '0';
    }();
    return on;
}
void attitude_from_acc(os::WiimoteState& w) {
    w.pitch = std::asin(std::clamp(w.acc[2] / std::max(0.2f, std::sqrt(w.acc[0] * w.acc[0] + w.acc[1] * w.acc[1] + w.acc[2] * w.acc[2])), -1.0f, 1.0f));
    w.roll = std::atan2(w.acc[0], -w.acc[1]);
}""")

sub("src/host/window.cpp", """    // shaking: ~6 swings a second, 2.5 g up/down and back/forth
    if (SDL_GetGamepadButton(pad, SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER)) {
        m.shake_phase += dt * 6.0 * 2.0 * 3.14159265;""", """    // port/patch_wiimote_mpls.py: attitude and turn rate from the tilt
    w.motion_plus = wiimote_mplus();
    w.roll = roll;
    w.pitch = pitch;
    if (dt > 0.0f) {
        constexpr float kTurn = 1.0f / (2.0f * 3.14159265f);
        w.gyro[0] = (pitch - m.last_pitch) / dt * kTurn;
        w.gyro[2] = (roll - m.last_roll) / dt * kTurn;
    }
    m.last_roll = roll;
    m.last_pitch = pitch;
    // shaking: ~6 swings a second, 2.5 g up/down and back/forth
    if (SDL_GetGamepadButton(pad, SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER)) {
        w.gyro[0] += 1.5f * static_cast<float>(std::cos(m.shake_phase)); // the swing turns the remote too
        m.shake_phase += dt * 6.0 * 2.0 * 3.14159265;""")

# real remotes: the Motion Plus device
sub("src/host/window.cpp", """    int keys = -1, accel = -1, ir = -1, nunchuk = -1;""",
    """    int keys = -1, accel = -1, ir = -1, nunchuk = -1, mp = -1; // mp: port/patch_wiimote_mpls.py
    float mp_raw[3] = {0, 0, 0};""")
sub("src/host/window.cpp", """    for (int* fd : {&r.keys, &r.accel, &r.ir, &r.nunchuk}) {""",
    """    for (int* fd : {&r.keys, &r.accel, &r.ir, &r.nunchuk, &r.mp}) {""")
sub("src/host/window.cpp", """            for (int fd : {x.keys, x.accel, x.ir, x.nunchuk}) {""",
    """            for (int fd : {x.keys, x.accel, x.ir, x.nunchuk, x.mp}) {""")
sub("src/host/window.cpp", """            n.find("Balance") != std::string::npos || n.find("Classic") != std::string::npos ||
            n.find("Motion Plus") != std::string::npos) {""", """            n.find("Balance") != std::string::npos || n.find("Classic") != std::string::npos) {""")
sub("src/host/window.cpp", """                  : n.find(" IR") != std::string::npos ? &r->ir : n.find("Nunchuk") != std::string::npos ? &r->nunchuk : nullptr;""",
    """                  : n.find(" IR") != std::string::npos ? &r->ir : n.find("Nunchuk") != std::string::npos ? &r->nunchuk
                  : n.find("Motion Plus") != std::string::npos ? &r->mp : nullptr;""")
sub("src/host/window.cpp", """        // sensor axes (x left, y forward, z up; ~100 per g) -> KPAD frame (as Nintendo's KPAD converts them)""",
    """        drain(r.mp, [&](const input_event& e) { // port/patch_wiimote_mpls.py
            if (e.type == EV_ABS && e.code >= ABS_RX && e.code <= ABS_RZ) r.mp_raw[e.code - ABS_RX] = static_cast<float>(e.value);
        });
        // sensor axes (x left, y forward, z up; ~100 per g) -> KPAD frame (as Nintendo's KPAD converts them)""")
sub("src/host/window.cpp", """        w.connected = r.keys >= 0;
        if (!w.connected) close_remote(r);""", """        // port/patch_wiimote_mpls.py: attitude from gravity, turn rate from the Motion Plus (yaw, roll, pitch order)
        attitude_from_acc(w);
        w.motion_plus = wiimote_mplus();
        if (r.mp >= 0) {
            static const float units = [] {
                const char* v = std::getenv("CAFE_WIIMOTE_GYRO_UNITS");
                return v ? static_cast<float>(std::atof(v)) : 248.0f;
            }();
            const float to_rev = 1.0f / (units * 360.0f);
            w.gyro[1] = r.mp_raw[0] * to_rev;
            w.gyro[2] = r.mp_raw[1] * to_rev;
            w.gyro[0] = r.mp_raw[2] * to_rev;
        }
        w.connected = r.keys >= 0;
        if (!w.connected) close_remote(r);""")

# scripted tilt for unattended runs: "t:tilt=roll/pitch/seconds" (degrees) holds Wii Remote 0 (and its Nunchuk)
# at that attitude, e.g. "40:tilt=0/90/5" = both pointing up.
sub("src/os/input.cpp", """    std::vector<StickHold> touches; // port/patch_touch_ui.py: "t:touch=x/y/seconds\"""",
    """    std::vector<StickHold> touches; // port/patch_touch_ui.py: "t:touch=x/y/seconds"
    std::vector<StickHold> tilts;   // port/patch_wiimote_mpls.py: "t:tilt=roll/pitch/seconds" (degrees)""")
sub("src/os/input.cpp", """            if (name.rfind("touch=", 0) == 0) {""", """            if (name.rfind("tilt=", 0) == 0) { // port/patch_wiimote_mpls.py
                double roll = 0, pitch = 0, duration = 0.2;
                std::sscanf(name.c_str() + 5, "%lf/%lf/%lf", &roll, &pitch, &duration);
                script.tilts.push_back({std::atof(item.substr(0, colon).c_str()), roll, pitch, duration, script.anchors.size()});
            }
            if (name.rfind("touch=", 0) == 0) {""")
sub("src/os/input.cpp", """// port/patch_touch_ui.py: a scripted touch, if one is under way.""", """// port/patch_wiimote_mpls.py: a scripted tilt of Wii Remote 0 (radians), if one is under way.
bool scripted_tilt(float& roll, float& pitch) {
    static Script& script = load_script();
    if (script.tilts.empty()) return false;
    const double t = seconds_since(script.start);
    std::lock_guard lock(script.mutex);
    for (const StickHold& h : script.tilts) {
        const double start = script.starts[h.segment];
        if (start < 0.0 || t < start + h.at || t >= start + h.at + h.duration) continue;
        roll = static_cast<float>(h.x * 3.14159265 / 180.0);
        pitch = static_cast<float>(h.y * 3.14159265 / 180.0);
        return true;
    }
    return false;
}

// port/patch_touch_ui.py: a scripted touch, if one is under way.""")
sub("src/os/input.cpp", """        static int phase = 0;
        if (g_script_vpad & (vpad::kR | vpad::kZR)) {""", """        float roll = 0.0f, pitch = 0.0f; // port/patch_wiimote_mpls.py
        if (scripted_tilt(roll, pitch)) {
            const float a[3] = {std::sin(roll) * std::cos(pitch), -std::cos(roll) * std::cos(pitch), std::sin(pitch)};
            for (int i = 0; i < 3; ++i) w.acc[i] = w.nunchuk_acc[i] = a[i];
            w.roll = roll;
            w.pitch = pitch;
        }
        static int phase = 0;
        if (g_script_vpad & (vpad::kR | vpad::kZR)) {""")

# TTT2_TRACE_WIIMOTE=1: print MotionPlus switches and every change of a remote's buttons / extension type
sub("src/os/input.cpp", """    status->hold = w.buttons;
    status->trigger = w.buttons & ~c.wm_previous;""", """    static const bool trace = std::getenv("TTT2_TRACE_WIIMOTE") != nullptr;
    if (trace && (w.buttons != c.wm_previous || wiimote_type(c) != c.wm_traced_type)) {
        std::fprintf(stderr, "wiimote: ch %d hold %04X type %u acc %.2f %.2f %.2f\\n", static_cast<int>(&c - g_pro), w.buttons,
                     wiimote_type(c), w.acc[0], w.acc[1], w.acc[2]);
        c.wm_traced_type = wiimote_type(c);
    }
    status->hold = w.buttons;
    status->trigger = w.buttons & ~c.wm_previous;""")
sub("src/os/input.cpp", """    std::chrono::steady_clock::time_point mp_last{};""", """    std::chrono::steady_clock::time_point mp_last{};
    uint8_t wm_traced_type = 0xFF;""")

# A real pointer is never perfectly still. Sochi's menus (app::menu::Pointer) stay in "digital" (D-pad) mode until the
# pointer's screen position keeps changing for a few frames - an emulated, perfectly still pointer could never press
# its pointer-only buttons ("Zeige ... auf den Fernseher und druecke A"). Emulated remotes jitter by ~1 pixel.
sub("include/cafe/input.h", """    bool motion_plus = true;""", """    bool motion_plus = true;
    bool real_ir = false; // from a real IR camera (emulated pointers get a 1-pixel jitter)""")
sub("src/os/input.cpp", """    if (w.pointer_valid) {
        put_f(status, 0x20, w.pointer_x);""", """    if (w.pointer_valid && !w.real_ir) { // a hand is never perfectly still: +-1 pixel
        static uint32_t jitter = 0;
        w.pointer_x += (++jitter & 1) ? 0.003f : -0.003f;
    }
    if (w.pointer_valid) {
        put_f(status, 0x20, w.pointer_x);""")
sub("src/host/window.cpp", """        w.pointer_valid = dots > 0;
        if (dots > 0) {""", """        w.pointer_valid = dots > 0;
        w.real_ir = true;
        if (dots > 0) {""")
