#!/bin/bash
# native-build.sh GAME_FOLDER : builds the native program of this repository's game from YOUR OWN game dump.
# Called by setup-linux.sh (Linux) and setup-windows.ps1 (Windows, inside MSYS2's CLANG64 shell); you normally
# do not run it yourself. Same file in every Wii U repository; what differs per game is in ../game.conf.
#
#   GAME_FOLDER  your own dump of the game, unpacked: code/ content/ meta/ (as Cemu or a dumper gives it)
#
# Environment (all optional):
#   NATIVE_WORK   build folder (default: <repo>/build)   NATIVE_PLAY  result folder (default: <repo>/play)
#   JOBS          parallel compile jobs (default: from cores and memory)
#   CAFE_SYS_DIR  a Cemu-style mlc01/sys folder from your own Wii U (Mii resources ...), written into the starter
#
# Nothing from the game is downloaded or stored in the repository: the game's code is translated to C++ and
# compiled on your computer, into the build folder. The translated code and the program contain the game's code:
# keep them for yourself.
set -euo pipefail

HERE=$(cd "$(dirname "$0")/.." && pwd)
say() { printf '%s\n   %s\n' "$1" "$2"; }               # German line, English line
step() { printf '\n==> %s\n    %s\n' "$1" "$2"; }
die() { printf '\nFEHLER: %s\nERROR:  %s\n' "$1" "$2" >&2; exit 1; }

[ -f "$HERE/game.conf" ] || die "game.conf fehlt im Repository." "game.conf is missing from the repository."
# shellcheck source=/dev/null
. "$HERE/game.conf"

GAME_IN=${1:-}
[ -n "$GAME_IN" ] || die "Aufruf: native-build.sh SPIELORDNER" "usage: native-build.sh GAME_FOLDER"

# ---- the base this port is built on: Smash 4 PC (MIT), itself built on Petexy's cafe-recomp (MIT) ----------------
BASE_REPO=https://github.com/josiahg2502-glitch/Smash4PC
BASE_COMMIT=f145e7fc14d0be2caf712cc4080f9deb3e7ab6aa
DEPS=(
  "ZArchive https://github.com/Exzap/ZArchive.git 965b66c8d67b6b7e30fd63b3b75aa91a99ff303b"
  "addrlib https://github.com/decaf-emu/addrlib.git 194162c47469ce620dd2470eb767ff5e42f5954a"
  "Vulkan-Headers https://github.com/KhronosGroup/Vulkan-Headers.git b0c3dd6851e22621f194306d511b9253e4c1577f"
)
SDL_TAG=release-3.2.26   # only built when the system has no SDL3 (Linux)

