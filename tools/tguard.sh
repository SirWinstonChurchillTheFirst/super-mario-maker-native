#!/bin/sh
# Waehrend eines Tests: alle 5 s Prozessor/Grafik messen, Hoechstwerte merken, bei > 85 C Spiel beenden.
mc=0; mg=0; end=$(( $(date +%s) + ${1:-300} ))
while [ $(date +%s) -lt $end ]; do
  for h in /sys/class/hwmon/hwmon*; do case $(cat $h/name) in k10temp) c=$(( $(cat $h/temp1_input)/1000 ));; amdgpu) g=$(( $(cat $h/temp1_input)/1000 ));; esac; done
  [ $c -gt $mc ] && mc=$c; [ $g -gt $mg ] && mg=$g
  echo "max Prozessor $mc C, Grafik $mg C (jetzt $c / $g)" > /tmp/tguard.out
  if [ $c -gt 85 ] || [ $g -gt 85 ]; then echo "ABBRUCH: zu heiss $c / $g" >> /tmp/tguard.out; curl -s -m 5 localhost:1234/emukill >/dev/null; exit 0; fi
  sleep 5
done
