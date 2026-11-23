"""Removes the runtime's "no h264 device" stubs (offline_services.cpp); port/os_extra.cpp provides H264DEC* now
(black frames from a working decoder interface, see there). Applied to the runtime tree (default ~/wiiu/smash4)."""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "runtime/src/os/offline_services.cpp")
text = open(path, encoding="utf-8").read()
if "patch_h264" in text:
    sys.exit("already: " + path)
lines = text.split("\n")
out = []
removed = 0
for line in lines:
    if line.startswith("CAFE_EXPORT(h264, "):
        removed += 1
        continue
    out.append(line)
text = "\n".join(out).replace("// Video decoding (h264): not available yet,",
                              "// port/patch_h264.py: h264 now in port/os_extra.cpp.\n// Video decoding (h264): not available yet,")
open(path, "w", encoding="utf-8", newline="").write(text)
print("removed", removed, "h264 exports from", path)