WINDOWS=0
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) WINDOWS=1 ;; esac
EXE=; [ $WINDOWS = 1 ] && EXE=.exe
# Paths handed to native Windows programs (cmake, ninja, the recompiler, Python) as C:/x/y.
P() { if [ $WINDOWS = 1 ]; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
PY=python3; command -v python3 >/dev/null || PY=python

if [ $WINDOWS = 1 ]; then   # paths given from PowerShell (C:\...) as MSYS paths
  GAME_IN=$(cygpath -u "$GAME_IN")
  for v in CAFE_SYS_DIR NATIVE_WORK NATIVE_PLAY; do [ -n "${!v:-}" ] && export "$v=$(cygpath -u "${!v}")"; done
fi
GAME=$(cd "$GAME_IN" 2>/dev/null && pwd) || die "Spielordner nicht gefunden: $GAME_IN" "game folder not found: $GAME_IN"
WORK=${NATIVE_WORK:-$HERE/build}
PLAY=${NATIVE_PLAY:-$HERE/play}
SRC=$WORK/smash4
BLD=$WORK/build
GEN=$WORK/gen
mkdir -p "$WORK" "$GEN"
LOG=$WORK/build.log

# ---- 1. the game dump ----------------------------------------------------------------------------------------------
step "Pruefe den Spielordner: $GAME" "Checking the game folder"
[ -f "$GAME/code/$RPX" ] || die "In $GAME/code fehlt $RPX. Erwartet wird DEIN eigener, entpackter Dump von \"$TITLE\" (Ordner code, content, meta)." \
  "$GAME/code has no $RPX. Expected: YOUR OWN unpacked dump of \"$TITLE\" (folders code, content, meta)."
[ -d "$GAME/content" ] || die "Im Spielordner fehlt content/." "The game folder has no content/."
for m in ${NEEDS_FILES:-}; do
  [ -f "$GAME/code/$m" ] || die "In $GAME/code fehlt $m (gehoert zum Spiel)." "$GAME/code has no $m (part of the game)."
done
if [ -f "$GAME/meta/meta.xml" ]; then
  ID=$(sed -n 's/.*<title_id[^>]*>\([0-9A-Fa-f]*\)<.*/\1/p' "$GAME/meta/meta.xml" | head -1 | tr a-f A-F)
  if [ -n "$ID" ] && [ -n "${TESTED_TITLE_ID:-}" ] && [ "$ID" != "$TESTED_TITLE_ID" ]; then
    say "Hinweis: Dein Dump hat die Titel-ID $ID, getestet wurde $TESTED_TITLE_ID ($TESTED_REGION). Es kann trotzdem gehen." \
        "Note: your dump is title $ID; this was tested with $TESTED_TITLE_ID ($TESTED_REGION). It may still work."
  fi
fi

# ---- 2. tools ------------------------------------------------------------------------------------------------------
for t in git cmake ninja clang clang++ $PY; do
  command -v "$t" >/dev/null || die "Werkzeug fehlt: $t (setup-linux.sh / setup-windows.ps1 installieren es)." \
    "missing tool: $t (setup-linux.sh / setup-windows.ps1 install it)."
done
if [ -z "${JOBS:-}" ]; then
  CORES=$(nproc 2>/dev/null || echo 4)
  MEM_GB=$(awk '/MemTotal/ {printf "%d", $2 / 1048576}' /proc/meminfo 2>/dev/null || echo 8)
  JOBS=$(( CORES < MEM_GB * 2 / 3 ? CORES : MEM_GB * 2 / 3 )); [ "$JOBS" -ge 1 ] || JOBS=1
fi

# ---- 3. runtime + recompiler at the tested version, with this port's changes -----------------------------------
step "Hole die Grundlage (Smash4PC ${BASE_COMMIT:0:7}) und wende die Aenderungen dieses Ports an" \
     "Fetching the base (Smash4PC ${BASE_COMMIT:0:7}) and applying this port's changes"
PATCH=$HERE/port/upstream-local.patch
[ -f "$PATCH" ] || die "port/upstream-local.patch fehlt." "port/upstream-local.patch is missing."
if [ ! -d "$SRC/.git" ]; then
  git -c core.autocrlf=false clone --quiet --no-checkout "$BASE_REPO" "$SRC" \
    || die "git clone von $BASE_REPO ging nicht (Internet?)." "git clone of $BASE_REPO failed (internet?)."
fi
git -C "$SRC" config core.autocrlf false
WANT="$(git hash-object "$PATCH") $WINDOWS"
if [ "$(cat "$SRC/.native-patch" 2>/dev/null)" != "$WANT" ]; then
  git -C "$SRC" cat-file -e "$BASE_COMMIT^{commit}" 2>/dev/null || git -C "$SRC" fetch --quiet origin
  git -C "$SRC" reset --quiet --hard "$BASE_COMMIT" || die "Stand $BASE_COMMIT nicht gefunden." "commit $BASE_COMMIT not found."
  # The patch is applied as bytes (LF), whatever the checkout of this repository did to line endings.
  tr -d '\r' < "$PATCH" > "$WORK/upstream-local.patch"
  git -C "$SRC" apply --whitespace=nowarn "$WORK/upstream-local.patch" \
    || die "Die Aenderungen (upstream-local.patch) passen nicht auf die Grundlage." "upstream-local.patch does not apply to the base."
  if [ $WINDOWS = 1 ]; then
    # Windows: libraries come from MSYS2's CLANG64 instead of Smash4PC's own dependency build.
    sed -i "s#set(CAFE_DEPS_PREFIX \${CMAKE_SOURCE_DIR}/build-deps/prefix)#set(CAFE_DEPS_PREFIX $(cygpath -m /clang64))#" "$SRC/CMakeLists.txt"
  fi
  echo "$WANT" > "$SRC/.native-patch"
fi
for d in "${DEPS[@]}"; do
  set -- $d
  dir=$SRC/third_party/$1
  if [ "$(git -C "$dir" rev-parse HEAD 2>/dev/null)" != "$3" ]; then
    rm -rf "$dir"; mkdir -p "$dir"; git -C "$dir" init -q
    git -C "$dir" -c core.autocrlf=false fetch -q --depth 1 "$2" "$3" && git -C "$dir" -c core.autocrlf=false checkout -q FETCH_HEAD \
      || die "Konnte $1 nicht holen ($2)." "could not fetch $1 ($2)."
  fi
done
ZW=$SRC/third_party/ZArchive/src/zarchivewriter.cpp   # needs <cstdlib> with MinGW's headers
grep -q '^#include <cstdlib>' "$ZW" || sed -i '1i #include <cstdlib>' "$ZW"

# ---- 4. SDL3 (Linux only, when the system has none) ---------------------------------------------------------------
CMAKE_ARGS=(-G Ninja -Wno-dev -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++
            "-DCMAKE_CXX_FLAGS=${CXX_DEFINES:-}")
if [ $WINDOWS = 1 ]; then
  CMAKE_ARGS+=("-DVulkan_LIBRARY=$(cygpath -m /clang64/lib/libvulkan-1.dll.a)")
else
  CMAKE_ARGS+=("-DVulkan_INCLUDE_DIR=$SRC/third_party/Vulkan-Headers/include")
  SHADERC=
  for f in $(ldconfig -p 2>/dev/null | awk '/libshaderc(_shared)?\.so /{print $NF}') \
           /usr/lib/x86_64-linux-gnu/libshaderc_shared.so /usr/lib/x86_64-linux-gnu/libshaderc.so \
           /usr/lib64/libshaderc_shared.so /usr/lib64/libshaderc.so /usr/lib/libshaderc_shared.so /usr/lib/libshaderc.so; do
    [ -f "$f" ] && { SHADERC=$f; break; }
  done
  [ -n "$SHADERC" ] || die "libshaderc nicht gefunden (Paket libshaderc-dev / shaderc)." "libshaderc not found (package libshaderc-dev / shaderc)."
  CMAKE_ARGS+=("-DSHADERC_LIBRARY=$SHADERC")
  if ! pkg-config --exists sdl3 2>/dev/null && [ ! -f "$WORK/sdl/lib/cmake/SDL3/SDL3Config.cmake" ]; then
    step "Baue SDL3 ($SDL_TAG), weil das System keins hat" "Building SDL3 ($SDL_TAG): the system has none"
    rm -rf "$WORK/SDL"
    git clone --quiet --depth 1 -b "$SDL_TAG" https://github.com/libsdl-org/SDL.git "$WORK/SDL"
    cmake -S "$WORK/SDL" -B "$WORK/SDL/build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$WORK/sdl" \
      -DSDL_TESTS=OFF -DSDL_EXAMPLES=OFF > "$WORK/sdl.log" 2>&1 && nice ninja -C "$WORK/SDL/build" -j"$JOBS" install >> "$WORK/sdl.log" 2>&1 \
      || die "SDL3 liess sich nicht bauen, siehe $WORK/sdl.log" "SDL3 failed to build, see $WORK/sdl.log"
  fi
  [ -f "$WORK/sdl/lib/cmake/SDL3/SDL3Config.cmake" ] && CMAKE_ARGS+=("-DCMAKE_PREFIX_PATH=$WORK/sdl")
fi

# Long builds: show one progress line every 20 s, everything else into the log.
run_ninja() { # target
  : > "$LOG.part"
  nice ninja -C "$(P "$BLD")" -j"$JOBS" "$1" > "$LOG.part" 2>&1 &
  local pid=$! last=
  while kill -0 $pid 2>/dev/null; do
    sleep 20
    last=$(grep -o '^\[[0-9]*/[0-9]*\]' "$LOG.part" | tail -1 || true)
    [ -n "$last" ] && printf '    %s %s\n' "$last" "$(date +%H:%M:%S)"
  done
  local rc=0; wait $pid || rc=$?
  cat "$LOG.part" >> "$LOG"
  if [ $rc != 0 ]; then
    grep -E 'error|FAILED' "$LOG.part" | head -20 >&2 || true
    die "Bauen von $1 fehlgeschlagen, ganzes Protokoll: $LOG" "building $1 failed, full log: $LOG"
  fi
}

step "Baue den Uebersetzer (cafe-recomp)" "Building the recompiler (cafe-recomp)"
: > "$LOG"
cmake -S "$(P "$SRC")" -B "$(P "$BLD")" "${CMAKE_ARGS[@]}" >> "$LOG" 2>&1 \
  || { tail -20 "$LOG" >&2; die "cmake fehlgeschlagen, siehe $LOG" "cmake failed, see $LOG"; }
run_ninja cafe-recomp
RECOMP=$BLD/recomp/cafe-recomp$EXE

# ---- 5. translate the game's code (from your dump) --------------------------------------------------------------
recomp() { # env... -- rpx out args...
  local envs=()
  while [ "$1" != -- ]; do envs+=("$1"); shift; done; shift
  local rpx=$1 out=$2; shift 2
  env "${envs[@]}" "$RECOMP" "$(P "$rpx")" "$(P "$out")" "$@" > "$WORK/recomp.log" 2>&1 \
    || { tail -5 "$WORK/recomp.log" >&2; die "Uebersetzen von $(basename "$rpx") fehlgeschlagen." "translating $(basename "$rpx") failed."; }
  grep '^entries' "$WORK/recomp.log" | sed 's/^/    /'
}
step "Uebersetze den Code des Spiels nach C++ (aus deinem Dump)" "Translating the game's code to C++ (from your dump)"
EXTRA_SRC="$(P "$HERE/port/netplay_none.cpp");$(P "$HERE/port/os_extra.cpp")"
MODULE_DIRS=
RENV=()
[ -n "${RECOMP_ENTRIES_FILE:-}" ] && RENV+=("CAFE_EXTRA_ENTRIES=$(tr -d '\r\n' < "$HERE/$RECOMP_ENTRIES_FILE" | sed 's/^CAFE_EXTRA_ENTRIES=//')")
[ -n "${RECOMP_ENTRIES:-}" ] && RENV+=("CAFE_EXTRA_ENTRIES=$RECOMP_ENTRIES")
rm -f "$WORK/data-imports.map" "$WORK/module-imports.map"
case "${MODULES:-}" in
  "")
    recomp "${RENV[@]}" -- "$GAME/code/$RPX" "$GEN/main" $RECOMP_ARGS
    ;;
  mk8)
    # Mario Kart 8: its video player module mvplayer.rpl is translated at free addresses (code +0x06000000,
    # data +0x00300000) and loaded by port/modules.cpp; the game's data imports from it come from a map
    # written from YOUR mvplayer.rpl (tools/make_data_imports.py).
    recomp CAFE_RPL_REBASE=06000000,00300000 CAFE_DATA_IMPORT_FIRST=32 -- "$GAME/code/mvplayer.rpl" "$GEN/mvplayer" --any-rpx --all
    $PY "$(P "$HERE/port/module_rename.py")" "$(P "$GEN/mvplayer")" mvplayer
    $PY "$(P "$HERE/tools/make_data_imports.py")" "$(P "$GAME/code/mvplayer.rpl")" 00300000 "$(P "$WORK/data-imports.map")"
    recomp "CAFE_DATA_IMPORT_MAP=$(P "$WORK/data-imports.map")" -- "$GAME/code/$RPX" "$GEN/main" $RECOMP_ARGS
    MODULE_DIRS=$(P "$GEN/mvplayer")
    EXTRA_SRC="$EXTRA_SRC;$(P "$HERE/port/modules.cpp")"
    ;;
  mp10)
    # Mario Party 10: the title plus 91 modules it loads at run time. Every module gets a fixed address range
    # (port/mp10_layout.py), is translated there and linked to the title (port/mp10_link.py); the module table
    # and the import map are generated here from YOUR files.
    recomp -- "$GAME/code/$RPX" "$GEN/main" $RECOMP_ARGS
    $PY "$(P "$HERE/port/mp10_link.py")" map "$(P "$GAME/code/$RPX")" "$(P "$GEN/main")" "$(P "$WORK/module-imports.map")" | sed 's/^/    /'
    $PY "$(P "$HERE/port/mp10_layout.py")" "$(P "$GAME/code")" --csv "$(P "$WORK/mp10-layout.csv")" | tail -1 | sed 's/^/    /'
    n=0
    while IFS=, read -r name cb cs db ds cdel ddel; do
      [ "$name" = "#end" ] && continue
      recomp "CAFE_RPL_REBASE=$cdel,$ddel" "CAFE_DATA_IMPORT_MAP=$(P "$WORK/module-imports.map")" CAFE_DATA_IMPORT_FIRST=100 -- \
        "$GAME/code/$name.rpl" "$GEN/mp10-$name" --any-rpx --all > /dev/null
      $PY "$(P "$HERE/port/module_rename.py")" "$(P "$GEN/mp10-$name")" "$name" > /dev/null
      MODULE_DIRS="$MODULE_DIRS${MODULE_DIRS:+;}$(P "$GEN/mp10-$name")"
      n=$((n + 1))
    done < "$WORK/mp10-layout.csv"
    echo "    $n Module uebersetzt / modules translated"
    $PY "$(P "$HERE/port/mp10_link.py")" gen "$(P "$GAME/code/$RPX")" "$(P "$GEN/main")" "$(P "$GEN")" "$(P "$WORK/mp10-layout.csv")" \
      "$(P "$WORK/mp10_modules_gen.cpp")" | head -3 | sed 's/^/    /'
    cp "$HERE/port/mp10_modules.h" "$WORK/"
    EXTRA_SRC="$EXTRA_SRC;$(P "$HERE/port/modules_dyn.cpp");$(P "$WORK/mp10_modules_gen.cpp");$(P "$HERE/port/mp10_fibers.cpp")"
    ;;
  *) die "Unbekanntes MODULES=$MODULES in game.conf" "unknown MODULES=$MODULES in game.conf" ;;
