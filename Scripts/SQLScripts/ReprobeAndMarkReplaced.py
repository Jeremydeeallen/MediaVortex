"""Final remediation for remux files where the .orig was already cleaned up
and the good remuxed output is sitting at the source path.

These files don't need _ProcessCompleteFileReplacement (no file to move).
They just need:
1. Re-probe the file at its current path to update MediaFiles metadata
2. Mark TranscodeAttempts.FileReplaced = true
3. Clean up TemporaryFilePaths

Usage:
  py Scripts/SQLScripts/ReprobeAndMarkReplaced.py --dry-run --worker=larry-worker-1
  py Scripts/SQLScripts/ReprobeAndMarkReplaced.py --worker=larry-worker-1
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from datetime import datetime, timezone


def GetRemainingAttempts():
    DB = DatabaseService()
    return DB.ExecuteQuery(
        """
        SELECT ta.id, ta.mediafileid, m.filepath AS media_filepath,
               tp.localoutputpath AS temp_output_path
        FROM TranscodeAttempts ta
        JOIN MediaFiles m ON m.id = ta.mediafileid
        LEFT JOIN TemporaryFilePaths tp ON tp.transcodeattemptid = ta.id
        WHERE ta.success = true
          AND ta.ffpmpegcommand ILIKE '%%copy%%loudnorm%%'
          AND ta.filereplaced = false
          AND ta.disposition = 'BypassReplace'
        ORDER BY ta.id
        """
    )


def FindActualFile(CanonicalPath, ToLocal):
    """Try the DB path first, then -mv variants for extension-change remuxes."""
    LocalPath = ToLocal(CanonicalPath)
    if os.path.exists(LocalPath):
        return LocalPath, CanonicalPath

    # Try -mv.<ext> variant (staged output name when extension changes)
    BaseName = os.path.splitext(CanonicalPath)[0]
    for Ext in ['mp4', 'mkv']:
        MvCanonical = f"{BaseName}-mv.{Ext}"
        MvLocal = ToLocal(MvCanonical)
        if os.path.exists(MvLocal):
            return MvLocal, MvCanonical

    return None, None


def RunReprobe(DryRun=False, WorkerName=None):
    Rows = GetRemainingAttempts()
    Total = len(Rows)
    print(f"Found {Total} remaining attempts to re-probe and mark replaced")

    if Total == 0:
        print("Nothing to do.")
        return

    if not WorkerName:
        import socket
        WorkerName = socket.gethostname().lower()

    # Get FFprobePath for this worker
    DB = DatabaseService()
    WorkerRows = DB.ExecuteQuery(
        "SELECT FFprobePath FROM Workers WHERE LOWER(WorkerName) = %s LIMIT 1",
        (WorkerName.lower(),),
    )
    FFprobePath = WorkerRows[0].get('FFprobePath') if WorkerRows else None
    print(f"WorkerName: {WorkerName}")
    print(f"FFprobePath: {FFprobePath}")

    from Core.PathStorage import LoadStorageRoots, Parse as PathParse, Resolve as PathResolve
    from Services.FileManagerService import FileManagerService
    import ntpath

    FileManager = FileManagerService(FFprobePath=FFprobePath)
    StorageRoots = LoadStorageRoots(DB)

    def ToLocal(CanonicalPath):
        SrId, Rel = PathParse(CanonicalPath, StorageRoots)
        if SrId is None:
            return CanonicalPath
        return PathResolve(SrId, Rel, WorkerName, DB)

    if DryRun:
        Reachable = 0
        for R in Rows:
            LocalPath, _ = FindActualFile(R['media_filepath'], ToLocal)
            if LocalPath:
                Reachable += 1
            else:
                print(f"  Unreachable: AttemptId={R['id']} DB={R['media_filepath']}")
        print(f"\n--- DRY RUN ---")
        print(f"  Reachable: {Reachable}/{Total}")
        print(f"  Would re-probe each and mark FileReplaced=true")
        return

    Succeeded = 0
    Failed = 0
    Skipped = 0
    Errors = []

    for I, R in enumerate(Rows, 1):
        AttemptId = R['id']
        MediaFileId = R['mediafileid']
        CanonicalPath = R['media_filepath']
        LocalPath, ActualCanonical = FindActualFile(CanonicalPath, ToLocal)

        if not LocalPath:
            Skipped += 1
            continue

        try:
            # Re-probe the file
            Metadata = FileManager.ExtractMediaMetadata(LocalPath)
            if not Metadata.get('Success', False):
                Failed += 1
                Errors.append((AttemptId, f"FFprobe failed: {Metadata.get('ErrorMessage')}"))
                print(f"  [{I}/{Total}] AttemptId={AttemptId} -- PROBE FAILED")
                continue

            # Update MediaFiles with fresh metadata
            FileName = ntpath.basename(ActualCanonical)
            NewRes = Metadata.get('Resolution', '')
            ResCat = None
            if NewRes and 'x' in NewRes:
                W = int(NewRes.split('x')[0])
                if W >= 3000: ResCat = "2160p"
                elif W >= 1700: ResCat = "1080p"
                elif W >= 1100: ResCat = "720p"
                elif W >= 600: ResCat = "480p"
                else: ResCat = "480p"

            DB.ExecuteNonQuery(
                """
                UPDATE MediaFiles SET
                    FilePath = %s,
                    FileName = %s,
                    SizeMB = %s,
                    VideoBitrateKbps = %s,
                    AudioBitrateKbps = %s,
                    Resolution = %s,
                    Codec = %s,
                    DurationMinutes = %s,
                    FrameRate = %s,
                    TotalFrames = %s,
                    AudioChannels = %s,
                    AudioSampleRate = %s,
                    AudioChannelLayout = %s,
                    AudioCodec = %s,
                    ContainerFormat = %s,
                    OverallBitrate = %s,
                    AudioLanguages = %s,
                    HasExplicitEnglishAudio = %s,
                    ResolutionCategory = %s,
                    TranscodedByMediaVortex = true,
                    LastModifiedDate = %s
                WHERE Id = %s
                """,
                (
                    ActualCanonical,
                    FileName,
                    Metadata.get('FileSizeMB'),
                    Metadata.get('VideoBitrateKbps'),
                    Metadata.get('AudioBitrateKbps'),
                    Metadata.get('Resolution'),
                    Metadata.get('VideoCodec'),
                    Metadata.get('DurationMinutes'),
                    Metadata.get('FrameRate'),
                    Metadata.get('TotalFrames'),
                    Metadata.get('AudioChannels'),
                    Metadata.get('AudioSampleRate'),
                    Metadata.get('AudioChannelLayout'),
                    Metadata.get('AudioCodec'),
                    Metadata.get('ContainerFormat'),
                    Metadata.get('OverallBitrate'),
                    Metadata.get('AudioLanguages'),
                    Metadata.get('HasExplicitEnglishAudio'),
                    ResCat,
                    datetime.now(timezone.utc),
                    MediaFileId,
                ),
            )

            # Mark TranscodeAttempt as replaced
            DB.ExecuteNonQuery(
                """
                UPDATE TranscodeAttempts SET
                    FileReplaced = true,
                    FileReplacedDate = %s,
                    ReplacementType = 'Bypass'
                WHERE Id = %s
                """,
                (datetime.now(timezone.utc), AttemptId),
            )

            # Clean up TemporaryFilePaths
            DB.ExecuteNonQuery(
                "DELETE FROM TemporaryFilePaths WHERE TranscodeAttemptId = %s",
                (AttemptId,),
            )

            Succeeded += 1
            if I % 50 == 0 or I == Total:
                print(f"  [{I}/{Total}] {Succeeded} OK so far...")

        except Exception as Ex:
            Failed += 1
            Errors.append((AttemptId, str(Ex)))
            print(f"  [{I}/{Total}] AttemptId={AttemptId} -- EXCEPTION: {Ex}")

    print(f"\nComplete: {Succeeded} succeeded, {Failed} failed, {Skipped} skipped (unreachable) out of {Total}")
    if Errors:
        print(f"\nFailed ({len(Errors)}):")
        for AttemptId, ErrMsg in Errors[:10]:
            print(f"  AttemptId={AttemptId}: {ErrMsg}")
        if len(Errors) > 10:
            print(f"  ... and {len(Errors) - 10} more")


if __name__ == '__main__':
    DryRun = '--dry-run' in sys.argv
    WorkerName = None
    for Arg in sys.argv:
        if Arg.startswith('--worker='):
            WorkerName = Arg.split('=', 1)[1]
    RunReprobe(DryRun=DryRun, WorkerName=WorkerName)
