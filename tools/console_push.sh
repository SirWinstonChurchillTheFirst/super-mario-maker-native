#!/bin/bash
# console_push.sh LOCAL_FILE NAME [host]: replaces /userdata/ports-native/wiiu/NAME/cafegame on the console with LOCAL_FILE.
# Throttled pieces (the WLAN stick stalls on fast uploads), the program there before is kept as cafegame.vor-<date>,
# refuses while a game runs there. Prints both checksums (must be equal).
F=$1; N=$2; H=${3:-${CONSOLE_HOST:-root@batocera.local}}; B=/userdata/ports-native/wiiu
run=$(ssh -o ConnectTimeout=10 $H 'curl -s -m 3 localhost:1234/runningGame' 2>/dev/null)
echo "$run" | grep -q "NO GAME RUNNING\|\"name\": \"Nova Home\"" || { echo "stop: a game is running on the console"; exit 1; }
T=$(mktemp -d); gzip -9 -c "$F" > $T/t.gz; (cd $T && split -b 400k t.gz p.)
ssh -o ConnectTimeout=30 -o BatchMode=yes $H 'rm -rf /tmp/ch; mkdir -p /tmp/ch' 2>/dev/null
for f in $T/p.*; do ok=0; for try in 1 2 3 4 5 6 7 8; do
    if scp -q -l 1500 -o ConnectTimeout=20 $f $H:/tmp/ch/ 2>/dev/null; then ok=1; break; fi; ping -n 10 127.0.0.1 >/dev/null; done
  [ $ok = 1 ] || { echo "FEHLER $f"; exit 1; }; done
ssh -o ConnectTimeout=30 -o BatchMode=yes $H "cd $B/$N && cat /tmp/ch/p.* | gunzip > cafegame.neu && chmod +x cafegame.neu && cp -p cafegame cafegame.vor-\$(date +%Y%m%d-%H%M) && mv -f cafegame.neu cafegame && rm -rf /tmp/ch && md5sum cafegame | cut -c1-32" 2>/dev/null
md5sum "$F" | cut -c1-32; rm -rf $T
