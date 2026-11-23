#!/usr/bin/env python3
"""Debug: TTT2_TRACE_DYNLOAD=1 prints OSDynLoad_Acquire / OSDynLoad_FindExport calls and what they answer.

usage: patch_dynload_trace.py RUNTIME_DIR
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
p = root / "src/os/dynload.cpp"
s = p.read_text()
if "TTT2_TRACE_DYNLOAD" in s:
    print("already patched")
    sys.exit(0)
old = """    std::string module(guest_string(name));
    if (module.size() > 4 && module.compare(module.size() - 4, 4, ".rpl") == 0) module.resize(module.size() - 4);"""
new = """    std::string module(guest_string(name));
    if (module.size() > 4 && module.compare(module.size() - 4, 4, ".rpl") == 0) module.resize(module.size() - 4);
    if (std::getenv("TTT2_TRACE_DYNLOAD")) std::fprintf(stderr, "dynload: acquire %s\\n", module.c_str()); // port/patch_dynload_trace.py"""
assert s.count(old) == 1
s = s.replace(old, new)
old2 = """    const std::string symbol(guest_string(name));
    const std::string key = module->second + ":" + symbol;"""
new2 = """    const std::string symbol(guest_string(name));
    const std::string key = module->second + ":" + symbol;
    if (std::getenv("TTT2_TRACE_DYNLOAD")) std::fprintf(stderr, "dynload: find %s%s\\n", key.c_str(), is_data ? " (data)" : ""); // port/patch_dynload_trace.py"""
assert s.count(old2) == 1
s = s.replace(old2, new2)
if "#include <cstdlib>" not in s:
    s = s.replace('#include "kernel.h"', '#include "kernel.h"\n#include <cstdio>\n#include <cstdlib>', 1)
p.write_text(s)
print("ok")
