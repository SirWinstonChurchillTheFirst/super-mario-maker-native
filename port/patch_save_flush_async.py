#!/usr/bin/env python3
"""patch_save_flush_async.py RUNTIME_SRC_DIR : nn_save SAVEFlushQuotaAsync (Sochi 2014 after creating its save):
saves are written through at once, so it completes at once like SAVEFlushQuota, through the async path."""
import sys
p = sys.argv[1] + "/os/fs.cpp"
s = open(p, encoding="utf-8").read()
if "patch_save_flush_async" in s:
    print("already applied"); sys.exit(0)
old = "CAFE_EXPORT(nn_save, SAVEOpenFileAsync, SAVEOpenFileAsync);\n"
new = old + """// port/patch_save_flush_async.py
static int32_t SAVEFlushQuotaAsync(PPCContext& ctx, GuestAddress client, GuestAddress block, uint8_t, uint32_t,
                                   const be<uint32_t>* async) {
    return complete_async(ctx, client, block, 0, async);
}
CAFE_EXPORT(nn_save, SAVEFlushQuotaAsync, SAVEFlushQuotaAsync);
"""
assert s.count(old) == 1
open(p, "w", encoding="utf-8", newline="\n").write(s.replace(old, new))
print("patched", p)
