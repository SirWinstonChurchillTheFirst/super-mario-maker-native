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

See `port/setup.sh`, `tools/win_build.sh` and `console/deploy.sh`. Translate with
`CAFE_EXTRA_ENTRIES=0272B9A4 cafe-recomp Block.rpx gen/maker --any-rpx`, build the runtime with the patches applied
and run with the switches in `console/maker.game.env`. The system font is not part of a game dump: copy your
console's `CafeStd.ttf` to `build-NAME/fonts/`.

## License

The files here are under the MIT license, as the projects they build on. Third-party code keeps its own license.
