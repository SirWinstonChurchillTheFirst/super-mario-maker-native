#!/bin/bash
# console_threads.sh NAME "TITLE" WAIT_SECS "INPUT SCRIPT" [host]: starts a native Wii U port on the console like
# console_test.sh (test save folder, menu interface), samples every thread's CPU time over 5 s after WAIT_SECS and
# prints the busiest threads (name, % of one core), then ends the game. One ssh session. Refuses while a game runs.
NAME=$1; TITLE=$2; WAIT=${3:-45}; INPUT=$4; H=${5:-root@192.168.178.75}
B=/userdata/ports-native/wiiu/$NAME
mkdir /tmp/wiiu-console-test.lock 2>/dev/null || { echo "stop: another console test is running"; exit 1; }
trap 'rmdir /tmp/wiiu-console-test.lock 2>/dev/null' EXIT
ssh -o ConnectTimeout=15 $H "
run=\$(curl -s -m 3 localhost:1234/runningGame)
echo \"\$run\" | grep -q 'NO GAME RUNNING\|\"name\": \"Nova Home\"' || { echo 'stop: a game is running on the console'; exit 1; }
rm -rf $B/save-test; mkdir -p $B/save-test
cat > /tmp/wiiutest.env <<EOF
export CAFE_SAVE_DIR=$B/save-test TTT2_INPUT_SCRIPT='$INPUT' $EXTRA
EOF
curl -s -m 5 -X POST localhost:1234/launch -d '/userdata/roms/ports/$TITLE (Nativ).sh' >/dev/null
sleep $WAIT
pid=\$(pgrep -x cafegame | head -1)
[ -n \"\$pid\" ] || { echo 'game not running'; rm -f /tmp/wiiutest.env; exit 1; }
snap() { for t in /proc/\$pid/task/*; do echo \"\$(basename \$t) \$(sed 's/.*) //' \$t/stat | awk '{print \$12+\$13}') \$(cat \$t/comm)\"; done; }
snap > /tmp/thr1; sleep 5; snap > /tmp/thr2
join /tmp/thr1 /tmp/thr2 | awk '{d=\$4-\$2; printf \"%5.1f%% %s\n\", d/5, \$3}' | sort -rn | head -12
cat /sys/class/thermal/thermal_zone0/temp
rm -f /tmp/wiiutest.env
curl -s -m 5 localhost:1234/emukill >/dev/null; sleep 6
pgrep -x cafegame >/dev/null && { pkill -x cafegame; sleep 2; }
curl -s -m 3 localhost:1234/runningGame | grep -m1 '\"name\"\|NO GAME'
" 2>&1 | grep -v -i "warning\|post-quantum\|upgraded\|store now"
