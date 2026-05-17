#!/bin/sh
# Reliable status across worker containers using docker top.
for i in 1 2 3 4 5 6 7 8; do
  N=$(docker top mediavortex-worker-${i}-1 2>/dev/null | grep -c BackfillProbe)
  echo "worker-${i}: ${N} backfill process(es)"
done
