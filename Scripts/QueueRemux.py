import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Core.Database.DatabaseService import DatabaseService
from Core.Path.Path import Path, PathError
from Core.Path.PathStorageRoots import GetPrefixMap


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def PickOneCandidate(Db) -> int:
    """Return a MediaFileId currently in WorkBucket='Remux'; deterministic by smallest size + Id so parallel operators don't fight."""
    Rows = Db.ExecuteQuery(
        "SELECT m.Id FROM MediaFiles m "
        "WHERE m.WorkBucket = 'Remux' "
        "AND m.AudioCodec IS NOT NULL "
        "AND m.SizeMB >= 10 "
        "AND m.Id NOT IN (SELECT MediaFileId FROM TranscodeQueue WHERE MediaFileId IS NOT NULL) "
        "ORDER BY m.SizeMB ASC, m.Id ASC LIMIT 1"
    )
    if not Rows:
        print("No untranscoded Remux candidates found", file=sys.stderr)
        sys.exit(1)
    return int(Rows[0]['Id'])


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def _CanonicalDirectory(StorageRootId, RelativePath: str) -> str:
    """Canonical-form parent directory derived from typed pair; '' when typed pair is missing or invalid."""
    if StorageRootId is None:
        return ''
    try:
        return Path(StorageRootId, RelativePath or '').ParentDir().CanonicalDisplay(GetPrefixMap())
    except PathError:
        return ''


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def Main():
    """Manually queue one TranscodeQueue row with ProcessingMode='Remux' for a given MediaFileId; smoke-test for the remux pipeline. Idempotent: refuses if MediaFile is already in the queue."""
    Parser = argparse.ArgumentParser(description="Queue a single Remux job")
    Parser.add_argument('MediaFileId', nargs='?', type=int, help="MediaFileId to queue. Omit when --pick-one is used.")
    Parser.add_argument('--priority', type=int, default=200, help="Priority for the queue row. Default 200 (top of queue, manual override).")
    Parser.add_argument('--pick-one', action='store_true', help="Pick the smallest MediaFile currently in WorkBucket='Remux'.")
    Args = Parser.parse_args()

    Db = DatabaseService()

    if Args.pick_one and not Args.MediaFileId:
        Args.MediaFileId = PickOneCandidate(Db)
        print(f"Picked MediaFileId={Args.MediaFileId}")
    elif not Args.MediaFileId:
        Parser.error("Either MediaFileId or --pick-one is required")

    Rows = Db.ExecuteQuery(
        "SELECT Id, StorageRootId, RelativePath, FilePath, FileName, FileSize AS SizeBytes, SizeMB, ContainerFormat, "
        "Codec, AudioCodec, ResolutionCategory, WorkBucket, IsCompliant "
        "FROM MediaFiles WHERE Id = %s",
        (Args.MediaFileId,)
    )
    if not Rows:
        print(f"MediaFile {Args.MediaFileId} not found", file=sys.stderr)
        sys.exit(1)
    M = Rows[0]

    Existing = Db.ExecuteQuery("SELECT Id, Status, ProcessingMode FROM TranscodeQueue WHERE MediaFileId = %s", (Args.MediaFileId,))
    if Existing:
        E = Existing[0]
        print(f"MediaFile {Args.MediaFileId} is already in TranscodeQueue: Id={E['Id']} Status={E['Status']} Mode={E['ProcessingMode']} -- skipping", file=sys.stderr)
        sys.exit(2)

    FilePath = M['FilePath'] or ''
    FileName = M['FileName'] or ''
    Directory = _CanonicalDirectory(M.get('StorageRootId'), M.get('RelativePath') or '')

    print(
        f"\nMediaFile {Args.MediaFileId}:\n"
        f"  FilePath:           {FilePath}\n"
        f"  ContainerFormat:    {M.get('ContainerFormat')}\n"
        f"  Codec:              {M.get('Codec')}\n"
        f"  AudioCodec:         {M.get('AudioCodec')}\n"
        f"  ResolutionCategory: {M.get('ResolutionCategory')}\n"
        f"  WorkBucket:         {M.get('WorkBucket')}\n"
        f"  IsCompliant:        {M.get('IsCompliant')}\n"
    )
    if M.get('WorkBucket') != 'Remux':
        print(f"NOTE: this file's compliance-decided WorkBucket is {M.get('WorkBucket')!r}, not 'Remux'. Continuing because this is a manual smoke-test queue insert.", file=sys.stderr)

    Db.ExecuteNonQuery(
        "INSERT INTO TranscodeQueue ("
        "StorageRootId, RelativePath, FilePath, FileName, Directory, SizeBytes, SizeMB, "
        "Priority, Status, ProcessingMode, DateAdded, MediaFileId"
        ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            M.get('StorageRootId'),
            M.get('RelativePath') or '',
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
    NewRows = Db.ExecuteQuery("SELECT Id FROM TranscodeQueue WHERE MediaFileId = %s ORDER BY Id DESC LIMIT 1", (Args.MediaFileId,))
    print(
        f"Queued: TranscodeQueue.Id={NewRows[0]['Id']} Mode='Remux' Priority={Args.priority}\n"
        f"\nA worker with TranscodeEnabled=true should claim it on the next poll cycle.\n"
        f"Watch with:\n"
        f"  py Scripts/SQLScripts/QueryDatabase.py sql \"SELECT Id, Status, ClaimedBy, ProcessingMode FROM TranscodeQueue WHERE MediaFileId = {Args.MediaFileId}\"\n"
    )


if __name__ == '__main__':
    Main()
