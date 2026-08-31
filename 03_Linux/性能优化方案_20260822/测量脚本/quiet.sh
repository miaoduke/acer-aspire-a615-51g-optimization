#!/bin/bash
# quiet.sh - 把后台大负载进程临时降权(nice +15), 恢复用 unquiet.sh
for p in firefox mintinstall mintdrivers revokefs-fuse baloo_file tracker-miner-fs; do
  for pid in $(pgrep -f "$p" 2>/dev/null); do
    [ "$(ps -o user= -p $pid 2>/dev/null)" = "$USER" ] && renice -n 15 -p "$pid" 2>/dev/null
  done
done
echo "quieted: $(ps aux --sort=-%cpu | awk 'NR>1 && $3>5 {n++} END{print n+0}') processes >5% CPU remain"