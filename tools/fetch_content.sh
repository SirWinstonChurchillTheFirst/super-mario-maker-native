#!/bin/bash
# fetch_content.sh : copy the content/ folders of more titles from the console to games/ (throttled, read-only there).
cd /d/retro/wiiurecomp/games || exit 1
for g in "Mario Tennis Ultra Smash" "Mario Kart 8" "Super Mario 3D World"; do
  [ -f "$g/.content-complete" ] && continue
  echo "$(date +%H:%M:%S) start $g"
  scp -q -r -l 24000 -o ConnectTimeout=15 "root@192.168.178.107:/userdata/roms/wiiu/$g/content" "$g/" 2>/dev/null && touch "$g/.content-complete"
  echo "$(date +%H:%M:%S) done $g rc=$? $(du -sh "$g/content" | cut -f1)"
done
