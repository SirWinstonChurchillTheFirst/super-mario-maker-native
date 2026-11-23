#!/bin/bash
# iter.sh NAME "GAME FOLDER" [SECONDS] : build build-NAME/cafegame and run it without a window; prints why it stopped.
# Extra environment (TTT2_TRACE_*, TTT2_GPU=...) is passed through. Run in WSL.
NAME=$1; GAME=$2; SECS=${3:-40}
PORT=$(cd "$(dirname "$0")" && pwd)
# The port's sources are built from a copy inside WSL: a file just written from Windows can still show its old
# time on /mnt/d, and ninja then skips it.
mkdir -p ~/wiiu/port
for f in $PORT/*.cpp; do cmp -s "$f" ~/wiiu/port/$(basename "$f") || cp "$f" ~/wiiu/port/; done
cd ~/wiiu/build-$NAME || exit 1
cmake -Wno-dev -DGAME_MAIN=$HOME/wiiu/port/game_main.cpp "-DGAME_EXTRA=$HOME/wiiu/port/netplay_none.cpp;$HOME/wiiu/port/os_extra.cpp" . > cmake.log 2>&1 || { tail -5 cmake.log; exit 1; }
nice ninja -j20 cafegame > build.log 2>&1 || { grep -n "error" -A6 build.log | head -40 | cut -c1-260; exit 1; }
[ "$SECS" = 0 ] && exit 0
mkdir -p ~/wiiu/run/$NAME/save && cd ~/wiiu/run/$NAME
n=$(ls run*.log 2>/dev/null | wc -l); LOG=run$((n + 1)).log
CAFE_SAVE_DIR=$PWD/save TTT2_GPU=${TTT2_GPU:-null} timeout $SECS ~/wiiu/build-$NAME/cafegame "$GAME" > $LOG 2>&1
echo "RC=$? $LOG lines=$(wc -l < $LOG)"
grep -n "does not implement\|^ttt2: \|^port: \|fatal\|not provided\|warning" $LOG | sort -t: -k2 -u | tail -${LINES_MAX:-12} | cut -c1-230
echo "--- last lines"; grep -v "^  r[0-9]\|^  lr \|^  0x" $LOG | tail -${TAIL:-6} | cut -c1-230
