#!/usr/bin/env python3
"""
QueueRemux.py
Manually insert a TranscodeQueue row with ProcessingMode='Remux' for a given
MediaFileId. Used for smoke-testing the remux pipeline before the
transcode-vs-remux-routing cascade starts auto-routing files.

Usage:
    py Scripts/SQLScripts/QueueRemux.py <MediaFileId>
    py Scripts/SQLScripts/QueueRemux.py <MediaFileId> --priority 200   # bump to top of queue
    py Scripts/SQLScripts/QueueRemux.py --pick-one                     # pick one of the
                                                                       # current Remux candidates

Idempotent for a given MediaFileId: refuses to insert if the file is already
in the queue (any status). Prints the resulting TranscodeQueue.Id on success.

Owns: the smoke-test mechanism for remux.flow.md before
transcode-vs-remux-routing.feature.md step 6 ships.
"""

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


def PickOneCandidate(Db) -> int:
    """Return a MediaFileId currently flagged RecommendedMode='Remux'.

    Picks deterministically by smallest Id so two operators running this in
    parallel won't fight (one will hit the dedup guard).
    """
    # Pick the smallest *real* candidate: must have audio (so the audio re-encode
    # has something to work on), nontrivial size (skip degenerate test files
    # under 10 MB), and not already in queue.
    Rows = Db.ExecuteQuery(
        """
        SELECT m.Id
        FROM MediaFiles m
        WHERE m.RecommendedMode = 'Remux'
          AND m.AudioCodec IS NOT NULL
          AND m.SizeMB >= 10
          AND m.Id NOT IN (SELECT MediaFileId FROM TranscodeQueue WHERE MediaFileId IS NOT NULL)
        ORDER BY m.SizeMB ASC, m.Id ASC
        LIMIT 1
        """
    )
    if not Rows:
        print("No untranscoded Remux candidates found", file=sys.stderr)
        sys.exit(1)
    return int(Rows[0]['Id'])


def Main():
    Parser = argparse.ArgumentParser(description="Queue a single Remux job")
    Parser.add_argument('MediaFileId', nargs='?', type=int,
                        help="MediaFileId to queue. Omit when --pick-one is used.")
    Parser.add_argument('--priority', type=int, default=200,
                        help="Priority for the queue row. Default 200 (top of queue, manual override).")
    Parser.add_argument('--pick-one', action='store_true',
                        help="Pick the smallest-by-size MediaFile currently flagged RecommendedMode='Remux'.")
    Args = Parser.parse_args()

    Db = DatabaseService()

    if Args.pick_one and not Args.MediaFileId:
        Args.MediaFileId = PickOneCandidate(Db)
        print(f"Picked MediaFileId={Args.MediaFileId}")
    elif not Args.MediaFileId:
        Parser.error("Either MediaFileId or --pick-one is required")

    Rows = Db.ExecuteQuery(
        """
        SELECT Id, FilePath, FileName, FileSize AS SizeBytes, SizeMB, ContainerFormat,
               Codec, AudioCodec, ResolutionCategory, RecommendedMode, IsCompliant
        FROM MediaFiles WHERE Id = %s
        """,
        (Args.MediaFileId,)
    )
    if not Rows:
        print(f"MediaFile {Args.MediaFileId} not found", file=sys.stderr)
        sys.exit(1)
    M = Rows[0]

    Existing = Db.ExecuteQuery(
        "SELECT Id, Status, ProcessingMode FROM TranscodeQueue WHERE MediaFileId = %s",
        (Args.MediaFileId,)
    )
    if Existing:
        E = Existing[0]
        print(
            f"MediaFile {Args.MediaFileId} is already in TranscodeQueue: "
            f"Id={E['Id']} Status={E['Status']} Mode={E['ProcessingMode']} -- skipping",
            file=sys.stderr,
        )
        sys.exit(2)

    FilePath = M['FilePath'] or ''
    FileName = M['FileName'] or ''
    Parts = FilePath.replace('\\', '/').split('/')
    Directory = '\\'.join(Parts[:-1]) if len(Parts) > 1 else ''

    print(
        f"\nMediaFile {Args.MediaFileId}:\n"
        f"  FilePath:           {FilePath}\n"
        f"  ContainerFormat:    {M.get('ContainerFormat')}\n"
        f"  Codec:              {M.get('Codec')}\n"
        f"  AudioCodec:         {M.get('AudioCodec')}\n"
        f"  ResolutionCategory: {M.get('ResolutionCategory')}\n"
        f"  RecommendedMode:    {M.get('RecommendedMode')}\n"
        f"  IsCompliant:        {M.get('IsCompliant')}\n"
    )
    if M.get('RecommendedMode') != 'Remux':
        print(
            f"NOTE: this file's cascade-decided RecommendedMode is "
            f"{M.get('RecommendedMode')!r}, not 'Remux'. Continuing because "
            f"this is a manual smoke-test queue insert.",
            file=sys.stderr,
        )

    Db.ExecuteNonQuery(
        """
        INSERT INTO TranscodeQueue (
            FilePath, FileName, Directory, SizeBytes, SizeMB,
            Priority, Status, ProcessingMode, DateAdded, MediaFileId
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            FilePath,
            FileName,
            Directory,
            int(M.get('SizeBytes') or 0),
            float(M.get('SizeMB') or 0),
            int(Args.priority),
            'Pending',
            'Remux',
            datetime.now(timezone.utc),
            int(Args.MediaFileId),
        ),
    )
    NewRows = Db.ExecuteQuery(
        "SELECT Id FROM TranscodeQueue WHERE MediaFileId = %s ORDER BY Id DESC LIMIT 1",
        (Args.MediaFileId,)
    )
    print(
        f"Queued: TranscodeQueue.Id={NewRows[0]['Id']} "
        f"Mode='Remux' Priority={Args.priority}\n"
        f"\nA worker with TranscodeEnabled=true should claim it on the next poll cycle.\n"
        f"Watch with:\n"
        f"  py Scripts/SQLScripts/QueryDatabase.py sql \"SELECT Id, Status, ClaimedBy, "
        f"ProcessingMode FROM TranscodeQueue WHERE MediaFileId = {Args.MediaFileId}\"\n"
    )


if __name__ == '__main__':
    Main()
