#!/bin/bash
# quick.sh NAME "GAME FOLDER" [SECONDS] : rebuild win/build-NAME (port sources + runtime) and run it WITHOUT a window
# (TTT2_GPU=null), to find the next missing system function or fault fast. Prints why it stopped.
NAME=$1; GAME=$2; SECS=${3:-40}
R=/d/retro/wiiurecomp
bash $R/tools/win_build.sh $NAME | tail -4
mkdir -p $R/win/run/$NAME/save && cd $R/win/run/$NAME || exit 1
W=$(cygpath -m "$PWD")
PATH="/c/msys64/clang64/bin:$PATH" CAFE_SAVE_DIR="$W/save" TTT2_GPU=null TTT2_INPUT_SCRIPT="${INPUT:-10:a,14:a,18:a,22:a,26:a,30:a,34:a}" \
  timeout $SECS $R/win/build-$NAME/cafegame.exe "$(cygpath -m "$GAME")" > quick.log 2>&1
echo "RC=$? lines=$(wc -l < quick.log)"
grep -n "does not implement\|^port: \|fatal\|fault\|not provided" quick.log | sort -t: -k2 -u | tail -8 | cut -c1-220
echo "--- last lines"; grep -v "^  r[0-9]\|^  lr \|^  0x" quick.log | tail -${TAIL:-5} | cut -c1-220
