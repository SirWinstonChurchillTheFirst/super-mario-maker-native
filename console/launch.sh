#!/bin/bash
# Starts a Wii U game built with the cafe runtime on the Batocera box: launch.sh <name> "<game folder>"
#   name = folder under /userdata/ports-native/wiiu (3dworld, tennis, ...), holds cafegame, fonts/, save/
# Called from the hidden ports script "/userdata/roms/ports/<Title> (Nativ).sh".
# First run on the console: 19 November (Super Mario 3D World).
NAME=$1
GAME=$2
BASE=/userdata/ports-native/wiiu/$NAME
cd "$BASE" || exit 1
[ -n "$DISPLAY" ] || export DISPLAY=:0.0
# shaderc comes with the Wii ports; everything else the binary needs is part of Batocera 43
export LD_LIBRARY_PATH=/userdata/ports-native/wiiu/lib:/userdata/ports-native/wiirecomp/lib
# Controllers through the normal input system, with the menu's mapping (as the other native ports)
export SDL_JOYSTICK_HIDAPI=0 SDL_JOYSTICK_HIDAPI_WII=0
export SDL_GAMECONTROLLERCONFIG="$(python3 /userdata/system/nova/padfix.py 2>/dev/null)"
export TTT2_FULLSCREEN=1 CAFE_SAVE_DIR=$BASE/save
mkdir -p "$BASE/save" /userdata/system/logs
# Scale 1 = the Wii U's own 1280x720: the runtime's default on a 1080p screen is 2560x1440, which the console's
# Vega 6 cannot fill (1.6 pictures a second, measured 19 November).
export TTT2_SCALE=1
# The console language the games see (runtime: port/patch_language.py): Batocera's system.language (de_DE, fr_FR, ...),
# German when it is not set. CAFE_LANGUAGE given from outside wins.
if [ -z "$CAFE_LANGUAGE" ]; then
  CAFE_LANGUAGE=$(batocera-settings-get system.language 2>/dev/null)
  export CAFE_LANGUAGE=${CAFE_LANGUAGE:-de}
fi
# Mii resources (system title 0005001B-10056000) from the player's own Wii U, where Cemu keeps them; read only.
# Without them the games run with Miis missing. The account Mii comes from Cemu's account file if there is one.
[ -z "$CAFE_SYS_DIR" ] && [ -d /userdata/saves/wiiu/sys/title ] && export CAFE_SYS_DIR=/userdata/saves/wiiu/sys
[ -z "$CAFE_ACCOUNT_DAT" ] && [ -f /userdata/saves/wiiu/usr/save/system/act/80000001/account.dat ] && \
  export CAFE_ACCOUNT_DAT=/userdata/saves/wiiu/usr/save/system/act/80000001/account.dat
# After this game is ended with the hotkey (Alt+F4 from Batocera's virtual "batocera hotkeys" keyboard), the display
# server keeps Alt and F4 as held down on that keyboard, and every game started afterwards closes after 3 s
# (seen 19 November, three times; why the release is lost is NOT found). Until it is: a held key on that
# keyboard is released by switching the device off and on, before the start and after the end, with a log line.
LOG=/userdata/system/logs/native-wiiu-$NAME.log
fix_keys() {
  for id in $(xinput list --id-only 2>/dev/null); do
    [ "$(xinput list --name-only $id 2>/dev/null)" = "batocera hotkeys" ] || continue
    if xinput query-state $id 2>/dev/null | grep -q '=down'; then
      xinput disable $id; sleep 0.3; xinput enable $id
      echo "launch.sh: keys were held down on 'batocera hotkeys' ($1): released" >> "$LOG.keys"
    fi
  done
}
fix_keys "before the start"
# Switches one game always needs (e.g. Super Mario Maker: GamePad picture, touch cursor), beside its program.
[ -f "$BASE/game.env" ] && . "$BASE/game.env"
# Extra switches for one test run (the file is gone after a restart): e.g. "export CAFE_SAVE_DIR=$BASE/save-test"
[ -f /tmp/wiiutest.env ] && . /tmp/wiiutest.env
./cafegame "$GAME" > "$LOG" 2>&1 &
game=$!
trap 'kill $game 2>/dev/null; sleep 3; kill -9 $game 2>/dev/null' TERM INT HUP
wait $game
sleep 1
fix_keys "after the end"
