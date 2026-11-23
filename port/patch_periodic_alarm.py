"""OSSetPeriodicAlarm's start is an OSTime (OSGetTime: ticks since 2000), but the runtime's alarms run on the system
time base (ticks since start-up): a start taken from OSGetTime() lay years in the future, so the alarm never fired
(Mario Party 10: nw::snd's Wii Remote speaker alarm -> remotes never counted as players). Converts such a start.
Applied to the runtime tree (default ~/wiiu/smash4)."""
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/wiiu/smash4")


def patch(rel, old, new):
    path = os.path.join(ROOT, rel)
    text = open(path, encoding="utf-8").read()
    if "patch_periodic_alarm" in text:
        print("already:", rel)
        return
    if text.count(old) != 1:
        sys.exit(f"{rel}: anchor not found once")
    open(path, "w", encoding="utf-8", newline="").write(text.replace(old, new))
    print("patched:", rel)


patch("runtime/src/os/coreinit_misc.cpp",
      "} // namespace cafe::os\n",
      "// port/patch_periodic_alarm.py: OSGetTime minus the system time base.\n"
      "int64_t os_time_offset() { return ticks_since_2000() - static_cast<int64_t>(cafe_ppc_timebase()); }\n"
      "} // namespace cafe::os\n")

patch("runtime/src/os/alarm.cpp",
      "bool OSSetPeriodicAlarm(GuestAddress alarm, uint64_t start, uint64_t period, uint32_t handler) {\n"
      "    uint64_t when = start;\n",
      "bool OSSetPeriodicAlarm(GuestAddress alarm, uint64_t start, uint64_t period, uint32_t handler) {\n"
      "    // port/patch_periodic_alarm.py: an OSTime start (from OSGetTime) to the system time base\n"
      "    const int64_t offset = os_time_offset();\n"
      "    if (offset > 0 && start >= static_cast<uint64_t>(offset)) start -= static_cast<uint64_t>(offset);\n"
      "    uint64_t when = start;\n")

path = os.path.join(ROOT, "runtime/src/os/alarm.cpp")
text = open(path, encoding="utf-8").read()
decl = "int64_t os_time_offset(); // port/patch_periodic_alarm.py\n"
if decl not in text:
    i = text.index("namespace cafe::os {\n") + len("namespace cafe::os {\n")
    text = text[:i] + decl + text[i:]
    open(path, "w", encoding="utf-8", newline="").write(text)
    print("declared in alarm.cpp")
