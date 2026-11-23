"""Write-backs that would overwrite newer CPU data are dropped; switches to study write-backs (Mario Tennis).

The runtime copies small render targets back into guest memory when the GPU work has RETIRED (targets.cpp), which can
be a frame or more after the draw. On the console's GPU the target is in guest memory right when it is drawn. If the
title reuses that memory for CPU data in between (a per-frame scratch pool), the late write-back overwrites the newer
CPU data. Mario Tennis Ultra Smash showed its match scene turned (rect passes 90 degrees each) depending on write-back
timing (PC uncached vs cached memory, console: always turned), which fits this race.
Guard: when a write-back is queued (submission), the guest bytes it will cover are kept; when it retires, the bytes
are compared first. Changed = somebody wrote the memory after the draw was submitted -> the write-back is skipped
(logged with the address, first 20 times). A write-back that retires refreshes the kept bytes of later queued ones of
the same address, so a target written every frame does not skip itself.
Switches: TTT2_WRITEBACK_GUARD=0 turns the guard off, TTT2_NO_WRITEBACK=1 writes nothing back (A/B),
TTT2_WRITEBACK_LOG=1 logs every target address the first time it is written back.
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
SRC = os.path.join(ROOT, "runtime/src/gpu/vulkan")


def patch(rel, pairs):
    path = os.path.join(SRC, rel)
    text = open(path, encoding="utf-8").read()
    if "patch_writeback_guard" in text:
        print("already:", rel)
        return
    for old, new in pairs:
        if text.count(old) != 1:
            sys.exit(f"{rel}: anchor not found once: {old[:70]!r}")
        text = text.replace(old, new)
    open(path, "w", encoding="utf-8", newline="").write(text)
    print("patched:", rel)


patch("renderer.h", [(
    "        uint32_t address, base_reg, tile_mode, bpp, pitch, height;\n    };\n",
    "        uint32_t address, base_reg, tile_mode, bpp, pitch, height;\n"
    "        std::vector<uint8_t> before; // guest bytes when queued (port/patch_writeback_guard.py)\n"
    "    };\n")])

patch("targets.cpp", [
    ("void Renderer::queue_write_back(Target* t) {\n"
     "    if (!t->write_back || replaying_ || t->write_back_queued) return;\n",
     "void Renderer::queue_write_back(Target* t) {\n"
     "    static const bool none = std::getenv(\"TTT2_NO_WRITEBACK\") != nullptr; // port/patch_writeback_guard.py\n"
     "    if (none) return;\n"
     "    if (!t->write_back || replaying_ || t->write_back_queued) return;\n"),
    ("        write_backs_.push_back({value, staging, t->address, t->base_reg, t->tile_mode, bytes * 8, t->pitch, t->height});\n",
     "        write_backs_.push_back({value, staging, t->address, t->base_reg, t->tile_mode, bytes * 8, t->pitch, t->height, {}});\n"
     "        {\n"
     "            static const bool guard = [] {\n"
     "                const char* v = std::getenv(\"TTT2_WRITEBACK_GUARD\");\n"
     "                return v == nullptr || *v != '0';\n"
     "            }();\n"
     "            static const bool log = std::getenv(\"TTT2_WRITEBACK_LOG\") != nullptr;\n"
     "            const uint32_t n = t->pitch * t->height * bytes;\n"
     "            if (guard) write_backs_.back().before.assign(guest_pointer(t->address), guest_pointer(t->address) + n);\n"
     "            static std::set<uint32_t> seen;\n"
     "            if (log && seen.insert(t->address).second) {\n"
     "                std::fprintf(stderr, \"ttt2: write-back: 0x%08X fmt 0x%03X %ux%u tile %u (%u bytes)\\n\", t->address,\n"
     "                             t->format, t->pitch, t->height, t->tile_mode, n);\n"
     "            }\n"
     "        }\n"),
    ("        TiledLevel level{};\n        level.data = guest_pointer(w.address);\n",
     "        const uint32_t n = w.pitch * w.height * (w.bpp / 8);\n"
     "        if (!w.before.empty() && std::memcmp(w.before.data(), guest_pointer(w.address), n) != 0) {\n"
     "            // Written since the draw was submitted: the newer data stays (port/patch_writeback_guard.py).\n"
     "            static std::atomic<uint32_t> skipped{0};\n"
     "            const uint32_t k = skipped.fetch_add(1);\n"
     "            if (k < 20 || (k & (k - 1)) == 0) {\n"
     "                std::fprintf(stderr, \"ttt2: write-back of 0x%08X %ux%u skipped: guest memory changed since the draw (%u so far)\\n\",\n"
     "                             w.address, w.pitch, w.height, k + 1);\n"
     "            }\n"
     "            std::lock_guard lock(write_back_mutex_);\n"
     "            write_back_free_.push_back(w.staging);\n"
     "            continue;\n"
     "        }\n"
     "        TiledLevel level{};\n        level.data = guest_pointer(w.address);\n"),
    ("        add_stat(kStatWriteBackBytes, uint64_t{w.pitch} * w.height * w.bpp / 8);\n"
     "        std::lock_guard lock(write_back_mutex_);\n"
     "        write_back_free_.push_back(w.staging);\n",
     "        add_stat(kStatWriteBackBytes, uint64_t{w.pitch} * w.height * w.bpp / 8);\n"
     "        std::lock_guard lock(write_back_mutex_);\n"
     "        write_back_free_.push_back(w.staging);\n"
     "        // Later queued write-backs of the same place compare against what this one wrote.\n"
     "        for (WriteBack& later : write_backs_) {\n"
     "            if (later.address == w.address && !later.before.empty() && later.before.size() == n) {\n"
     "                std::memcpy(later.before.data(), guest_pointer(w.address), n);\n"
     "            }\n"
     "        }\n"),
])

path = os.path.join(SRC, "targets.cpp")
text = open(path, encoding="utf-8").read()
for inc in ("#include <set>\n", "#include <atomic>\n", "#include <cstring>\n", "#include <cstdlib>\n"):
    if inc not in text:
        first = text.index("#include <")
        text = text[:first] + inc + text[first:]
open(path, "w", encoding="utf-8", newline="").write(text)
