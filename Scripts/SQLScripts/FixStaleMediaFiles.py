"""Fix MediaFiles records for files that were transcoded and replaced on disk
but whose DB records were never updated (due to FFprobe path bug on Linux workers).

Updates: FilePath, FileName, SizeMB, Codec, TranscodedByMediaVortex, LastScannedDate.
Does NOT update resolution/bitrate/audio metadata (requires FFprobe re-probe).

Run with --commit to persist changes. Default is dry-run.
"""

import sys
import os
import re
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


def Main():
    Commit = '--commit' in sys.argv
    DB = DatabaseService()

    # Find all files where transcode succeeded, file was replaced, but MediaFiles not updated
    Query = """
        SELECT ta.id as attempt_id,
               ta.filepath as original_path,
               ta.newsizebytes,
               ta.ffpmpegcommand,
               ta.quality
        FROM TranscodeAttempts ta
        JOIN MediaFiles mf ON ta.mediafileid = mf.id
        WHERE ta.success = true
          AND ta.filereplaced = true
          AND (mf.transcodedbymediavortex IS NULL OR mf.transcodedbymediavortex = false)
          AND ta.id > 1537
        ORDER BY ta.id
    """

    Rows = DB.ExecuteQuery(Query)
    if not Rows:
        print("No stale records found.")
        return

    print(f"Found {len(Rows)} stale MediaFiles records to fix.")
    print()

    Updated = 0
    Skipped = 0

    for Row in Rows:
        AttemptId = Row['attempt_id']
        OriginalPath = Row['original_path']
        NewSizeBytes = Row['newsizebytes']
        FfmpegCommand = Row['ffpmpegcommand']

        # Extract output filename from FFmpeg command: last argument after -y ".../"
        Match = re.search(r'-y\s+"[^"]*[/\\]([^"]+)"', FfmpegCommand)
        if not Match:
            print(f"  SKIP attempt {AttemptId}: cannot parse output filename from FFmpeg command")
            Skipped += 1
            continue

        NewFilename = Match.group(1)

        # Build new canonical path: original directory + new filename
        # Original path uses backslashes (Windows canonical format)
        LastBackslash = OriginalPath.rfind('\\')
        if LastBackslash == -1:
            print(f"  SKIP attempt {AttemptId}: cannot find directory in {OriginalPath}")
            Skipped += 1
            continue

        OriginalDir = OriginalPath[:LastBackslash + 1]
        NewPath = OriginalDir + NewFilename
        NewSizeMB = NewSizeBytes / (1024 * 1024) if NewSizeBytes else None

        # Determine codec from filename extension
        NewCodec = 'av1'  # All profiles are SVT-AV1

        print(f"  Attempt {AttemptId}:")
        print(f"    OLD: {OriginalPath}")
        print(f"    NEW: {NewPath}")
        print(f"    Size: {NewSizeMB:.1f} MB, Codec: {NewCodec}")

        if Commit:
            # Update MediaFiles record
            UpdateQuery = """
                UPDATE MediaFiles
                SET filepath = %s,
                    filename = %s,
                    sizemb = %s,
                    codec = %s,
                    transcodedbymediavortex = true,
                    lastscanneddate = %s
                WHERE filepath = %s
            """
            DB.ExecuteNonQuery(UpdateQuery, (
                NewPath,
                NewFilename,
                NewSizeMB,
                NewCodec,
                datetime.now(),
                OriginalPath
            ))
            print(f"    UPDATED")
        else:
            print(f"    (dry run)")

        Updated += 1
        print()

    print(f"Done. Updated: {Updated}, Skipped: {Skipped}")
    if not Commit:
        print("(dry run -- use --commit to persist changes)")


if __name__ == '__main__':
    Main()
