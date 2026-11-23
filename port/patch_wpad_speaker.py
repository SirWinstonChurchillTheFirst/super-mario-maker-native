"""Removes the runtime's "no device" answers for the Wii Remote speaker (offline_services.cpp); port/os_extra.cpp
answers them now for connected (emulated) remotes: Mario Party 10 waits for WPADControlSpeaker's callback before it
counts a remote as a player. Applied to the runtime tree (default ~/wiiu/smash4)."""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")
path = os.path.join(ROOT, "runtime/src/os/offline_services.cpp")
text = open(path, encoding="utf-8").read()
names = ("WPADCanSendStreamData", "WPADSendStreamData", "WPADControlSpeaker")
lines = text.split("\n")
out = [l for l in lines if not any(l.startswith("CAFE_EXPORT(padscore, %s," % n) for n in names)]
print("removed", len(lines) - len(out), "lines from", path)
open(path, "w", encoding="utf-8", newline="").write("\n".join(out))
