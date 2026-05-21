#!/bin/sh
# Kill ALL Backfill / ffmpeg ebur128 processes inside each worker container.
# Uses container-namespace PIDs (host PIDs from docker top wouldn't work via docker exec).
for i in 1 2 3 4 5 6 7 8; do
  echo "--- worker-${i} ---"
  docker exec mediavortex-worker-${i}-1 sh -c '
    for p in /proc/[0-9]*/cmdline; do
      if grep -aqE "BackfillProbe|ebur128" "$p" 2>/dev/null; then
        pid=$(echo "$p" | cut -d/ -f3)
        kill -9 "$pid" 2>/dev/null && echo "  killed $pid"
      fi
    done
  '
done
