#!/usr/bin/env python3
"""patch_fetch_1010102.py SMASH4_DIR (after patch_fetch_2101010.py): vertex fetch data format 0x1B (10_10_10_2) with
normalized or scaled conversion, which the translator refused ("10_10_10_2 fetch conversion"). Mario Tennis Ultra
Smash uses it; its vertex shaders with such inputs were not translated and those models were not drawn.
Uses the per-width conversion added for format 0x19."""
import sys
p = sys.argv[1] + '/runtime/src/latte/translate.cpp'
s = open(p, encoding='utf-8').read()
pairs = [
    ('    if (data_format == 0x19 && !raw32) {\n', '    if ((data_format == 0x19 || data_format == 0x1B) && !raw32) {\n'),
    ('''    if (data_format == 0x1B && num_format != 1 && !raw32) {
        fail("10_10_10_2 fetch conversion"); // W has its own width
    }
''', ''),
]
changed = False
for old, new in pairs:
    if old in s:
        s = s.replace(old, new, 1)
        changed = True
if changed:
    open(p, 'w', encoding='utf-8').write(s)
print('patch_fetch_1010102:', 'done' if changed else 'already there')