esac

if [ -n "${NATIVE_ONLY_TRANSLATE:-}" ]; then   # for checking the translation step alone
  say "Nur uebersetzt (NATIVE_ONLY_TRANSLATE): $GEN" "Translated only (NATIVE_ONLY_TRANSLATE): $GEN"; exit 0
fi

# ---- 6. compile ----------------------------------------------------------------------------------------------------
step "Kompiliere Laufzeit + uebersetztes Spiel mit $JOBS Jobs (dauert: ${BUILD_MINUTES:-10-30} Minuten)" \
     "Compiling the runtime + translated game with $JOBS jobs (takes ${BUILD_MINUTES:-10-30} minutes)"
cmake -S "$(P "$SRC")" -B "$(P "$BLD")" "${CMAKE_ARGS[@]}" "-DGAME_GENERATED_DIR=$(P "$GEN/main")" \
  "-DGAME_MAIN=$(P "$HERE/port/game_main.cpp")" "-DGAME_EXTRA=$EXTRA_SRC" "-DGAME_MODULE_DIRS=$MODULE_DIRS" >> "$LOG" 2>&1 \
  || { tail -20 "$LOG" >&2; die "cmake fehlgeschlagen, siehe $LOG" "cmake failed, see $LOG"; }
run_ninja cafegame

