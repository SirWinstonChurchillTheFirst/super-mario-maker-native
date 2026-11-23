#!/usr/bin/env python3
"""Runs ON the console (console/deploy.sh sends it): adds the port to the Emulator/Nativ chooser's list
and hides its ports entry, as the other native ports' entries are. Existing entries stay.
NOT RUN YET. Written for the new shell (Nova Home reads gamelist.xml itself; EmulationStation is not running):
the ports entry is written into gamelist.xml directly, after a backup."""
import json
import shutil
import time
from pathlib import Path
from xml.sax.saxutils import escape

stamp = time.strftime("%Y%m%d-%H%M")
games = Path("/userdata/system/nova/native-games.json")
data = json.loads(games.read_text(encoding="utf-8"))
add = json.loads(Path("/tmp/native-games.add.json").read_text(encoding="utf-8"))
have = {g["rom"] for g in data["games"]}
new = [e for e in add if e["rom"] not in have]
if new:
    shutil.copy(games, f"{games}.bak-{stamp}")
    data["games"] += new
    games.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("chooser:", [e["title"] for e in new])

gl = Path("/userdata/roms/ports/gamelist.xml")
text = gl.read_text(encoding="utf-8")
entries = ""
for e in add:
    name = Path(e["native"]).name
    if f"./{escape(name)}</path>" in text:
        continue
    entries += f"\t<game>\n\t\t<path>./{escape(name)}</path>\n\t\t<name>{escape(name[:-3])}</name>\n\t\t<hidden>true</hidden>\n\t</game>\n"
if entries and "</gameList>" in text:
    shutil.copy(gl, f"{gl}.bak-{stamp}")
    gl.write_text(text.replace("</gameList>", entries + "</gameList>"), encoding="utf-8")
    print("ports list: hidden entry written")
else:
    print("ports list: nothing to add")
