#!/usr/bin/env python3
"""patch_unaligned_entry.py SMASH4_DIR : an entry at an address that is not a multiple of 4 (Sochi 2014: a symbol
at 0x03338EF5) was emitted as an alternate entry jumping to label loc_03338EF5, which no instruction has -> the
generated shard did not compile. Such an entry now starts at its aligned instruction."""
import sys
p = sys.argv[1] + "/recomp/src/codegen.cpp"
s = open(p, encoding="utf-8").read()
if "patch_unaligned_entry" in s:
    print("already applied"); sys.exit(0)
old = """        if (entry.address != function_.address) {
            line(text::format("goto loc_{:08X};", entry.address));
        }"""
new = """        // port/patch_unaligned_entry.py: an unaligned entry (a symbol at an odd address) starts at its instruction.
        if ((entry.address & ~3u) != function_.address) {
            line(text::format("goto loc_{:08X};", entry.address & ~3u));
        }"""
assert s.count(old) == 1
open(p, "w", encoding="utf-8").write(s.replace(old, new))
print("patched", p)