# ---- 7. the folder you play from -------------------------------------------------------------------------------------
step "Stelle den Spielordner zusammen: $PLAY" "Putting the play folder together: $PLAY"
mkdir -p "$PLAY/fonts" "$PLAY/save"
cp -f "$BLD/cafegame$EXE" "$PLAY/"
[ -f "$WORK/data-imports.map" ] && cp -f "$WORK/data-imports.map" "$PLAY/"
[ -f "$WORK/module-imports.map" ] && cp -f "$WORK/module-imports.map" "$PLAY/"
# The Wii U's system font is not part of a game dump: a free font stands in (put your console's CafeStd.ttf
# into play/fonts to replace it; it is never overwritten).
if [ ! -f "$PLAY/fonts/CafeStd.ttf" ]; then
  for f in /clang64/share/fonts/TTF/DejaVuSans.ttf /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf \
           /usr/share/fonts/TTF/DejaVuSans.ttf /usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf /usr/share/fonts/dejavu/DejaVuSans.ttf; do
    [ -f "$f" ] && { cp "$f" "$PLAY/fonts/CafeStd.ttf"; break; }
  done
  [ -f "$PLAY/fonts/CafeStd.ttf" ] || say "Hinweis: keine DejaVuSans.ttf gefunden - Texte im Spiel fehlen, bis eine Schrift in play/fonts/CafeStd.ttf liegt." \
                                          "Note: no DejaVuSans.ttf found - in-game text stays empty until a font is in play/fonts/CafeStd.ttf."
