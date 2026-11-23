#!/usr/bin/env python3
"""patch_hfio_sys.py RUNTIME_SRC_DIR : /vol/storage_hfiomlc01/sys = /vol/storage_mlc01/sys (CAFE_SYS_DIR, read only).
Paper Mario Color Splash looks for the shared font title 0005001B-1005C000 through SCIGetContentPath, which tries the
"hfio" device name first."""
import sys
p = sys.argv[1] + "/vfs.cpp"
s = open(p, encoding="utf-8").read()
if "patch_hfio_sys" in s:
    print("already applied"); sys.exit(0)
old = '    if (parts.size() >= 3 && iequals(parts[1], "storage_mlc01") && iequals(parts[2], "sys") && !sys_root().empty()) {\n'
new = ('    // port/patch_hfio_sys.py: storage_hfiomlc01 is the same system area\n'
       '    if (parts.size() >= 3 && (iequals(parts[1], "storage_mlc01") || iequals(parts[1], "storage_hfiomlc01")) &&\n'
       '        iequals(parts[2], "sys") && !sys_root().empty()) {\n')
assert s.count(old) == 1
open(p, "w", encoding="utf-8", newline="\n").write(s.replace(old, new))
print("patched", p)
