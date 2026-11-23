#!/usr/bin/env python3
"""fix_surface_string.py SMASH4_DIR : repairs a string literal an early version of patch_surface_invalid.py broke
across two lines (harmless when the file is already right)."""
import sys
p = sys.argv[1] + '/runtime/src/gx2/surface.cpp'
s = open(p, encoding='utf-8').read()
bad = 'answered 0 bytes\n", width'
if bad in s:
    s = s.replace(bad, 'answered 0 bytes' + chr(92) + 'n", width')
    open(p, 'w', encoding='utf-8').write(s)
    print('fix_surface_string: repaired')
else:
    print('fix_surface_string: nothing to do')
