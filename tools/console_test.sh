#!/bin/bash
# console_test.sh NAME "TITLE" SECONDS "INPUT SCRIPT" [TAG] [host]: one scripted run of a Wii U port ON THE CONSOLE,
# started through the menu's interface (as the player starts it), with a test save folder, pictures of the
# screen every 20 s, the sound stream at the end, frame pacing lines in the log. Afterwards the game is ended,
# the test switches are removed and a picture shows what the console is left in (must be Nova Home).
# Refuses when a game is already running there (the player may be playing).
NAME=$1; TITLE=$2; SECS=${3:-120}; INPUT=$4; TAG=${5:-c1}; H=${6:-root@192.168.178.107}
OUT=/d/retro/wiiurecomp/console/run/$NAME-$TAG; mkdir -p "$OUT"
# One run at a time: a second run's "end the game" hit the first run's game on 19 November and left Alt+F4 held
# on the virtual hotkey keyboard (every game then closed 3 s after its start, until "xinput disable/enable").
mkdir /tmp/wiiu-console-test.lock 2>/dev/null || { echo "stop: another console_test.sh is running (or remove /tmp/wiiu-console-test.lock)"; exit 1; }
trap 'rmdir /tmp/wiiu-console-test.lock 2>/dev/null' EXIT
B=/userdata/ports-native/wiiu/$NAME
# Temperature guard (lost at every reboot): copied up, then a pause (dropbear throttles quick logins).
scp -q -l 1500 /d/retro/wiiurecomp/tools/tguard.sh $H:/tmp/tguard.sh 2>/dev/null; sleep 11
run=$(ssh -o ConnectTimeout=10 $H 'curl -s -m 3 localhost:1234/runningGame' 2>/dev/null)
echo "$run" | grep -q "NO GAME RUNNING\|\"name\": \"Nova Home\"" || { echo "stop: a game is running on the console"; exit 1; }
ssh $H "rm -rf $B/save-test; mkdir -p $B/save-test; rm -f /tmp/wiiu-*.jpg
chmod +x /tmp/tguard.sh 2>/dev/null; [ -x /tmp/tguard.sh ] && (/tmp/tguard.sh $((SECS+30)) &)
cat > /tmp/wiiutest.env <<EOF
export CAFE_SAVE_DIR=$B/save-test TTT2_TRACE_PACING=1 TTT2_INPUT_SCRIPT='$INPUT' $EXTRA
EOF
curl -s -m 5 -X POST localhost:1234/launch -d '/userdata/roms/ports/$TITLE (Nativ).sh' >/dev/null
n=0; t=0
while [ \$t -lt $SECS ]; do
  sleep 20; t=\$((t+20)); n=\$((n+1))
  DISPLAY=:0.0 ffmpeg -loglevel error -y -f x11grab -i :0.0 -frames:v 1 -vf scale=960:-1 -q:v 4 /tmp/wiiu-\$(printf %02d \$n).jpg
  pgrep -x cafegame >/dev/null || { echo \"game ended by itself after about \$t s\"; break; }
done
echo \"sound streams: \$(pactl list short sink-inputs 2>/dev/null | wc -l)\"; pactl list sink-inputs 2>/dev/null | grep -i 'application.name\|Corked\|Sink:' | head -6
cat /proc/loadavg; cat /tmp/tguard.out 2>/dev/null
rm -f /tmp/wiiutest.env
curl -s -m 5 localhost:1234/emukill >/dev/null; sleep 6
pgrep -x cafegame >/dev/null && { echo 'still running after emukill -> kill'; pkill -x cafegame; sleep 2; }
DISPLAY=:0.0 ffmpeg -loglevel error -y -f x11grab -i :0.0 -frames:v 1 -vf scale=960:-1 -q:v 4 /tmp/wiiu-zz-after.jpg
curl -s -m 3 localhost:1234/runningGame | grep -m1 '\"name\"\|NO GAME'
cp /userdata/system/logs/native-wiiu-$NAME.log /tmp/wiiu-run.log; ls $B/save-test -R | head -12
dmesg | tail -4 | grep -i 'trap\|segfault\|oom'; for id in \$(DISPLAY=:0.0 xinput list --id-only); do DISPLAY=:0.0 xinput query-state \$id 2>/dev/null | grep -q '=down' && echo \"KEY HELD DOWN on input device \$id\"; done" 2>/dev/null
scp -q -l 4000 "$H:/tmp/wiiu-*.jpg" "$H:/tmp/wiiu-run.log" "$OUT/" 2>/dev/null
grep -c "" "$OUT/wiiu-run.log"
grep -n "does not implement\|fault\|fatal\|^port: \|GPU: \|error" "$OUT/wiiu-run.log" | cut -c1-200 | head -12
grep "frames/s" "$OUT/wiiu-run.log" | cut -c1-170 | tail -6
grep "^pacing" "$OUT/wiiu-run.log" | tail -3 | cut -c1-160
PY=$(command -v python)
"$PY" - "$OUT" "$NAME" "$TAG" <<'PY'
import sys, glob
from PIL import Image
out, name, tag = sys.argv[1:4]
fs = sorted(glob.glob(out + '/wiiu-*.jpg'))
if fs:
    cols = 4; rows = (len(fs) + cols - 1) // cols
    sheet = Image.new('RGB', (480 * cols, 270 * rows))
    for i, f in enumerate(fs):
        sheet.paste(Image.open(f).convert('RGB').resize((480, 270)), ((i % cols) * 480, (i // cols) * 270))
    p = f'D:/retro/screenshots/wiiurecomp/console-{name}-{tag}-sheet.jpg'
    sheet.save(p, quality=85); print(len(fs), 'pictures ->', p)
PY
