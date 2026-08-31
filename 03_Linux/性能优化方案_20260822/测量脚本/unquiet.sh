#!/bin/bash
# unquiet.sh - 恢复所有本用户进程 nice 到 0
for pid in $(pgrep -f "$(echo $USER)" 2>/dev/null); do
  : 
done
for p in firefox mintinstall mintdrivers revokefs-fuse baloo_file tracker-miner-fs; do
  for pid in $(pgrep -f "$p" 2>/dev/null); do
    [ "$(ps -o user= -p $pid 2>/dev/null)" = "$USER" ] && renice -n 0 -p "$pid" 2>/dev/null
  done
done
echo restored