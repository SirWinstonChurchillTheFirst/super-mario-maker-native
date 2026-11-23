#!/usr/bin/env python3
"""patch_cpu_profile.py RUNTIME_SRC_DIR (…/runtime/src) : a sampling profiler for the command processor thread.

Linux only (the console has no perf or gdb). TTT2_CPU_PROFILE=<seconds>: from TTT2_CPU_PROFILE_START seconds after
start-up (default 30) the "gpu" thread's instruction pointer is sampled every 1 ms of its CPU time for that many
seconds; then the 60 most frequent addresses are printed: "cpuprof: <count> <module>+0x<offset> <symbol>".
Symbolize the program's offsets in WSL: addr2line -f -C -e ~/wiiu/build-NAME/cafegame 0x<offset>."""
import sys

p = sys.argv[1] + "/gpu/command_processor.cpp"
s = open(p, encoding="utf-8").read()
if "patch_cpu_profile" in s:
    print("already applied"); sys.exit(0)
old_inc = "#include <vector>\n"
new_inc = """#include <vector>
#ifdef __linux__ // port/patch_cpu_profile.py
#include <algorithm>
#include <atomic>
#include <chrono>
#include <csignal>
#include <ctime>
#include <dlfcn.h>
#include <sys/syscall.h>
#include <ucontext.h>
#include <unistd.h>
#include <unordered_map>
#endif
"""
assert s.count(old_inc) == 1
s = s.replace(old_inc, new_inc, 1)

old_main = "void command_processor_main() {\n    pthread_setname_np(pthread_self(), \"gpu\");\n"
new_main = """#ifdef __linux__
// port/patch_cpu_profile.py: TTT2_CPU_PROFILE=<seconds> (TTT2_CPU_PROFILE_START=<seconds>, default 30).
namespace {
constexpr uint64_t kProfileSlots = 1u << 17;
std::atomic<uint64_t> g_profile_count{0};
uintptr_t g_profile_pc[kProfileSlots];
void profile_signal(int, siginfo_t*, void* context) {
    const auto* uc = static_cast<const ucontext_t*>(context);
    const uint64_t n = g_profile_count.fetch_add(1, std::memory_order_relaxed);
    if (n < kProfileSlots) g_profile_pc[n] = static_cast<uintptr_t>(uc->uc_mcontext.gregs[REG_RIP]);
}
void start_cpu_profile() {
    const char* v = std::getenv("TTT2_CPU_PROFILE");
    if (v == nullptr) return;
    const int seconds = std::max(1, std::atoi(v));
    const char* s = std::getenv("TTT2_CPU_PROFILE_START");
    const int start = s ? std::max(0, std::atoi(s)) : 30;
    struct sigaction sa {};
    sa.sa_sigaction = profile_signal;
    sa.sa_flags = SA_SIGINFO | SA_RESTART;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGPROF, &sa, nullptr);
    sigevent sev{};
    sev.sigev_notify = SIGEV_THREAD_ID;
    sev.sigev_signo = SIGPROF;
#ifdef sigev_notify_thread_id
    sev.sigev_notify_thread_id = static_cast<pid_t>(syscall(SYS_gettid));
#else
    sev._sigev_un._tid = static_cast<pid_t>(syscall(SYS_gettid));
#endif
    static timer_t timer;
    if (timer_create(CLOCK_THREAD_CPUTIME_ID, &sev, &timer) != 0) {
        std::fprintf(stderr, "cpuprof: timer_create failed\\n");
        return;
    }
    std::thread([seconds, start] {
        std::this_thread::sleep_for(std::chrono::seconds(start));
        itimerspec on{};
        on.it_interval.tv_nsec = 1000000;
        on.it_value.tv_nsec = 1000000;
        timer_settime(timer, 0, &on, nullptr);
        std::fprintf(stderr, "cpuprof: sampling the gpu thread for %d s\\n", seconds);
        std::this_thread::sleep_for(std::chrono::seconds(seconds));
        itimerspec off{};
        timer_settime(timer, 0, &off, nullptr);
        const uint64_t n = std::min<uint64_t>(g_profile_count.load(), kProfileSlots);
        std::unordered_map<uintptr_t, uint32_t> counts;
        for (uint64_t i = 0; i < n; ++i) ++counts[g_profile_pc[i]];
        std::vector<std::pair<uint32_t, uintptr_t>> top;
        for (const auto& [pc, c] : counts) top.push_back({c, pc});
        std::sort(top.begin(), top.end(), [](const auto& a, const auto& b) { return a.first > b.first; });
        std::fprintf(stderr, "cpuprof: %llu samples\\n", static_cast<unsigned long long>(n));
        for (size_t i = 0; i < top.size() && i < 60; ++i) {
            Dl_info info{};
            const uintptr_t pc = top[i].second;
            if (dladdr(reinterpret_cast<void*>(pc), &info) && info.dli_fname) {
                const char* slash = std::strrchr(info.dli_fname, '/');
                std::fprintf(stderr, "cpuprof: %u %s+0x%llx %s\\n", top[i].first, slash ? slash + 1 : info.dli_fname,
                             static_cast<unsigned long long>(pc - reinterpret_cast<uintptr_t>(info.dli_fbase)),
                             info.dli_sname ? info.dli_sname : "");
            } else {
                std::fprintf(stderr, "cpuprof: %u 0x%llx\\n", top[i].first, static_cast<unsigned long long>(pc));
            }
        }
    }).detach();
}
} // namespace
#endif

void command_processor_main() {
    pthread_setname_np(pthread_self(), "gpu");
#ifdef __linux__
    start_cpu_profile(); // port/patch_cpu_profile.py
#endif
"""
assert s.count(old_main) == 1
s = s.replace(old_main, new_main, 1)
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched", p)
