"""Audit files flagged as TranscodedByMediaVortex = True.

Probes each file with FFprobe and checks:
  1. Does the file exist on disk?
  2. Is the codec AV1 (expected from libsvtav1 profiles)?
  3. Does the metadata comment contain 'MediaVortex'? (future transcodes only)

Usage:
    py Scripts/AuditTranscodedFiles.py              # audit all
    py Scripts/AuditTranscodedFiles.py --limit 50   # audit first 50
    py Scripts/AuditTranscodedFiles.py --suspect     # only show suspect files
"""

import argparse
import json
import os
import subprocess
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Core.Database.DatabaseService import DatabaseService

FFPROBE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'FFmpegMaster', 'bin', 'ffprobe.exe')


def ProbeFile(FilePath):
    """Run FFprobe and return codec + comment metadata."""
    try:
        Result = subprocess.run(
            [FFPROBE_PATH, '-v', 'quiet', '-print_format', 'json',
             '-show_format', '-show_streams', FilePath],
            capture_output=True, text=True, timeout=30
        )
        if Result.returncode != 0:
            return None
        Data = json.loads(Result.stdout)

        # Video codec
        VideoCodec = None
        for Stream in Data.get('streams', []):
            if Stream.get('codec_type') == 'video':
                VideoCodec = Stream.get('codec_name')
                break

        # Metadata comment
        Tags = Data.get('format', {}).get('tags', {})
        Comment = Tags.get('comment', Tags.get('COMMENT', ''))

        return {'Codec': VideoCodec, 'Comment': Comment}
    except Exception as Ex:
        return None


def Main():
    Parser = argparse.ArgumentParser(description='Audit TranscodedByMediaVortex files')
    Parser.add_argument('--limit', type=int, default=0, help='Max files to check (0 = all)')
    Parser.add_argument('--suspect', action='store_true', help='Only print suspect files')
    Args = Parser.parse_args()

    LimitClause = f'LIMIT {int(Args.limit)}' if Args.limit > 0 else ''
    Sql = f"""
        SELECT Id, FilePath, FileName, Codec, SizeMB
        FROM MediaFiles
        WHERE TranscodedByMediaVortex = true
        ORDER BY SizeMB DESC
        {LimitClause}
    """

    Db = DatabaseService()
    Rows = Db.ExecuteQuery(Sql)
    print(f"Found {len(Rows)} files flagged as TranscodedByMediaVortex = True\n")

    SuspectCount = 0
    MissingCount = 0
    VerifiedCount = 0

    for Row in Rows:
        FilePath = Row.get('filepath', '')
        FileName = Row.get('filename', '')
        DbCodec = Row.get('codec', '')
        SizeMB = round(float(Row.get('sizemb', 0) or 0), 1)

        # Check file existence
        if not os.path.exists(FilePath):
            MissingCount += 1
            if not Args.suspect:
                print(f"  MISSING  {FileName} ({SizeMB} MB) - file not found on disk")
            continue

        # Probe file
        ProbeResult = ProbeFile(FilePath)
        if ProbeResult is None:
            SuspectCount += 1
            print(f"  SUSPECT  {FileName} ({SizeMB} MB) - FFprobe failed")
            continue

        ActualCodec = ProbeResult['Codec'] or 'unknown'
        HasMVComment = 'mediavortex' in ProbeResult['Comment'].lower()

        # AV1 codec = likely genuinely transcoded by our libsvtav1 profiles
        IsAV1 = ActualCodec in ('av1', 'libsvtav1')

        if IsAV1:
            VerifiedCount += 1
            if not Args.suspect:
                Tag = 'TAGGED' if HasMVComment else 'NO-TAG'
                print(f"  OK [{Tag}]  {FileName} ({SizeMB} MB) codec={ActualCodec}")
        else:
            SuspectCount += 1
            print(f"  SUSPECT  {FileName} ({SizeMB} MB) codec={ActualCodec} (expected av1) db_codec={DbCodec}")

    print(f"\n--- Summary ---")
    print(f"  Verified (AV1):  {VerifiedCount}")
    print(f"  Suspect:         {SuspectCount}")
    print(f"  Missing on disk: {MissingCount}")
    print(f"  Total checked:   {len(Rows)}")


if __name__ == '__main__':
    Main()
