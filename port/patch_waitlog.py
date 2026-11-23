"""TTT2_WAIT_LOG=1: once a second, where each frame's time goes.

Prints per shown frame (averaged over the second): the command thread's busy time, the retirement thread's
wait for the GPU and its write-back (tiling) time and bytes, and how long the title's threads waited on GPU
timestamps, vsync and flips. Measures why a title holds 30 instead of 60 frames a second.
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
SRC = os.path.join(ROOT, "runtime/src")


def patch(rel, old, new, count=1):
    path = os.path.join(SRC, rel)
    text = open(path, encoding="utf-8").read()
    if new in text:
        print("already:", rel)
        return
    if text.count(old) != count:
        sys.exit(f"{rel}: expected {count} of {old[:60]!r}, found {text.count(old)}")
    open(path, "w", encoding="utf-8", newline="").write(text.replace(old, new))
    print("patched:", rel)


patch("gpu/gpu.h", "namespace cafe::gpu {\n",
      "namespace cafe::gpu {\n\n"
      "// TTT2_WAIT_LOG: busy and wait times (nanoseconds) and write-back bytes, summed until the display\n"
      "// prints them once a second. Any thread.\n"
      "enum Stat { kStatCp, kStatGpuWait, kStatWriteBack, kStatWriteBackBytes, kStatGuestTs, kStatGuestVsync, kStatGuestFlip,\n"
      "            kStatCount };\n"
      "void add_stat(Stat stat, uint64_t value);\n"
      "uint64_t stat_now_ns();\n"
      "bool wait_log_enabled();\n")

patch("gpu/display.cpp", "namespace cafe::gpu {\nnamespace {\n",
      "namespace cafe::gpu {\n"
      "namespace {\n"
      "std::atomic<uint64_t> g_stats[kStatCount];\n"
      "uint64_t g_stat_flips = 0;\n"
      "uint64_t g_stat_vsyncs = 0;\n"
      "}\n\n"
      "bool wait_log_enabled() {\n"
      "    static const bool on = std::getenv(\"TTT2_WAIT_LOG\") != nullptr;\n"
      "    return on;\n"
      "}\n\n"
      "void add_stat(Stat stat, uint64_t value) {\n"
      "    if (wait_log_enabled()) g_stats[stat].fetch_add(value, std::memory_order_relaxed);\n"
      "}\n\n"
      "uint64_t stat_now_ns() {\n"
      "    return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(\n"
      "        std::chrono::steady_clock::now().time_since_epoch()).count());\n"
      "}\n\n"
      "namespace {\n")

# Once a second (60 blanks): frames shown and the per-frame averages.
patch("gpu/display.cpp",
      "    if (g_frames_ready > g_flips && g_vsyncs - g_last_flip_vsync >= std::max<uint32_t>(g_swap_interval, 1)) {\n"
      "        flip(now);\n"
      "    }\n",
      "    if (g_frames_ready > g_flips && g_vsyncs - g_last_flip_vsync >= std::max<uint32_t>(g_swap_interval, 1)) {\n"
      "        flip(now);\n"
      "    }\n"
      "    if (wait_log_enabled() && g_vsyncs - g_stat_vsyncs >= 60) {\n"
      "        const uint64_t frames = std::max<uint64_t>(g_flips - g_stat_flips, 1);\n"
      "        uint64_t s[kStatCount];\n"
      "        for (int i = 0; i < kStatCount; ++i) s[i] = g_stats[i].exchange(0);\n"
      "        const auto ms = [&](int i) { return static_cast<double>(s[i]) / 1e6 / static_cast<double>(frames); };\n"
      "        std::fprintf(stderr, \"waitlog: %llu frames/%llu blanks | per frame: cp %.2f ms, retire gpu-wait %.2f ms, \"\n"
      "                     \"write-back %.2f ms (%.0f KB) | title waits: timestamp %.2f ms, vsync %.2f ms, flip %.2f ms | swap interval %u\\n\",\n"
      "                     static_cast<unsigned long long>(g_flips - g_stat_flips),\n"
      "                     static_cast<unsigned long long>(g_vsyncs - g_stat_vsyncs), ms(kStatCp), ms(kStatGpuWait),\n"
      "                     ms(kStatWriteBack), static_cast<double>(s[kStatWriteBackBytes]) / 1024.0 / static_cast<double>(frames),\n"
      "                     ms(kStatGuestTs), ms(kStatGuestVsync), ms(kStatGuestFlip), g_swap_interval);\n"
      "        g_stat_flips = g_flips;\n"
      "        g_stat_vsyncs = g_vsyncs;\n"
      "    }\n")

patch("gpu/display.cpp",
      "    const uint64_t target = g_vsyncs + 1;\n"
      "    os::wait_until(lock, os::kWaitDisplay, [&] { return g_vsyncs >= target; });\n",
      "    const uint64_t target = g_vsyncs + 1;\n"
      "    const uint64_t t0 = stat_now_ns();\n"
      "    os::wait_until(lock, os::kWaitDisplay, [&] { return g_vsyncs >= target; });\n"
      "    add_stat(kStatGuestVsync, stat_now_ns() - t0);\n")

patch("gpu/display.cpp",
      "    const uint32_t target = g_flips + 1;\n"
      "    os::wait_until(lock, os::kWaitDisplay, [&] { return g_flips >= target; });\n",
      "    const uint32_t target = g_flips + 1;\n"
      "    const uint64_t t0 = stat_now_ns();\n"
      "    os::wait_until(lock, os::kWaitDisplay, [&] { return g_flips >= target; });\n"
      "    add_stat(kStatGuestFlip, stat_now_ns() - t0);\n")

patch("gpu/command_processor.cpp",
      "        g_backend->wait_for(r.done);\n"
      "        g_backend->retired(r.done);\n",
      "        const uint64_t t0 = stat_now_ns();\n"
      "        g_backend->wait_for(r.done);\n"
      "        const uint64_t t1 = stat_now_ns();\n"
      "        g_backend->retired(r.done);\n"
      "        add_stat(kStatGpuWait, t1 - t0);\n"
      "        add_stat(kStatWriteBack, stat_now_ns() - t1);\n")

patch("gpu/command_processor.cpp",
      "        execute(s.buffer, s.words, 0);\n"
      "        retire_later({Retirement::kTimestamp, g_backend->flush(), 0, s.timestamp});\n",
      "        const uint64_t t0 = stat_now_ns();\n"
      "        execute(s.buffer, s.words, 0);\n"
      "        retire_later({Retirement::kTimestamp, g_backend->flush(), 0, s.timestamp});\n"
      "        add_stat(kStatCp, stat_now_ns() - t0);\n")

patch("gpu/command_processor.cpp",
      "    os::KernelLock lock(os::kernel_mutex());\n"
      "    return os::wait_until_for(lock, os::kWaitGpu, timeout_ns, [&] { return g_retired >= timestamp; });\n",
      "    os::KernelLock lock(os::kernel_mutex());\n"
      "    const uint64_t t0 = stat_now_ns();\n"
      "    const bool done = os::wait_until_for(lock, os::kWaitGpu, timeout_ns, [&] { return g_retired >= timestamp; });\n"
      "    add_stat(kStatGuestTs, stat_now_ns() - t0);\n"
      "    return done;\n")

patch("gpu/vulkan/targets.cpp",
      "        tile(level, w.pitch, w.height, 0, 1, data);\n",
      "        tile(level, w.pitch, w.height, 0, 1, data);\n"
      "        add_stat(kStatWriteBackBytes, uint64_t{w.pitch} * w.height * w.bpp / 8);\n")
