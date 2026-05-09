#!/usr/bin/env python3
"""
BackfillPriorityScores.py
One-shot batched backfill that populates MediaFiles.PriorityScore for rows
with NULL scores.

Owns: priority-materialization.feature.md criteria 12-13.
Idempotent. Safe to run multiple times.

Usage:
    py Scripts/SQLScripts/BackfillPriorityScores.py [--batch-size N] [--limit N] [--dry-run]
"""

import argparse
import os
import sys
import time

# Make project imports work when run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService


def Main():
    Parser = argparse.ArgumentParser(description="Backfill MediaFiles.PriorityScore")
    Parser.add_argument('--batch-size', type=int, default=1000,
                        help='Rows per batch (default 1000)')
    Parser.add_argument('--limit', type=int, default=None,
                        help='Stop after N total rows (default: all NULL rows)')
    Parser.add_argument('--dry-run', action='store_true',
                        help='Compute scores but do not write')
    Args = Parser.parse_args()

    Db = DatabaseService()
    Service = QueueManagementBusinessService()

    Rows = Db.ExecuteQuery("SELECT COUNT(*) AS Count FROM MediaFiles WHERE PriorityScore IS NULL")
    Total = Rows[0]['Count']
    if Args.limit and Args.limit < Total:
        Total = Args.limit
    print(f"Rows to backfill: {Total}")
    if Total == 0:
        print("Nothing to do.")
        return

    Processed = 0
    Started = time.time()

    while Processed < Total:
        Remaining = Total - Processed
        Limit = min(Args.batch_size, Remaining)
        Rows = Db.ExecuteQuery(
            "SELECT Id FROM MediaFiles WHERE PriorityScore IS NULL ORDER BY Id LIMIT %s",
            (Limit,)
        )
        if not Rows:
            break
        Ids = [r['Id'] for r in Rows]

        if Args.dry_run:
            # Still call compute to exercise the math but skip the write side.
            # We do this by reading -- the bulk function writes, so dry-run skips it.
            print(f"  [dry-run] would compute {len(Ids)} rows (Ids {Ids[0]}..{Ids[-1]})")
            Processed += len(Ids)
            continue

        BatchStart = time.time()
        Updated = Service.ComputePriorityScoresForFiles(Ids)
        Elapsed = time.time() - BatchStart
        Processed += Updated
        Rate = Updated / Elapsed if Elapsed > 0 else 0
        Eta = (Total - Processed) / Rate if Rate > 0 else 0
        print(f"  batch: {Updated}/{len(Ids)} updated in {Elapsed:.1f}s ({Rate:.0f} rows/s) -- {Processed}/{Total} done -- ETA {Eta:.0f}s")

        if Updated == 0 and not Args.dry_run:
            # Nothing got updated despite finding NULL rows -- likely a logic bug, abort.
            print("WARNING: bulk update returned 0 rows updated; aborting to avoid infinite loop.")
            break

    TotalElapsed = time.time() - Started
    print(f"\nDone. Processed {Processed}/{Total} rows in {TotalElapsed:.1f}s")

    Rows = Db.ExecuteQuery("SELECT COUNT(*) AS Count FROM MediaFiles WHERE PriorityScore IS NULL")
    print(f"Remaining MediaFiles with PriorityScore IS NULL: {Rows[0]['Count']}")


if __name__ == '__main__':
    Main()
