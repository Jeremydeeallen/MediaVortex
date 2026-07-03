import argparse
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


# directive: filereplacement-drain-bug
STUCK_QUERY = (
    "SELECT ta.Id AS attempt_id, ta.MediaFileId, ta.OldSizeBytes, ta.NewSizeBytes, "
    "ta.Disposition, ta.FileReplaced, ta.ErrorMessage, "
    "EXTRACT(EPOCH FROM (NOW() - ta.AttemptDate))/60 AS minutes_old, "
    "tfp.Id AS tfp_id, m.SizeMB, m.FileName "
    "FROM TranscodeAttempts ta "
    "LEFT JOIN TemporaryFilePaths tfp ON tfp.TranscodeAttemptId = ta.Id "
    "LEFT JOIN MediaFiles m ON m.Id = ta.MediaFileId "
    "WHERE ta.Disposition = 'Replace' AND ta.FileReplaced = FALSE "
    "AND ta.AttemptDate < NOW() - INTERVAL '15 minutes' "
    "AND (ta.ErrorMessage IS NULL OR ta.ErrorMessage NOT ILIKE '%%Recovery refused%%') "
    "ORDER BY ta.Id"
)


# directive: filereplacement-drain-bug
def Recover(DryRun=False):
    DB = DatabaseService()
    Rows = DB.ExecuteQuery(STUCK_QUERY)
    print(f"Stuck attempts: {len(Rows)}")
    if not Rows:
        return 0

    Recovered = 0
    Failed = 0
    for R in Rows:
        Aid = R['attempt_id']
        Mid = R['mediafileid']
        OldBytes = R['oldsizebytes'] or 0
        NewBytes = R['newsizebytes'] or 0
        SizeMb = float(R['sizemb'] or 0)
        TruthBytes = int(SizeMb * 1024 * 1024)
        TfpId = R['tfp_id']
        FileName = R['filename'] or '?'
        MinutesOld = float(R['minutes_old'] or 0)

        print(f"\n  attempt={Aid} mediafile={Mid} ({FileName[:60]}) age={MinutesOld:.0f}min")
        print(f"    OldSizeBytes={OldBytes}, NewSizeBytes={NewBytes}, TFP={TfpId or 'MISSING'}, MediaFile size={TruthBytes}")

        if DryRun:
            print("    [DRY-RUN] would backfill OldSizeBytes + re-invoke FileReplacement")
            continue

        if OldBytes == 0 and TruthBytes > 0:
            DB.ExecuteNonQuery("UPDATE TranscodeAttempts SET OldSizeBytes = %s WHERE Id = %s", (TruthBytes, Aid))
            print(f"    backfilled OldSizeBytes -> {TruthBytes}")

        if TfpId is None:
            if not DryRun:
                DB.ExecuteNonQuery(
                    "UPDATE TranscodeAttempts SET ErrorMessage = %s WHERE Id = %s",
                    (f"Recovery refused: TFP row missing (.inprogress path mapping unrecoverable; attempt age {MinutesOld:.0f}min)", Aid),
                )
            print(f"    SKIPPED: TFP missing -- marked permanently refused")
            Failed += 1
            continue

        from Features.FileReplacement.FileReplacementBusinessService import FileReplacementBusinessService
        from Repositories.DatabaseManager import DatabaseManager
        Result = FileReplacementBusinessService(DatabaseManager()).ProcessFileReplacement(Aid)
        if Result.get('Success'):
            Recovered += 1
            print(f"    RECOVERED")
        else:
            Failed += 1
            Err = Result.get('ErrorMessage') or 'unknown'
            print(f"    RECOVERY FAILED: {Err[:140]}")
            DB.ExecuteNonQuery(
                "UPDATE TranscodeAttempts SET ErrorMessage = %s WHERE Id = %s",
                (f"Recovery refused: {Err[:400]}", Aid),
            )

    print(f"\nSummary: {Recovered} recovered, {Failed} still stuck, {len(Rows)} total.")
    return Recovered


# directive: filereplacement-drain-bug
def Main():
    Ap = argparse.ArgumentParser(description="Recover stuck FileReplaced=False attempts. Backfills OldSizeBytes from MediaFile.SizeMB when 0, then re-invokes ProcessFileReplacement.")
    Ap.add_argument('--dry-run', action='store_true', help='List the stuck attempts without writing')
    Args = Ap.parse_args()
    Recover(DryRun=Args.dry_run)


if __name__ == '__main__':
    Main()
