#!/bin/bash
# Puts one Wii U port on the console (first run: 19 November, Super Mario 3D World).
#   bash console/deploy.sh 3dworld "Super Mario 3D World" "Super Mario 3D World" code/RedCarpet.rpx [host]
#     $1 name (WSL build ~/wiiu/build-$1/cafegame)   $2 title for the menu
#     $3 game folder under /userdata/roms/wiiu        $4 the game's entry in the Wii U list (rom path below the folder)
# - refuses while a game runs there (Nova Home does not count)
# - the program goes over in throttled pieces (the WLAN stick stalls on fast uploads)
# - nothing of the player's is overwritten: save/ is only created, native-games.json is backed up first,
#   an existing program is kept as cafegame.vor-<date>
# - the chooser's default stays "emulator" until the user has tried the native one
# After it: start the ports script once through the menu's interface and LOOK at the picture
#   curl -s -X POST localhost:1234/launch -d "/userdata/roms/ports/<Title> (Nativ).sh"
set -e
N=$1; TITLE=$2; FOLDER=$3; ROM=$4; H=${5:-${CONSOLE_HOST:-root@batocera.local}}
P=${WIIU_WORK:-$HOME/wiiurecomp}
OUT=$P/console/out/$N; mkdir -p "$OUT"
running=$(ssh -o ConnectTimeout=10 $H 'curl -s -m 3 localhost:1234/runningGame' 2>/dev/null)
echo "$running" | grep -q "NO GAME RUNNING\|\"name\": \"Nova Home\"" || { echo "stop: a game is running on the console"; exit 1; }

push() {  # push <local file> <path on the console>
  local T; T=$(mktemp -d); gzip -6 -c "$1" > $T/t.gz; (cd $T && split -b 400k t.gz p.)
  ssh -o ConnectTimeout=30 -o BatchMode=yes $H 'rm -rf /tmp/ch; mkdir -p /tmp/ch' 2>/dev/null
  for f in $T/p.*; do ok=0; for try in 1 2 3 4 5 6 7 8; do
      if scp -q -l 1500 -o ConnectTimeout=20 $f $H:/tmp/ch/ 2>/dev/null; then ok=1; break; fi; ping -n 10 127.0.0.1 >/dev/null; done
    [ $ok = 1 ] || { echo "FEHLER $f"; exit 1; }; done
  ssh -o ConnectTimeout=30 -o BatchMode=yes $H "cat /tmp/ch/p.* | gunzip > '$2.neu' && mv -f '$2.neu' '$2' && md5sum '$2' | cut -c1-32" 2>/dev/null
  md5sum "$1" | cut -c1-32; rm -rf $T
}

wsl -e bash -lc "strip -o ${WIIU_WORK_WSL:-/mnt/c/wiiurecomp}/console/out/$N/cafegame ~/wiiu/build-$N/cafegame && cp ~/wiiu/build-$N/fonts/CafeStd.ttf ${WIIU_WORK_WSL:-/mnt/c/wiiurecomp}/console/out/$N/CafeStd.ttf"
B=/userdata/ports-native/wiiu
ssh $H "mkdir -p $B/$N/fonts $B/$N/save $B/lib; [ -f $B/$N/cafegame ] && cp -p $B/$N/cafegame $B/$N/cafegame.vor-\$(date +%Y%m%d-%H%M); true" 2>/dev/null
# Game data on the SSD: /userdata/roms is a merged view of the hard disk without a page cache there,
# every read costs 8-40 ms (found by the 3DS work, 19 November). Copied on the console itself, once.
echo "== game data to the SSD"
ssh $H "[ -f $B/$N/game/.komplett ] || { rm -rf $B/$N/game.neu && cp -a \"/userdata/roms/wiiu/$FOLDER\" $B/$N/game.neu && rm -rf $B/$N/game && mv $B/$N/game.neu $B/$N/game && touch $B/$N/game/.komplett; }; du -sh $B/$N/game | cut -f1" 2>/dev/null
echo "== program"; push "$OUT/cafegame" $B/$N/cafegame; ssh $H "chmod +x $B/$N/cafegame" 2>/dev/null
scp -q "$OUT/CafeStd.ttf" "$H:$B/$N/fonts/CafeStd.ttf" 2>/dev/null     # free stand-in font (DejaVu Sans), not Nintendo's
scp -q "$P/console/launch.sh" "$H:$B/launch.sh" 2>/dev/null; ssh $H "chmod +x $B/launch.sh" 2>/dev/null

S="$OUT/$TITLE (Nativ).sh"
cat > "$S" <<EOF
#!/bin/bash
# Nativer Port (Wii U, ohne Emulator): $TITLE
exec /userdata/ports-native/wiiu/launch.sh $N "/userdata/ports-native/wiiu/$N/game"
EOF
cat > "$OUT/native-games.add.json" <<EOF
[{"rom": "/userdata/roms/wiiu/$FOLDER/$ROM", "title": "$TITLE",
  "native": "/userdata/roms/ports/$TITLE (Nativ).sh", "native_system": "ports", "native_systemname": "Ports",
  "native_label": "Nativ", "native_sub": "Recomp · 60 fps", "emulator_label": "Emulator", "emulator_sub": "Cemu"}]
EOF
scp -q "$S" "$OUT/native-games.add.json" "$P/console/install_entry.py" "$H:/tmp/" 2>/dev/null
ssh $H "cd /tmp && { [ -e \"/userdata/roms/ports/$TITLE (Nativ).sh\" ] || { cp \"$TITLE (Nativ).sh\" /userdata/roms/ports/ && chmod +x \"/userdata/roms/ports/$TITLE (Nativ).sh\"; }; } && python3 /tmp/install_entry.py" 2>/dev/null
echo "done. Not started yet."
