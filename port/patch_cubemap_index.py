"""SET_CUBEMAP_INDEX in pixel/vertex shaders is accepted (no-op) instead of failing the whole shader.

Mario Kart 8 has dozens of pixel shaders with SET_CUBEMAP_INDEX (it selects the layer of a cube-map array for the
next SAMPLE); the translator refused them ("unsupported texture instruction SET_CUBEMAP_INDEX"), so those draws were
skipped and the picture stayed black. The runtime binds cube maps as single cubes, so the index has nothing to
select: the instruction is now dropped (layer 0), as Cemu effectively does for non-array cube maps.
After this change delete win/build-NAME/cache (translated shader cache).
Applied to the runtime tree given as the first argument (default ~/wiiu/smash4).
"""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "runtime/src/latte/translate.cpp")
text = open(path, encoding="utf-8").read()
if "patch_cubemap_index" in text:
    print("already: translate.cpp")
    sys.exit(0)
old = "    switch (t.inst) {\n    case kSetGradientsH:\n    case kSetGradientsV:\n"
new = ("    switch (t.inst) {\n"
       "    case kSetCubemapIndex: // port/patch_cubemap_index.py: cube maps are bound as single cubes, layer 0\n"
       "        return;\n"
       "    case kSetGradientsH:\n    case kSetGradientsV:\n")
assert text.count(old) == 1
text = text.replace(old, new)
open(path, "w", encoding="utf-8", newline="\n").write(text)
print("patched: translate.cpp (SET_CUBEMAP_INDEX)")
