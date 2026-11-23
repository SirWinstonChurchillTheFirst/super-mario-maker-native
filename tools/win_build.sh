#!/bin/bash
# win_build.sh NAME : Windows build of one translated title (Git Bash). Copies the generated code from WSL
# (~/wiiu/gen/NAME) to win/gen/NAME if it is not there, syncs the runtime and the port sources, configures
# win/build-NAME once and builds cafegame.exe. Log: win/build-NAME/build.log
NAME=$1; R=${WIIU_WORK:-$HOME/wiiurecomp}; W=$(cygpath -m "${WIIU_WORK:-$HOME/wiiurecomp}")/win
[ -d $R/win/gen/$NAME ] || wsl -e bash -lc "mkdir -p ${WIIU_WORK_WSL:-/mnt/c/wiiurecomp}/win/gen && cp -r ~/wiiu/gen/$NAME ${WIIU_WORK_WSL:-/mnt/c/wiiurecomp}/win/gen/"
wsl -e bash -lc "cp -ru ~/wiiu/smash4/runtime ${WIIU_WORK_WSL:-/mnt/c/wiiurecomp}/win/smash4/"
cp $R/port/*.cpp $R/win/port/
export PATH="/c/msys64/clang64/bin:$PATH"
cd $R/win || exit 1
if [ ! -f build-$NAME/build.ninja ]; then
  cmake -S smash4 -B build-$NAME -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
    -DVulkan_LIBRARY=C:/msys64/clang64/lib/libvulkan-1.dll.a -DGAME_GENERATED_DIR=$W/gen/$NAME \
    -DGAME_MAIN=$W/port/game_main.cpp "-DGAME_EXTRA=$W/port/netplay_none.cpp;$W/port/os_extra.cpp" > build-$NAME.cmake.log 2>&1 || { tail -5 build-$NAME.cmake.log; exit 1; }
fi
ninja -C build-$NAME -j${JOBS:-10} cafegame > build-$NAME/build.log 2>&1; rc=$?
grep -E "error|FAILED" build-$NAME/build.log | head -8 | cut -c1-240
[ -d build-$NAME/fonts ] || cp -r build-3dworld/fonts build-$NAME/ 2>/dev/null
echo "win_build $NAME rc=$rc"
