# Super Mario Maker (Wii U) – native (recompiled) build scripts

Scripts and runtime patches that turn **your own** dump of *Super Mario Maker* (Wii U, `Block.rpx`) into a native
Linux/Windows program with a static recompiler. No emulator. No game code, game data or Nintendo system files are in
this repository; you need your own dump (Europe), unpacked to `code/`, `content/`, `meta/`.

> The translated C++ and the program built from it contain the game's code: do not share them.
> Not affiliated with or endorsed by Nintendo.

**Miis.** The game asks for the Wii U's Mii resources (system title `0005001B-10056000`). They are **not** part of the
game and **not** included here: point `CAFE_SYS_DIR` at a Cemu-style `mlc01/sys` folder holding
`title/0005001b/10056000/content/` from your own Wii U.

Base: [Smash4PC](https://github.com/josiahg2502-glitch/Smash4PC) at `f145e7f` (MIT; built on Petexy's cafe-recomp and
Wii U runtime from [Tekken Tag 2 Ultimate Edition](https://github.com/Petexy/Tekken-Tag-2-Ultimate-Edition), MIT).
All credit for the recompiler and the runtime goes to them. `port/upstream-local.patch` is the full local diff against
it; the `port/patch_*.py` scripts are the same changes one by one (each script's header says what it fixes).

## Selbst bauen / Build it yourself

One command builds the native program from **your own dump** of Super Mario Maker. Nothing from the game is in this repository
or downloaded by the scripts: the game's code (Block.rpx) is translated to C++ and compiled on your computer.
*Ein Befehl baut das native Programm aus deinem eigenen Dump; nichts vom Spiel ist hier enthalten oder wird geladen.*

**You need / Du brauchst**
- your own dump of the game, **unpacked**: a folder with `code/`, `content/`, `meta/` (as Cemu or a Wii U dumper
  such as Dumpling gives it; `.wua`/`.wud` images must be unpacked first). Tested with Europe
  (000500001018DD00); other versions are translated from your files the same way and may work.
- Windows 10/11 64-bit or Linux x86-64; a CPU with AVX2/FMA (Intel Haswell, AMD Zen or newer); a GPU with a Vulkan driver.
- internet for the build tools and the pinned sources (Smash4PC `f145e7f`, ZArchive, addrlib, Vulkan-Headers from GitHub).
- about **2 GB** free in this folder (plus about 3 GB for MSYS2 on Windows) and 8 GB of RAM or more.
- time: about **5-15 minutes** for the first build on an 8-core PC; a second run only redoes what changed.

**Miis / Mii-Dateien.** Visible Miis need the Mii resource title (`0005001B-10056000`, files `FFLRes*.dat`) from **your own Wii U** — it is not part of the game, not in this repository and never downloaded. This game does not get far without it. Give the setup a Cemu-style `mlc01/sys` folder that holds `title/0005001b/10056000/content/` (`-SysDir` on Windows, `--sys` on Linux); it is written into the starter as `CAFE_SYS_DIR` and only read.
*Deutsch:* Sichtbare Miis brauchen den Mii-Systemtitel deiner **eigenen** Wii U (z. B. aus Cemus `mlc01/sys`), angegeben mit `-SysDir` bzw. `--sys`. Er ist nicht im Spiel-Dump und nicht hier enthalten.

**Windows** (PowerShell):

```powershell
git clone https://github.com/SirWinstonChurchillTheFirst/super-mario-maker-native
cd super-mario-maker-native
powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1 -GameDir "D:\Games\Super Mario Maker" -SysDir "D:\Cemu\mlc01\sys"
.\play\Start.bat
```

It installs [MSYS2](https://www.msys2.org) with winget if it is missing and the build packages into its CLANG64
environment with pacman (clang, lld, cmake, ninja, Python, git, SDL3, Vulkan loader + headers, shaderc, zlib, zstd,
xz, DejaVu fonts). Without `-GameDir` it asks for the folder. `-Jobs N` limits the parallel compile jobs; the build
runs at low priority so the PC stays usable.

**Linux** (Debian/Ubuntu, Arch, Fedora; others: install the same packages yourself):

```bash
git clone https://github.com/SirWinstonChurchillTheFirst/super-mario-maker-native
cd super-mario-maker-native
./setup-linux.sh "/path/to/Super Mario Maker" --sys ~/.local/share/Cemu/mlc01/sys
./play/start.sh
```

Missing packages are installed with sudo (apt: clang cmake ninja-build git python3 pkg-config zlib1g-dev libzstd-dev
libssl-dev libvulkan-dev libshaderc-dev fonts-dejavu-core, and libsdl3-dev where the distribution has it; without it
SDL 3.2.26 is built from source, e.g. on Ubuntu 24.04). `--jobs N` limits the compile jobs.

**What the setup does** (`tools/native-build.sh`, the same on both systems): checks your dump; clones
[Smash4PC](https://github.com/josiahg2502-glitch/Smash4PC) at `f145e7f` and the three pinned dependencies; applies
`port/upstream-local.patch` (all runtime/recompiler changes, made by the `port/patch_*.py` scripts in order); builds the
recompiler `cafe-recomp`; translates your `code/`; compiles runtime + translated game; and puts `cafegame`, a stand-in
font and the starter into `play/`. Everything it makes stays in `build/` and `play/` (both ignored by git): they hold
code translated from the game — **keep them for yourself, do not share them.**

The starter sets `TTT2_SHOW_GAMEPAD=1 CAFE_TOUCH_UI=1 TTT2_RELOAD_TARGETS=1` for this game (see the comments in `game.conf`); any of them can be overridden by setting it before starting.

The Wii U system font is not part of a game dump: DejaVu Sans stands in (`play/fonts/CafeStd.ttf`); put your console's
own `CafeStd.ttf` there to replace it. Saves go to `play/save/`. The system language follows your PC
(`CAFE_LANGUAGE=de|en|fr|...` overrides it).

**Getestet / tested (23 Nov 2026):** For this game the Windows setup's translation step was run on the tested dump: it gives the same code as the build that runs on the Batocera console (only the newer recompiler's `dcbf` lines differ); the complete build of this game through the scripts was not run yet. The same scripts were run end to end from an empty folder on 23 November 2026: Lost Levels and Mario Kart 8 on Windows 11, Lost Levels on Ubuntu 26.04 and on a fresh Ubuntu 24.04 (SDL3 built from source there), Mario Party 10 on Windows 11.

## State (23 November 2026)

Intro course plays, touching "Bauen!" opens the editor with its tutorial. PC (GeForce) and console (Batocera on a
Ryzen 3 4350GE / Vega 6, 1280x720): 59-60 frames/s, console CPU 64 C / GPU 58 C. Online/Miiverse: not available.

## What this title needed

- **Clears in window pixels.** Maker clears with its own rectangle draw under `GX2SetSpecialState(Clear)` (viewport
  transform off); the runtime only knew the copy state (`patch_special_clear.py`, `patch_vte_window.py`). Before
  that only the top-right quarter of the scene was drawn and every second frame was black.
- **Geometry shaders** (ground and terrain): the runtime had none; ES -> GS -> copy shader translation
  (`patch_gs.py`).
- A stale 8x8 colour target clipped the depth clear (`patch_tiny_color.py`); the tile atlas has CPU-written parts
  (`patch_reload_targets.py`, `TTT2_RELOAD_TARGETS=1`).
- **GamePad picture**: the title passes the GamePad colour buffer with zero register words
  (`patch_scancopy_regs.py`).
- **Touch screen** (`patch_touch_ui.py`): the GamePad picture can be shown in the window (`TTT2_SHOW_GAMEPAD=1`,
  F9 / left stick click with `CAFE_TOUCH_UI=1`); mouse = touch, or right stick = cursor and ZR / right stick click =
  touch.
- `GX2PatchDisplayList` (decaf-style, `port/os_extra.cpp`), an extra function entry for the recompiler
  (`patch_extra_entries.py`, `CAFE_EXTRA_ENTRIES=0272B9A4`), `AXDecodeAdpcmData`, vertex fetch const fields
  (`patch_vtx_const_fields.py`).
- **Speed on the console**: amdgpu re-walks an imported host pointer on every submission; guest memory as exportable
  GPU memory (`patch_guest_dmabuf.py`, `TTT2_GUEST_DMABUF=1`) took the command thread from 11 to 2.6 ms a frame.
  Only the used uniform registers are copied (`patch_reg_extent.py`).

## Use

Build it with the setup scripts (above); by hand: translate with
`CAFE_EXTRA_ENTRIES=0272B9A4 cafe-recomp Block.rpx gen/maker --any-rpx`, build the runtime with the patches applied
and run with the switches in `console/maker.game.env`.

## License

The files here are under the MIT license, as the projects they build on. Third-party code keeps its own license.
