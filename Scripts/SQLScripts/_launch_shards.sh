#!/bin/sh
# Launch 8 parallel backfill shards across larry-worker-{1..8} containers.
# Run from inside LXC 218 (mediavortex-workers).
for i in 1 2 3 4 5 6 7 8; do
  j=$((i-1))
  docker exec mediavortex-worker-${i}-1 sh -c "nohup python3 /tmp/BackfillProbeAndLoudness.py --worker-name larry-worker-${i} --shard-id ${j} --total-shards 8 --batch-size 5 > /tmp/loudness-shard.log 2>&1 < /dev/null & echo PID-${i}=\$!"
done