fi
SYS=${CAFE_SYS_DIR:-}
if [ -n "$SYS" ]; then
  SYS=$(cd "$SYS" 2>/dev/null && pwd) || die "CAFE_SYS_DIR/-SysDir nicht gefunden: $CAFE_SYS_DIR" "CAFE_SYS_DIR/-SysDir not found: $CAFE_SYS_DIR"
  for t in ${SYS_TITLES:-}; do
    [ -d "$SYS/title/0005001b/$t" ] || [ -d "$SYS/title/0005001B/$t" ] || [ -d "$SYS/title/0005001b/$(echo "$t" | tr a-f A-F)" ] || \
      say "Hinweis: $SYS hat kein title/0005001b/$t." "Note: $SYS has no title/0005001b/$t."
  done
fi
if [ $WINDOWS = 1 ]; then
  # The libraries the program loads, from MSYS2 (not Windows' own and not vulkan-1.dll: that is the graphics driver's).
  queue=("$PLAY/cafegame.exe"); seen=" "
  while [ ${#queue[@]} -gt 0 ]; do
    f=${queue[0]}; queue=("${queue[@]:1}")
    for dll in $(objdump -p "$f" | sed -n 's/^\s*DLL Name: \(.*\)$/\1/p' | tr -d '\r'); do
      lower=$(echo "$dll" | tr A-Z a-z)
      case "$seen" in *" $lower "*) continue ;; esac
      seen="$seen$lower "
      [ "$lower" = vulkan-1.dll ] && continue
      [ -f "/clang64/bin/$dll" ] || continue
      cp -f "/clang64/bin/$dll" "$PLAY/"; queue+=("/clang64/bin/$dll")
    done
  done
  [ -f /clang64/bin/liblzma-5.dll ] && cp -f /clang64/bin/liblzma-5.dll "$PLAY/"   # loaded at run time (lzma)
  # Start-Datei / starter
  {
    printf '@echo off\r\nchcp 65001 >nul\r\ncd /d "%%~dp0"\r\n'
    printf 'rem %s - native build (made by setup-windows.ps1). Log: cafegame.log\r\n' "$TITLE"
    printf 'set "CAFE_SAVE_DIR=%%~dp0save"\r\n'
    [ -n "$SYS" ] && printf 'if not defined CAFE_SYS_DIR set "CAFE_SYS_DIR=%s"\r\n' "$(cygpath -w "$SYS")"
    for e in ${START_ENV:-}; do printf 'set "%s"\r\n' "$e"; done
    printf 'echo %s laeuft / is running ... (Log: cafegame.log)\r\n' "$TITLE"
    printf 'cafegame.exe "%s" > cafegame.log 2>&1\r\n' "$(cygpath -w "$GAME")"
    printf 'if errorlevel 1 (echo Beendet mit Fehler / ended with an error - siehe/see cafegame.log & pause)\r\n'
  } > "$PLAY/Start.bat"
  STARTER="$PLAY/Start.bat"
else
  if [ -f "$WORK/sdl/lib/libSDL3.so.0" ]; then mkdir -p "$PLAY/lib"; cp -af "$WORK"/sdl/lib/libSDL3.so* "$PLAY/lib/"; fi
  {
    echo '#!/bin/bash'
    echo "# $TITLE - native build (made by setup-linux.sh). Log: cafegame.log"
    echo 'cd "$(dirname "$0")"'
    echo 'export LD_LIBRARY_PATH="$PWD/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"'
    echo 'export CAFE_SAVE_DIR="${CAFE_SAVE_DIR:-$PWD/save}"'
    [ -n "$SYS" ] && printf 'export CAFE_SYS_DIR="${CAFE_SYS_DIR:-%s}"\n' "$SYS"
    for e in ${START_ENV:-}; do echo "export ${e%%=*}=\"\${${e%%=*}:-${e#*=}}\""; done
    printf './cafegame %q 2>&1 | tee cafegame.log\n' "$GAME"
  } > "$PLAY/start.sh"
  chmod +x "$PLAY/start.sh" "$PLAY/cafegame"
  STARTER="$PLAY/start.sh"
fi

echo
say "Fertig. Starte das Spiel mit: $STARTER" "Done. Start the game with: $STARTER"
if [ -n "${SYS_TITLES:-}" ] && [ -z "$SYS" ]; then
  say "${SYS_NOTE_DE:-Hinweis: Ohne Systemdateien deiner Wii U (CAFE_SYS_DIR) fehlen Teile wie Miis.}" \
      "${SYS_NOTE_EN:-Note: without system files from your own Wii U (CAFE_SYS_DIR) parts such as Miis are missing.}"
fi
