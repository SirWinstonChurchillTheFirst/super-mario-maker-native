#!/bin/bash
# run_gpu.sh NAME "GAME FOLDER" SECONDS "INPUT SCRIPT" [TAG] : run win/build-NAME/cafegame.exe on the PC's graphics card
# (Git Bash), window at 1280x720, a TV picture every 3 s, sound to a WAV, frame pacing lines; then a contact sheet
# D:\retro\screenshots\wiiurecomp\NAME-TAG-sheet.jpg and a short summary.
NAME=$1; GAME=$2; SECS=${3:-45}; INPUT=$4; TAG=${5:-gpu}
ROOT=/d/retro/wiiurecomp/win; RUN=$ROOT/run/$NAME
mkdir -p "$RUN/save" "$RUN/cap-$TAG"; rm -f "$RUN/cap-$TAG"/*.png
PY=$(command -v python)   # the Windows Python (has PIL), found before the compiler tools come first on PATH
export PATH="/c/msys64/clang64/bin:$PATH"
cd "$RUN" || exit 1
W=$(cygpath -m "$RUN")
# Pictures of the window itself too (the runtime's own capture saves nothing for some titles).
# NOWINCAP=1: no window photos (each one holds the window for ~0.1 s, which shows as late pictures in the pacing numbers)
[ -n "$NOWINCAP" ] || "$PY" /d/retro/wiiurecomp/tools/wincap_loop.py cafegame.exe "$W/cap-$TAG" ${INTERVAL:-3} $((SECS / ${INTERVAL:-3})) > wincap-$TAG.log 2>&1 &
CAFE_SAVE_DIR="$W/save" TTT2_SCALE=1 TTT2_CAPTURE="$W/cap-$TAG" TTT2_CAPTURE_INTERVAL=${INTERVAL:-3} TTT2_CAPTURE_TV_ONLY=1 \
  TTT2_TRACE_PACING=1 TTT2_TRACE_FS=${TRACEFS:-}  TTT2_AUDIO_DUMP="$W/audio-$TAG.wav" TTT2_INPUT_SCRIPT="$INPUT" \
  timeout $SECS "$ROOT/build-$NAME/cafegame.exe" "$(cygpath -m "$GAME")" > $TAG.log 2>&1
echo "RC=$? (124 = still running when the time was up)"; wait
grep -n "does not implement\|fault\|fatal\|^port: \|erreula\|GPU: NVIDIA" $TAG.log | cut -c1-200 | head -12
grep "^ttt2: present:" $TAG.log | tail -2 | cut -c1-200
grep "^pacing" $TAG.log | tail -2 | cut -c1-160
"$PY" - "$(cygpath -m "$RUN")" "$NAME" "$TAG" <<'PY'
import sys, glob, wave, array
from PIL import Image
run, name, tag = sys.argv[1:4]
fs = sorted(glob.glob(f'{run}/cap-{tag}/tv_*.png')) or sorted(glob.glob(f'{run}/cap-{tag}/win_*.png'))
if fs:
    cols = 4; rows = (len(fs) + cols - 1) // cols
    sheet = Image.new('RGB', (480 * cols, 270 * rows))
    for i, f in enumerate(fs):
        sheet.paste(Image.open(f).convert('RGB').resize((480, 270)), ((i % cols) * 480, (i // cols) * 270))
    out = f'D:/retro/screenshots/wiiurecomp/{name}-{tag}-sheet.jpg'
    sheet.save(out, quality=85); print(len(fs), 'pictures ->', out)
else:
    print('no pictures')
try:
    w = wave.open(f'{run}/audio-{tag}.wav'); n = w.getnframes()
    a = array.array('h', w.readframes(n)); sr = w.getframerate() * w.getnchannels()
    parts = [a[s:s + sr * 5] for s in range(0, len(a), sr * 5)]
    print('sound, RMS per 5 s:', [int((sum(x * x for x in p) / len(p)) ** .5) for p in parts if len(p)])
except Exception as e:
    print('sound: no dump', e)
PY
