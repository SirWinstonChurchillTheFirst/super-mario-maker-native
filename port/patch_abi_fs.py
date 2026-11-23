#!/usr/bin/env python3
"""One-off edits of the Smash4PC runtime (kept for the record; the result is in port/upstream-local.patch):
  include/cafe/export.h: the ninth and later integer arguments of a system function come from the caller's stack
                         (PowerPC EABI), not from r11 on.
  src/os/fs.cpp:         FSGetPosFile, FSIsEof, FSGetVolumeState and the async read/write/position calls.
usage: patch_abi_fs.py <smash4/runtime>"""
import sys

root = sys.argv[1]

p = root + "/include/cafe/export.h"
s = open(p).read()
a = """struct Cursor {
    int gpr = 3;
    int fpr = 1;
};
"""
b = """struct Cursor {
    int gpr = 3;
    int fpr = 1;
    int stack = 0; // words taken from the caller's frame
};

// The next integer argument word: r3..r10, then the caller's frame from 8(r1) on (PowerPC EABI).
inline uint32_t next_word(PPCContext& ctx, Cursor& cursor) {
    if (cursor.gpr <= 10) return ctx.r[cursor.gpr++];
    return *guest<be<uint32_t>>(ctx.r[1] + 8 + 4 * static_cast<uint32_t>(cursor.stack++));
}
"""
assert a in s
s = s.replace(a, b)
a = """        return GuestAddress{ctx.r[cursor.gpr++]};
    } else if constexpr (std::is_pointer_v<T>) {
        return guest<std::remove_pointer_t<T>>(ctx.r[cursor.gpr++]);"""
b = """        return GuestAddress{next_word(ctx, cursor)};
    } else if constexpr (std::is_pointer_v<T>) {
        return guest<std::remove_pointer_t<T>>(next_word(ctx, cursor));"""
assert a in s
s = s.replace(a, b)
a = """        if ((cursor.gpr & 1) == 0) ++cursor.gpr;
        const uint64_t v = (uint64_t{ctx.r[cursor.gpr]} << 32) | ctx.r[cursor.gpr + 1];
        cursor.gpr += 2;
        return static_cast<T>(v);"""
b = """        // A 64-bit value takes an odd-even register pair, or (when none is left) an 8-aligned pair on the stack.
        if ((cursor.gpr & 1) == 0) ++cursor.gpr;
        if (cursor.gpr > 9) {
            cursor.gpr = 11;
            cursor.stack += cursor.stack & 1;
        }
        const uint64_t high = next_word(ctx, cursor);
        const uint64_t v = (high << 32) | next_word(ctx, cursor);
        return static_cast<T>(v);"""
assert a in s
s = s.replace(a, b)
a = """        return static_cast<T>(ctx.r[cursor.gpr++]);
    }
}"""
b = """        return static_cast<T>(next_word(ctx, cursor));
    }
}"""
assert a in s
s = s.replace(a, b)
open(p, "w").write(s)

p = root + "/src/os/fs.cpp"
s = open(p).read()
anchor = "// The FSAsyncResult of a completion message from a queue: the message's data word."
assert anchor in s and "FSGetPosFile" not in s
new = """int32_t FSGetPosFile(GuestAddress client, GuestAddress, int32_t handle, be<uint32_t>* position, uint32_t mask) {
    uint64_t at = 0;
    const auto status = vfs::tell_file(handle, at);
    if (status == vfs::kOk && position) *position = static_cast<uint32_t>(at);
    return finish(client, status, mask, "tell");
}
// FS_STATUS_END at the end of the file, else FS_STATUS_OK.
int32_t FSIsEof(GuestAddress client, GuestAddress, int32_t handle, uint32_t mask) {
    uint64_t at = 0;
    vfs::Stat stat;
    auto status = vfs::tell_file(handle, at);
    if (status == vfs::kOk) status = vfs::stat_file(handle, stat);
    if (status == vfs::kOk && at >= stat.size) status = vfs::kEnd;
    return finish(client, status, mask, "eof");
}
// FSVolumeState: 1 = ready (the game's volume is always there).
int32_t FSGetVolumeState(GuestAddress) { return 1; }

int32_t FSReadFileAsync(PPCContext& ctx, GuestAddress client, GuestAddress block, uint8_t* destination, uint32_t size,
                        uint32_t count, int32_t handle, uint32_t flags, uint32_t mask, const be<uint32_t>* async) {
    return complete_async(ctx, client, block, FSReadFile(client, block, destination, size, count, handle, flags, mask), async);
}
int32_t FSReadFileWithPosAsync(PPCContext& ctx, GuestAddress client, GuestAddress block, uint8_t* destination,
                               uint32_t size, uint32_t count, uint32_t position, int32_t handle, uint32_t flags,
                               uint32_t mask, const be<uint32_t>* async) {
    return complete_async(ctx, client, block,
                          FSReadFileWithPos(client, block, destination, size, count, position, handle, flags, mask), async);
}
int32_t FSWriteFileAsync(PPCContext& ctx, GuestAddress client, GuestAddress block, const uint8_t* source, uint32_t size,
                         uint32_t count, int32_t handle, uint32_t flags, uint32_t mask, const be<uint32_t>* async) {
    return complete_async(ctx, client, block, FSWriteFile(client, block, source, size, count, handle, flags, mask), async);
}
int32_t FSWriteFileWithPosAsync(PPCContext& ctx, GuestAddress client, GuestAddress block, const uint8_t* source,
                                uint32_t size, uint32_t count, uint32_t position, int32_t handle, uint32_t flags,
                                uint32_t mask, const be<uint32_t>* async) {
    return complete_async(ctx, client, block,
                          FSWriteFileWithPos(client, block, source, size, count, position, handle, flags, mask), async);
}
int32_t FSGetPosFileAsync(PPCContext& ctx, GuestAddress client, GuestAddress block, int32_t handle,
                          be<uint32_t>* position, uint32_t mask, const be<uint32_t>* async) {
    return complete_async(ctx, client, block, FSGetPosFile(client, block, handle, position, mask), async);
}
int32_t FSSetPosFileAsync(PPCContext& ctx, GuestAddress client, GuestAddress block, int32_t handle, uint32_t position,
                          uint32_t mask, const be<uint32_t>* async) {
    return complete_async(ctx, client, block, FSSetPosFile(client, block, handle, position, mask), async);
}
int32_t FSGetStatFileAsync(PPCContext& ctx, GuestAddress client, GuestAddress block, int32_t handle, uint8_t* out,
                           uint32_t mask, const be<uint32_t>* async) {
    return complete_async(ctx, client, block, FSGetStatFile(client, block, handle, out, mask), async);
}
"""
s = s.replace(anchor, new + anchor)
anchor = "CAFE_EXPORT(coreinit, FSGetAsyncResult, FSGetAsyncResult);"
assert anchor in s
names = ["FSGetPosFile", "FSIsEof", "FSGetVolumeState", "FSReadFileAsync", "FSReadFileWithPosAsync", "FSWriteFileAsync",
         "FSWriteFileWithPosAsync", "FSGetPosFileAsync", "FSSetPosFileAsync", "FSGetStatFileAsync"]
s = s.replace(anchor, anchor + "\n" + "\n".join("CAFE_EXPORT(coreinit, %s, %s);" % (n, n) for n in names))
open(p, "w").write(s)
