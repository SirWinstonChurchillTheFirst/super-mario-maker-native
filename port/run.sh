#!/bin/bash
# run.sh NAME GAME_FOLDER : start a title built by setup.sh. Saves go to ~/wiiu/run/NAME/save.
# TTT2_SCALE=1 renders at the console's 720p (default: 2x). TTT2_GPU=null runs without a window.
NAME=$1; GAME=$2
mkdir -p ~/wiiu/run/$NAME/save
LD_LIBRARY_PATH=$HOME/wiiu/sdl/lib CAFE_SAVE_DIR=$HOME/wiiu/run/$NAME/save exec ~/wiiu/build-$NAME/cafegame "$GAME"
