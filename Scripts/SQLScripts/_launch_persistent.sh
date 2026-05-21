#!/bin/sh
# _launch_persistent.sh -- daemonize backfill so it survives docker-exec teardown.
# Runs inside LXC 218 (mediavortex-workers).
# Arg 1: total shard count (e.g. 4)
# Arg 2: list of worker numbers to use (e.g. "1 3 5 7")
# Arg 3: optional drive filter (e.g. "T:"); empty = all drives
TOTAL=${1:-4}
WORKERS=${2:-"1 3 5 7"}
DRIVE=${3:-}

if [ -n "$DRIVE" ]; then
  DRIVE_ARG="--drive ${DRIVE}"
else
  DRIVE_ARG=""
fi

SHARD_ID=0
for w in $WORKERS; do
  CMD="setsid nohup python3 /tmp/BackfillProbeAndLoudness.py --worker-name larry-worker-${w} --shard-id ${SHARD_ID} --total-shards ${TOTAL} --batch-size 5 ${DRIVE_ARG} > /tmp/loudness-shard.log 2>&1 < /dev/null &"
  docker exec mediavortex-worker-${w}-1 sh -c "$CMD"
  echo "launched worker-${w} shard ${SHARD_ID}/${TOTAL} drive=${DRIVE:-all}"
  SHARD_ID=$((SHARD_ID+1))
done
echo "all launched. verify after 60s with /tmp/_status_shards.sh"
