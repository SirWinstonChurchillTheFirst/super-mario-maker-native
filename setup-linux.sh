#!/bin/bash
# Baut die native Linux-Version dieses Spiels aus DEINEM EIGENEN Dump.
# Builds the native Linux version of this game from YOUR OWN game dump.
#
#   ./setup-linux.sh "/pfad/zu/deinem/Spiel"            (Ordner mit code/ content/ meta/)
#   ./setup-linux.sh "/path/to/your/game" --sys "/path/to/mlc01/sys"   (optional: system files of YOUR Wii U)
#
# Nothing from the game is downloaded or stored in this repository: the game's code is translated and compiled
# on your PC, into ./build; ./play/start.sh starts it.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
GAME=; SYS=
while [ $# -gt 0 ]; do
  case "$1" in
    --sys) SYS=${2:?--sys braucht einen Ordner / needs a folder}; shift 2 ;;
    --jobs) export JOBS=${2:?}; shift 2 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) GAME=$1; shift ;;
  esac
done
. "$HERE/game.conf"
if [ -z "$GAME" ]; then
  printf 'Wo liegt dein entpackter Dump von "%s" (Ordner mit code, content, meta)?\nWhere is your unpacked dump of "%s" (folder with code, content, meta)?\n> ' "$TITLE" "$TITLE"
  read -r GAME
fi
[ -n "$GAME" ] || { echo "Kein Spielordner angegeben / no game folder given"; exit 1; }
[ "$(uname -m)" = x86_64 ] || { echo "Nur fuer x86-64 / x86-64 only"; exit 1; }
grep -qw avx2 /proc/cpuinfo || echo "Warnung/warning: dein Prozessor hat kein AVX2 - das Programm braucht x86-64-v3 (AVX2, FMA)."

# 1. Build tools and libraries.
SUDO=sudo; [ "$(id -u)" = 0 ] && SUDO=   # root (container/chroot): no sudo
need_cmds() { for c in clang clang++ cmake ninja git python3 pkg-config; do command -v $c >/dev/null || return 0; done; return 1; }
if command -v apt-get >/dev/null; then
  PKGS="clang cmake ninja-build git python3 pkg-config zlib1g-dev libzstd-dev libssl-dev libvulkan-dev libshaderc-dev fonts-dejavu-core"
  # SDL3 from the system where it exists (Ubuntu 25.04+, Debian 13+), otherwise built from source with these:
  if apt-cache show libsdl3-dev >/dev/null 2>&1; then PKGS="$PKGS libsdl3-dev"; else
    PKGS="$PKGS libx11-dev libxext-dev libxrandr-dev libxcursor-dev libxi-dev libxss-dev libxtst-dev libxkbcommon-dev
          libwayland-dev wayland-protocols libdecor-0-dev libegl-dev libasound2-dev libpulse-dev libpipewire-0.3-dev libudev-dev libdbus-1-dev"
  fi
  MISSING=$(for p in $PKGS; do dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q 'install ok installed' || echo "$p"; done)
  if [ -n "$MISSING" ]; then
    echo "Installiere fehlende Pakete (braucht sudo) / installing missing packages (needs sudo):" $MISSING
    $SUDO apt-get install -y $MISSING
  fi
elif command -v pacman >/dev/null; then
  PKGS="clang cmake ninja git python pkgconf zlib zstd openssl vulkan-icd-loader shaderc sdl3 ttf-dejavu"
  MISSING=$(pacman -T $PKGS || true)
  [ -n "$MISSING" ] && { echo "Installiere / installing:" $MISSING; $SUDO pacman -S --needed --noconfirm $MISSING; }
elif command -v dnf >/dev/null; then
  PKGS="clang cmake ninja-build git python3 pkgconf-pkg-config zlib-devel libzstd-devel openssl-devel vulkan-loader-devel libshaderc-devel SDL3-devel dejavu-sans-fonts"
  MISSING=$(for p in $PKGS; do rpm -q "$p" >/dev/null 2>&1 || echo "$p"; done)
  [ -n "$MISSING" ] && { echo "Installiere / installing:" $MISSING; $SUDO dnf install -y $MISSING; }
elif need_cmds; then
  echo "Bitte installiere / please install: clang cmake ninja git python3 pkg-config, zlib, zstd, OpenSSL 3, Vulkan loader, shaderc, SDL3 (dev packages), DejaVu fonts"
  exit 1
fi

# 2. Translate + compile (shared with the Windows setup).
[ -n "$SYS" ] && export CAFE_SYS_DIR="$SYS"
exec bash "$HERE/tools/native-build.sh" "$GAME"
