#!/bin/bash
# console_cemu_ref.sh TAG [host]: Super Mario 3D World in Cemu (the emulator entry) on the console, no input, screen
# pictures every 10 s from 30 s to 100 s, as a reference for the native port's brightness. The player's Cemu save of
# the title (usr/save/00050000/1010ed00) is backed up first and put back if anything in it changed.
TAG=${1:-cemu1}; H=${2:-${CONSOLE_HOST:-root@batocera.local}}
OUT=${WIIU_WORK:-$HOME/wiiurecomp}/console/run/3dworld-$TAG; mkdir -p "$OUT"
mkdir /tmp/wiiu-console-test.lock 2>/dev/null || { echo "stop: another console test is running"; exit 1; }
trap 'rmdir /tmp/wiiu-console-test.lock 2>/dev/null' EXIT
ROM="/userdata/roms/wiiu/Super Mario 3D World/code/RedCarpet.rpx"
S=/userdata/saves/wiiu/usr/save/00050000/1010ed00
ssh -o ConnectTimeout=10 $H "
run=\$(curl -s -m 3 localhost:1234/runningGame)
echo \"\$run\" | grep -q 'NO GAME RUNNING\|\"name\": \"Nova Home\"' || { echo 'stop: a game is running'; exit 1; }
BK=/userdata/saves/wiiu/save-backup-1010ed00-\$(date +%Y%m%d-%H%M).tgz
tar czf \$BK -C /userdata/saves/wiiu/usr/save/00050000 1010ed00 && echo backup \$BK
(cd $S && find . -type f -exec md5sum {} \; | sort) > /tmp/cemu-save.before
rm -rf /tmp/wbr; mkdir -p /tmp/wbr
[ -x /tmp/tguard.sh ] && (/tmp/tguard.sh 120 &)
printf '%s\nemulator\n' '$ROM' > /tmp/novahome.choice
curl -s -m 5 -X POST localhost:1234/launch -d '$ROM' >/dev/null
t0=\$(date +%s)
for s in 30 40 50 60 70 80 90 100; do
  while [ \$(( \$(date +%s) - t0 )) -lt \$s ]; do sleep 0.2; done
  DISPLAY=:0.0 ffmpeg -loglevel error -y -f x11grab -i :0.0 -frames:v 1 /tmp/wbr/x_\$s.png
done
curl -s -m 5 localhost:1234/emukill >/dev/null; sleep 10
pgrep -fl '[C]emu' | head -3
(cd $S && find . -type f -exec md5sum {} \; | sort) > /tmp/cemu-save.after
if cmp -s /tmp/cemu-save.before /tmp/cemu-save.after; then echo 'save unchanged'; else echo 'save CHANGED -> restoring'; rm -rf $S; tar xzf \$BK -C /userdata/saves/wiiu/usr/save/00050000; fi
cat /tmp/tguard.out 2>/dev/null
cd /tmp/wbr && tar czf /tmp/wbr.tgz . && ls -la /tmp/wbr.tgz
curl -s -m 3 localhost:1234/runningGame | grep -m1 '\"name\"\|NO GAME'"
sleep 11
scp -q -l 4000 "$H:/tmp/wbr.tgz" "$OUT/wbr.tgz" && (cd "$OUT" && tar xzf wbr.tgz && rm wbr.tgz)
ls "$OUT"
