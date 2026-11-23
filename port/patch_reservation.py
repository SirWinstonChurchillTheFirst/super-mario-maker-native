#!/usr/bin/env python3
"""patch_reservation.py SMASH4_DIR : lwarx/stwcx. with a real reservation instead of a bare compare-and-swap.

Upstream turns lwarx/stwcx. into "store if the word still holds the value lwarx saw". That has the ABA problem:
Mario & Sonic Rio 2016's lock-free free lists (hh::rsdx RsdxAtomicPopSList: head = lwarx; next = head->next;
stwcx. next) break when another thread pops the head, pops the next entry and pushes the head back in between -
the word holds the old value again, the compare-and-swap succeeds and the list hands out an entry that is in use
(random null shaders, garbage pointers, the "next == head" assertion in render jobs).

On hardware ANY store into the reservation granule in between makes stwcx. fail. Here every stwcx. bumps a
version counter of its address' line (a table of 4096 lines, hashed by 32-byte granule); lwarx remembers the
version, stwcx. only stores while that version is unchanged (and the word still holds the value). A collision of two
addresses in one line only causes a spurious failure, which the guest's retry loop absorbs. Plain stores by other
threads are still only caught when they change the value (as before)."""
import sys
root = sys.argv[1]


def edit(path, pairs):
    p = root + '/' + path
    s = open(p, encoding='utf-8').read()
    for old, new in pairs:
        if new in s:
            continue
        if old not in s:
            sys.exit('patch_reservation: text not found in %s: %r' % (path, old[:60]))
        s = s.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(s)


edit('runtime/include/cafe/ppc_context.h', [
    ('''    uint8_t reserve_valid;
    void* host_thread;''', '''    uint8_t reserve_valid;
    uint32_t reserve_version; // port/patch_reservation.py: line version seen by lwarx
    void* host_thread;'''),
])

edit('runtime/include/cafe/ppc_ops.h', [
    ('''// lwarx/stwcx. as a compare-and-swap on the observed word.
inline uint32_t lwarx(PPCContext& ctx, const uint8_t* base, uint32_t ea) {
    uint32_t raw;
''', '''// lwarx/stwcx. as a compare-and-swap on the observed word, guarded by a version per reservation line
// (port/patch_reservation.py): a stwcx. by another thread in between makes ours fail, as on hardware.
extern uint32_t g_reserve_lines[4096];
inline uint32_t* reserve_line(uint32_t ea) { return &g_reserve_lines[((ea >> 5) ^ (ea >> 17)) & 4095u]; }
inline uint32_t lwarx(PPCContext& ctx, const uint8_t* base, uint32_t ea) {
    ctx.reserve_version = __atomic_load_n(reserve_line(ea), __ATOMIC_ACQUIRE);
    uint32_t raw;
'''),
    ('''    uint32_t expected = ctx.reserve_value;
    return __atomic_compare_exchange_n(reinterpret_cast<uint32_t*>(base + ea),
                                       &expected, __builtin_bswap32(value),
                                       false, __ATOMIC_SEQ_CST,
                                       __ATOMIC_SEQ_CST);
}''', '''    uint32_t version = ctx.reserve_version;
    if (version & 1u) {
        return false; // lwarx saw another stwcx. in progress
    }
    uint32_t* const line = reserve_line(ea);
    if (!__atomic_compare_exchange_n(line, &version, version + 1u, false, __ATOMIC_ACQUIRE, __ATOMIC_RELAXED)) {
        return false; // another stwcx. to this line since our lwarx
    }
    uint32_t expected = ctx.reserve_value;
    const bool stored = __atomic_compare_exchange_n(reinterpret_cast<uint32_t*>(base + ea),
                                                    &expected, __builtin_bswap32(value),
                                                    false, __ATOMIC_SEQ_CST,
                                                    __ATOMIC_SEQ_CST);
    __atomic_store_n(line, ctx.reserve_version + 2u, __ATOMIC_RELEASE);
    return stored;
}'''),
])

edit('runtime/src/memory.cpp', [
    ('''void reserve_guest_memory() {''', '''namespace ppc {
uint32_t g_reserve_lines[4096]{}; // port/patch_reservation.py
}

void reserve_guest_memory() {'''),
])
