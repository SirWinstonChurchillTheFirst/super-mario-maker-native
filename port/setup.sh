#!/bin/bash
# setup.sh GAME_FOLDER NAME : translate one Wii U title and build it as a native Linux program.
#   GAME_FOLDER  your own dump, unpacked: code/ content/ meta/ (as Cemu or Dumpling give it)
#   NAME         a short name for the build folders, e.g. rio
# Result: ~/wiiu/build-NAME/cafegame. Start it with run.sh.
#
# NOTE (19 Nov 2026): this script writes down the steps that were done by hand that night, in order.
# As one script it has NOT been run from start to end yet.
#
# Needs (Ubuntu 24.04): clang cmake ninja-build git python3 zlib1g-dev libzstd-dev libssl-dev libvulkan-dev
# libshaderc-dev, and SDL3 built with video and sound (see the SDL block below).
set -e
GAME=$1; NAME=$2
[ -d "$GAME/code" ] && [ -n "$NAME" ] || { echo "usage: setup.sh GAME_FOLDER NAME"; exit 2; }
PORT=$(cd "$(dirname "$0")" && pwd)
W=~/wiiu; mkdir -p $W/port $W/rpx $W/gen; cd $W

# 1. The runtime and recompiler this builds on: Smash 4 PC (MIT), itself built on Petexy's cafe-recomp (MIT).
if [ ! -d smash4 ]; then
    git clone https://github.com/josiahg2502-glitch/Smash4PC smash4
    git -C smash4 checkout f145e7f
    git -C smash4 apply "$PORT/upstream-local.patch"
    cat "$PORT/game.cmake" >> smash4/CMakeLists.txt
    sed -i 's/^    add_subdirectory(launcher)/    # add_subdirectory(launcher)/; s/^    add_subdirectory(tests)/    # add_subdirectory(tests)/' smash4/CMakeLists.txt
    for d in "ZArchive https://github.com/Exzap/ZArchive.git 965b66c8d67b6b7e30fd63b3b75aa91a99ff303b" \
             "addrlib https://github.com/decaf-emu/addrlib.git 194162c47469ce620dd2470eb767ff5e42f5954a" \
             "Vulkan-Headers https://github.com/KhronosGroup/Vulkan-Headers.git b0c3dd6851e22621f194306d511b9253e4c1577f"; do
        set -- $d
        mkdir -p smash4/third_party/$1 && git -C smash4/third_party/$1 init -q
        git -C smash4/third_party/$1 fetch -q --depth 1 $2 $3 && git -C smash4/third_party/$1 checkout -q FETCH_HEAD
    done
fi

# 2. SDL3 with a window and sound.
if [ ! -d sdl ]; then
    git clone --depth 1 -b release-3.2.26 https://github.com/libsdl-org/SDL.git SDL
    cmake -S SDL -B SDL/build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=$W/sdl -DSDL_TESTS=OFF -DSDL_EXAMPLES=OFF
    ninja -C SDL/build install
fi

# 3. The recompiler alone (a small wrapper project around smash4/recomp).
if [ ! -x build-recomp/recomp/cafe-recomp ]; then
    mkdir -p rc && ln -sfn ../smash4/recomp rc/recomp && ln -sfn ../smash4/runtime rc/runtime && ln -sfn ../smash4/tests rc/tests
    printf 'cmake_minimum_required(VERSION 3.20)\nproject(rc LANGUAGES C CXX)\nadd_subdirectory(recomp)\n' > rc/CMakeLists.txt
    cmake -Wno-dev -S rc -B build-recomp -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++
    ninja -C build-recomp cafe-census cafe-recomp
fi

# 4. Translate the title's executable to C++ (the output contains the game's code: never share it).
RPX=$(ls "$GAME"/code/*.rpx | head -1)
cp "$RPX" rpx/$NAME.rpx
build-recomp/recomp/cafe-recomp rpx/$NAME.rpx gen/$NAME --any-rpx

# 5. Build runtime + translated code.
cp "$PORT"/*.cpp port/
cmake -Wno-dev -S smash4 -B build-$NAME -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
    -DCMAKE_PREFIX_PATH=$W/sdl -DVulkan_INCLUDE_DIR=$W/smash4/third_party/Vulkan-Headers/include \
    -DSHADERC_LIBRARY=/usr/lib/x86_64-linux-gnu/libshaderc.so \
    -DGAME_GENERATED_DIR=$W/gen/$NAME -DGAME_MAIN=$W/port/game_main.cpp \
    "-DGAME_EXTRA=$W/port/netplay_none.cpp;$W/port/os_extra.cpp"
ninja -C build-$NAME cafegame

# 6. The console's system font is not part of a game dump. Until you copy your console's CafeStd.ttf there,
#    a free font stands in (texts then look different from the console's).
mkdir -p build-$NAME/fonts
[ -f build-$NAME/fonts/CafeStd.ttf ] || cp /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf build-$NAME/fonts/CafeStd.ttf
echo "built: $W/build-$NAME/cafegame"
