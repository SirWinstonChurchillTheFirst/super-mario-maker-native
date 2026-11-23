#!/usr/bin/env python3
"""set_default.py JSON TITLE_SUBSTRING native|emulator: sets "default" of the matching native-games.json entry.

Runs on the console (python3 there). Backs the file up first as <file>.bak-<date-time>. Prints the changed entry.
"""
import json
import shutil
import sys
import time

path, title, mode = sys.argv[1], sys.argv[2], sys.argv[3]
assert mode in ("native", "emulator")
data = json.load(open(path, encoding="utf-8"))
hits = [g for g in data["games"] if title.lower() in g.get("title", "").lower()]
if len(hits) != 1:
    sys.exit(f"{len(hits)} entries match {title!r}: nothing changed")
backup = path + time.strftime(".bak-%Y%m%d-%H%M")
shutil.copy2(path, backup)
hits[0]["default"] = mode
with open(path + ".neu", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")
shutil.move(path + ".neu", path)
print("backup", backup)
print(hits[0]["title"], "->", hits[0]["default"])
