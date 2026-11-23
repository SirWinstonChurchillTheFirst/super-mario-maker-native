#!/usr/bin/env python3
"""patch_fs_async_defer.py RUNTIME_SRC_DIR (…/runtime/src)

FS*Async with a callback: the runtime ran the command and called the title's callback INSIDE the FS*Async call, on the
caller's thread, before the call returned. On the console the callback comes later from another thread. Mario &
Sonic Sochi 2014 counts a load as pending after FSOpenFileAsync returns and the callback counts it done: called
first, the count never reached zero and the boot job waited forever (no picture, the display flag never cleared).
Callbacks now run on the runtime's "cafe system" guest thread after the call returned. TTT2_FS_SYNC_CALLBACK=1 = old."""
import sys

src = sys.argv[1]


def patch(rel, pairs):
    p = src + "/" + rel
    s = open(p, encoding="utf-8").read()
    if "patch_fs_async_defer" in s:
        print(rel + ": already applied")
        return
    for old, new in pairs:
        assert s.count(old) == 1, rel + ": pattern not found or not unique: " + old[:80]
        s = s.replace(old, new)
    open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("patched", p)


patch("os/thread.cpp", [(
    "Thread* create_internal_thread(const char* name, int core) {\n",
    "// port/patch_fs_async_defer.py: guest work for the \"cafe system\" thread (FS async callbacks).\n"
    "void defer_guest_work(std::function<void(PPCContext&)> work) {\n"
    "    KernelLock lock(g_kernel);\n"
    "    g_deferred.push_back(std::move(work));\n"
    "    wake(kWaitDeferred);\n"
    "}\n"
    "\n"
    "Thread* create_internal_thread(const char* name, int core) {\n")])

p = src + "/os/kernel.h"
s = open(p, encoding="utf-8").read()
if "defer_guest_work" not in s:
    anchor = "std::mutex& kernel_mutex();"
    assert s.count(anchor) == 1, "kernel.h anchor"
    s = s.replace(anchor, anchor + "\n// port/patch_fs_async_defer.py: runs `work` on the runtime's system guest thread, later.\n"
                  "void defer_guest_work(std::function<void(PPCContext&)> work);", 1)
    if "#include <functional>" not in s:
        s = s.replace("#include", "#include <functional>\n#include", 1)
    open(p, "w", encoding="utf-8", newline="\n").write(s)
    print("patched", p)

patch("os/fs.cpp", [(
    "        call_guest(ctx, callback, {client.value, block.value, static_cast<uint32_t>(status), param});\n",
    "        // port/patch_fs_async_defer.py: later, from another thread, as the console does.\n"
    "        static const bool sync = std::getenv(\"TTT2_FS_SYNC_CALLBACK\") != nullptr;\n"
    "        if (sync) {\n"
    "            call_guest(ctx, callback, {client.value, block.value, static_cast<uint32_t>(status), param});\n"
    "        } else {\n"
    "            const uint32_t c = client.value, b = block.value, s = static_cast<uint32_t>(status);\n"
    "            defer_guest_work([callback, c, b, s, param](PPCContext& context) {\n"
    "                call_guest(context, callback, {c, b, s, param});\n"
    "            });\n"
    "        }\n")])
