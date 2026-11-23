#!/bin/bash
# console_bright.sh NAME "TITLE" TAG "EXTRA ENV" [host]: brightness check on the console. Starts the port through the
# shell's /launch WITHOUT input (title screen stays), saves the scan buffer the game made (TTT2_CAPTURE, from 38 s
# every 4 s) and, at the same moments, what X shows (x11grab, full size PNG). Temp guard runs alongside.
# Results: console/run/<name>-<tag>/ (tv_*.png = game's own picture, x_*.png = screen), log line "trace: saved".
NAME=$1; TITLE=$2; TAG=$3; EXTRA=$4; H=${5:-${CONSOLE_HOST:-root@batocera.local}}
OUT=${WIIU_WORK:-$HOME/wiiurecomp}/console/run/$NAME-$TAG; mkdir -p "$OUT"
mkdir /tmp/wiiu-console-test.lock 2>/dev/null || { echo "stop: another console test is running"; exit 1; }
trap 'rmdir /tmp/wiiu-console-test.lock 2>/dev/null' EXIT
B=/userdata/ports-native/wiiu/$NAME
ssh -o ConnectTimeout=10 $H "
run=\$(curl -s -m 3 localhost:1234/runningGame)
echo \"\$run\" | grep -q 'NO GAME RUNNING\|\"name\": \"Nova Home\"' || { echo 'stop: a game is running'; exit 1; }
rm -rf /tmp/wcap /tmp/wbr; mkdir -p /tmp/wcap /tmp/wbr $B/save-test
[ -x /tmp/tguard.sh ] && (/tmp/tguard.sh 75 &)
cat > /tmp/wiiutest.env <<EOF
export CAFE_SAVE_DIR=$B/save-test TTT2_CAPTURE=/tmp/wcap TTT2_CAPTURE_START=38 TTT2_CAPTURE_INTERVAL=4 TTT2_CAPTURE_TV_ONLY=1 $EXTRA
EOF
curl -s -m 5 -X POST localhost:1234/launch -d '/userdata/roms/ports/$TITLE (Nativ).sh' >/dev/null
t0=\$(date +%s)
for s in 39 43 47 51; do
  while [ \$(( \$(date +%s) - t0 )) -lt \$s ]; do sleep 0.2; done
  DISPLAY=:0.0 ffmpeg -loglevel error -y -f x11grab -i :0.0 -frames:v 1 /tmp/wbr/x_\$s.png
done
sleep 3
rm -f /tmp/wiiutest.env
curl -s -m 5 localhost:1234/emukill >/dev/null; sleep 6
pgrep -x cafegame >/dev/null && { pkill -x cafegame; sleep 2; }
cp /userdata/system/logs/native-wiiu-$NAME.log /tmp/wbr/run.log; cp /tmp/wcap/*.png /tmp/wbr/ 2>/dev/null
cat /tmp/tguard.out 2>/dev/null
grep 'presenting\|trace: saved' /tmp/wbr/run.log | head -8
cd /tmp/wbr && tar czf /tmp/wbr.tgz . && ls -la /tmp/wbr.tgz
curl -s -m 3 localhost:1234/runningGame | grep -m1 '\"name\"\|NO GAME'"
sleep 11
scp -q -l 4000 "$H:/tmp/wbr.tgz" "$OUT/wbr.tgz" && (cd "$OUT" && tar xzf wbr.tgz && rm wbr.tgz)
ls "$OUT"
