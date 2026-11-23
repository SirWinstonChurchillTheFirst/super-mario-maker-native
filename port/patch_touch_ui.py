#!/usr/bin/env python3
"""patch_touch_ui.py RUNTIME_SRC_DIR (…/runtime/src) : GamePad screen and touch input (Super Mario Maker).

- F9 (and, with CAFE_TOUCH_UI=1, a click of the LEFT stick) switches the window between the TV picture and the
  GamePad picture (scaled to the TV image; TTT2_SHOW_GAMEPAD=1 starts on it).
- On the GamePad picture: the mouse's left button touches where it points; on a controller the RIGHT stick moves a
  cursor and ZR or a click of the right stick touches (both are then not passed to the title). A cursor square is
  drawn into the shown picture (yellow while touching).
- VPADRead reports the touch in the calibrated 1280x720 space (VPADGetTPCalibratedPoint passes it through).
- TTT2_INPUT_SCRIPT gains "t:touch=x/y/seconds" (x, y = 0..1 of the GamePad screen) for unattended runs.
"""
import sys

src = sys.argv[1]


def patch(rel, pairs, marker="patch_touch_ui"):
    p = src + "/" + rel
    s = open(p, encoding="utf-8").read()
    if marker in s:
        print(rel + ": already applied")
        return
    for old, new in pairs:
        assert s.count(old) == 1, rel + ": pattern not found or not unique: " + old[:60]
        s = s.replace(old, new)
    open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("patched", p)


# ---------------------------------------------------------------- input.h
patch("../include/cafe/input.h", [(
    "    float right_x, right_y;\n};",
    "    float right_x, right_y;\n"
    "    bool touch = false;                   // port/patch_touch_ui.py: the GamePad's touch screen\n"
    "    float touch_x = 0.0f, touch_y = 0.0f; // 0..1 of the screen\n"
    "};")])

# ---------------------------------------------------------------- os/input.cpp
patch("os/input.cpp", [
    ("#include <array>\n", "#include <algorithm> // port/patch_touch_ui.py\n#include <array>\n"),
    ("    std::vector<StickHold> sticks;\n",
     "    std::vector<StickHold> sticks;\n"
     "    std::vector<StickHold> touches; // port/patch_touch_ui.py: \"t:touch=x/y/seconds\"\n"),
    ("            const size_t equals = name.find('=');\n",
     "            if (name.rfind(\"touch=\", 0) == 0) {\n"
     "                double x = 0.5, y = 0.5, duration = 0.2;\n"
     "                std::sscanf(name.c_str() + 6, \"%lf/%lf/%lf\", &x, &y, &duration);\n"
     "                script.touches.push_back({std::atof(item.substr(0, colon).c_str()), x, y, duration, script.anchors.size()});\n"
     "            }\n"
     "            const size_t equals = name.find('=');\n"),
    ("// ------------------------------------------------------------ the + chord\n",
     "// port/patch_touch_ui.py: a scripted touch, if one is under way.\n"
     "bool scripted_touch(float& x, float& y) {\n"
     "    static Script& script = load_script();\n"
     "    if (script.touches.empty()) return false;\n"
     "    const double t = seconds_since(script.start);\n"
     "    std::lock_guard lock(script.mutex);\n"
     "    for (const StickHold& h : script.touches) {\n"
     "        const double start = script.starts[h.segment];\n"
     "        if (start < 0.0 || t < start + h.at || t >= start + h.at + h.duration) continue;\n"
     "        x = static_cast<float>(h.x);\n"
     "        y = static_cast<float>(h.y);\n"
     "        return true;\n"
     "    }\n"
     "    return false;\n"
     "}\n\n"
     "// ------------------------------------------------------------ the + chord\n"),
    ("    status->right_stick = {pad.right_x, pad.right_y};\n",
     "    status->right_stick = {pad.right_x, pad.right_y};\n"
     "    { // port/patch_touch_ui.py: touch in the calibrated 1280x720 space\n"
     "        float tx = pad.touch_x, ty = pad.touch_y;\n"
     "        const bool touched = scripted_touch(tx, ty) || pad.touch;\n"
     "        if (touched) {\n"
     "            const TouchData t{static_cast<uint16_t>(std::clamp(tx, 0.0f, 1.0f) * 1279.0f + 0.5f),\n"
     "                              static_cast<uint16_t>(std::clamp(ty, 0.0f, 1.0f) * 719.0f + 0.5f), uint16_t{1}, uint16_t{0}};\n"
     "            status->touch = t;\n"
     "            status->touch_processed1 = t;\n"
     "            status->touch_processed2 = t;\n"
     "        }\n"
     "    }\n"),
])

# ---------------------------------------------------------------- host/window.h
patch("host/window.h", [(
    "bool window_open();\n",
    "bool window_open();\n"
    "// port/patch_touch_ui.py: whether the window shows the GamePad picture, and the touch cursor (0..1).\n"
    "struct GamePadView {\n"
    "    bool show;\n"
    "    float x, y;\n"
    "    bool touch;\n"
    "};\n"
    "GamePadView gamepad_view();\n")])

# ---------------------------------------------------------------- host/window.cpp
patch("host/window.cpp", [
    ("OverlayHooks g_overlay;\n",
     "// port/patch_touch_ui.py: GamePad picture and touch cursor.\n"
     "std::atomic<bool> g_show_drc{std::getenv(\"TTT2_SHOW_GAMEPAD\") != nullptr};\n"
     "std::atomic<float> g_cursor_x{0.5f}, g_cursor_y{0.5f};\n"
     "std::atomic<bool> g_cursor_touch{false};\n"
     "bool g_mouse_down = false;\n"
     "bool g_mouse_seen = false; // a real click happened: from then on mouse motion moves the cursor\n"
     "const bool g_touch_ui = std::getenv(\"CAFE_TOUCH_UI\") != nullptr;\n"
     "\n"
     "// A window point (SDL window coordinates) -> 0..1 of the letterboxed 16:9 picture; false outside it.\n"
     "bool picture_point(float wx, float wy, float& x, float& y) {\n"
     "    int ww = 0, wh = 0;\n"
     "    if (g_window == nullptr || !SDL_GetWindowSize(g_window, &ww, &wh) || ww <= 0 || wh <= 0) return false;\n"
     "    const float scale = std::min(ww / 16.0f, wh / 9.0f);\n"
     "    const float w = 16.0f * scale, h = 9.0f * scale;\n"
     "    x = (wx - (ww - w) * 0.5f) / w;\n"
     "    y = (wy - (wh - h) * 0.5f) / h;\n"
     "    return x >= 0.0f && x <= 1.0f && y >= 0.0f && y <= 1.0f;\n"
     "}\n"
     "\n"
     "OverlayHooks g_overlay;\n"),
    ("    SDL_free(ids);\n    for (int c = 0; pros && c < os::pro::kChannels; ++c) netplay::remote_pad(c, channels[c]);\n",
     "    SDL_free(ids);\n"
     "    { // port/patch_touch_ui.py: on the GamePad picture the right stick moves the touch cursor, ZR / R3 touch\n"
     "        static auto last = std::chrono::steady_clock::now();\n"
     "        const auto now = std::chrono::steady_clock::now();\n"
     "        const float dt = std::clamp(std::chrono::duration<float>(now - last).count(), 0.0f, 0.05f);\n"
     "        last = now;\n"
     "        if (g_touch_ui) state.buttons &= ~os::vpad::kStickL; // the screen switch\n"
     "        if (g_show_drc.load()) {\n"
     "            const auto curve = [](float v) { return v * std::fabs(v); };\n"
     "            const float speed = 0.7f; // screen widths per second at full tilt\n"
     "            g_cursor_x = std::clamp(g_cursor_x.load() + curve(state.right_x) * speed * dt, 0.0f, 1.0f);\n"
     "            g_cursor_y = std::clamp(g_cursor_y.load() - curve(state.right_y) * speed * dt * 16.0f / 9.0f, 0.0f, 1.0f);\n"
     "            const bool pad_touch = (state.buttons & (os::vpad::kZR | os::vpad::kStickR)) != 0;\n"
     "            state.buttons &= ~(os::vpad::kZR | os::vpad::kStickR);\n"
     "            state.right_x = state.right_y = 0.0f;\n"
     "            state.touch = pad_touch || g_mouse_down;\n"
     "            state.touch_x = g_cursor_x.load();\n"
     "            state.touch_y = g_cursor_y.load();\n"
     "        }\n"
     "        g_cursor_touch = state.touch;\n"
     "    }\n"
     "    for (int c = 0; pros && c < os::pro::kChannels; ++c) netplay::remote_pad(c, channels[c]);\n"),
    ("                if (event.key.scancode == SDL_SCANCODE_F10 && !event.key.repeat) os::request_profile();\n",
     "                if (event.key.scancode == SDL_SCANCODE_F10 && !event.key.repeat) os::request_profile();\n"
     "                // F9: TV or GamePad picture (port/patch_touch_ui.py).\n"
     "                if (event.key.scancode == SDL_SCANCODE_F9 && !event.key.repeat) g_show_drc = !g_show_drc.load();\n"),
    ("                if (other != SDL_GAMEPAD_BUTTON_INVALID && pad && SDL_GetGamepadButton(pad, other)) gpu::request_frame_trace();\n",
     "                if (other != SDL_GAMEPAD_BUTTON_INVALID && pad && SDL_GetGamepadButton(pad, other)) gpu::request_frame_trace();\n"
     "                // port/patch_touch_ui.py: CAFE_TOUCH_UI=1 - a left stick click switches TV / GamePad picture.\n"
     "                else if (g_touch_ui && event.gbutton.button == SDL_GAMEPAD_BUTTON_LEFT_STICK) g_show_drc = !g_show_drc.load();\n"),
    ("            default: break;\n            }\n        }\n        if (g_quit_requested) return false;\n",
     "            case SDL_EVENT_MOUSE_MOTION: { // port/patch_touch_ui.py\n"
     "                float x, y;\n"
     "                if (g_mouse_seen && g_show_drc.load() && picture_point(event.motion.x, event.motion.y, x, y)) {\n"
     "                    g_cursor_x = x;\n"
     "                    g_cursor_y = y;\n"
     "                }\n"
     "                break;\n"
     "            }\n"
     "            case SDL_EVENT_MOUSE_BUTTON_DOWN:\n"
     "            case SDL_EVENT_MOUSE_BUTTON_UP: {\n"
     "                if (event.button.button != SDL_BUTTON_LEFT) break;\n"
     "                float x, y;\n"
     "                const bool inside = picture_point(event.button.x, event.button.y, x, y);\n"
     "                if (event.type == SDL_EVENT_MOUSE_BUTTON_UP) {\n"
     "                    g_mouse_down = false;\n"
     "                } else if (g_show_drc.load() && inside) {\n"
     "                    g_cursor_x = x;\n"
     "                    g_cursor_y = y;\n"
     "                    g_mouse_down = true;\n"
     "                    g_mouse_seen = true;\n"
     "                }\n"
     "                break;\n"
     "            }\n"
     "            default: break;\n            }\n        }\n        if (g_quit_requested) return false;\n"),
    ("std::vector<const char*> vulkan_instance_extensions() {\n",
     "// port/patch_touch_ui.py\n"
     "GamePadView gamepad_view() { return {g_show_drc.load(), g_cursor_x.load(), g_cursor_y.load(), g_cursor_touch.load()}; }\n"
     "\n"
     "std::vector<const char*> vulkan_instance_extensions() {\n"),
])

# ---------------------------------------------------------------- gpu/vulkan/renderer.cpp
patch("gpu/vulkan/renderer.cpp", [(
    "    scan_valid_[index] = true;\n    profile_mark(\"copy to scan buffer\", t->address, width, height);\n",
    "    scan_valid_[index] = true;\n"
    "    // port/patch_touch_ui.py: the GamePad picture shown instead of the TV's (scaled into the TV scan image), with\n"
    "    // the touch cursor. The title copies the TV first, the GamePad second, then swaps.\n"
    "    if (index == 1 && scan_[0].image != VK_NULL_HANDLE) {\n"
    "        const host::GamePadView view = host::gamepad_view();\n"
    "        if (view.show) {\n"
    "            VkImageBlit blit{};\n"
    "            blit.srcSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};\n"
    "            blit.dstSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};\n"
    "            blit.srcOffsets[1] = {static_cast<int32_t>(width), static_cast<int32_t>(height), 1};\n"
    "            blit.dstOffsets[1] = {static_cast<int32_t>(scan_[0].width), static_cast<int32_t>(scan_[0].height), 1};\n"
    "            vkCmdBlitImage(cmd(), t->image.image, VK_IMAGE_LAYOUT_GENERAL, scan_[0].image, VK_IMAGE_LAYOUT_GENERAL, 1, &blit,\n"
    "                           VK_FILTER_LINEAR);\n"
    "            barrier();\n"
    "            const VkFormat f = scan_[0].format;\n"
    "            const bool rgba8 = f == VK_FORMAT_R8G8B8A8_UNORM || f == VK_FORMAT_R8G8B8A8_SRGB || f == VK_FORMAT_B8G8R8A8_UNORM ||\n"
    "                               f == VK_FORMAT_B8G8R8A8_SRGB;\n"
    "            const uint32_t n = std::max<uint32_t>(8, scan_[0].height / 45); // the cursor square, 16 px at 720 rows\n"
    "            if (rgba8 && scan_[0].width > n && scan_[0].height > n) {\n"
    "                const bool bgra = f == VK_FORMAT_B8G8R8A8_UNORM || f == VK_FORMAT_B8G8R8A8_SRGB;\n"
    "                // yellow while touching, else white; black border (bytes R,G,B,A or B,G,R,A)\n"
    "                const uint32_t fill_rgba = view.touch ? (bgra ? 0xFFFFDC00u : 0xFF00DCFFu) : 0xFFFFFFFFu;\n"
    "                VkDeviceSize offset = 0;\n"
    "                uint8_t* p = upload(VkDeviceSize{n} * n * 4, 16, offset);\n"
    "                for (uint32_t yy = 0; yy < n; ++yy) {\n"
    "                    for (uint32_t xx = 0; xx < n; ++xx) {\n"
    "                        const bool edge = xx < 2 || yy < 2 || xx >= n - 2 || yy >= n - 2;\n"
    "                        const uint32_t v = edge ? 0xFF000000u : fill_rgba;\n"
    "                        std::memcpy(p + (yy * n + xx) * 4, &v, 4);\n"
    "                    }\n"
    "                }\n"
    "                const int32_t cx = static_cast<int32_t>(view.x * scan_[0].width) - static_cast<int32_t>(n / 2);\n"
    "                const int32_t cy = static_cast<int32_t>(view.y * scan_[0].height) - static_cast<int32_t>(n / 2);\n"
    "                VkBufferImageCopy region{};\n"
    "                region.bufferOffset = offset;\n"
    "                region.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};\n"
    "                region.imageOffset = {std::clamp<int32_t>(cx, 0, static_cast<int32_t>(scan_[0].width - n)),\n"
    "                                      std::clamp<int32_t>(cy, 0, static_cast<int32_t>(scan_[0].height - n)), 0};\n"
    "                region.imageExtent = {n, n, 1};\n"
    "                vkCmdCopyBufferToImage(cmd(), ring_.buffer(), scan_[0].image, VK_IMAGE_LAYOUT_GENERAL, 1, &region);\n"
    "                barrier();\n"
    "            }\n"
    "        }\n"
    "    }\n"
    "    profile_mark(\"copy to scan buffer\", t->address, width, height);\n")])
