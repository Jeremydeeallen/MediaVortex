"""Retention cleanup for multi-variant test mode encoded outputs.

Removes the on-disk encoded files staged by test-mode TranscodeAttempts older
than SystemSettings.TestModeRetentionDays (default 30). DB rows are preserved
indefinitely -- only the disk files are removed.

Idempotent. Safe to schedule daily.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from Core.Database.DatabaseService import DatabaseService
from Core.WorkerContext import WorkerContext


def GetRetentionDays(Db):
    Rows = Db.ExecuteQuery(
        "SELECT SettingValue FROM SystemSettings WHERE SettingKey = 'TestModeRetentionDays'"
    )
    try:
        return int(Rows[0]['SettingValue']) if Rows else 30
    except (KeyError, ValueError, TypeError):
        return 30


def Main(DryRun=False):
    Db = DatabaseService()
    Days = GetRetentionDays(Db)
    Cutoff = datetime.now(timezone.utc) - timedelta(days=Days)
    print(f"Test-mode retention: {Days} days (cutoff = {Cutoff.isoformat()})")
    print(f"Dry run: {DryRun}")

    Rows = Db.ExecuteQuery(
        """
        SELECT tfp.Id AS TfpId, tfp.TranscodeAttemptId, tfp.LocalOutputPath, tfp.OriginalPath,
               ta.TestVariantSetId, ta.TestVariantName, ta.AttemptDate, ta.FileReplaced
        FROM TemporaryFilePaths tfp
        JOIN TranscodeAttempts ta ON ta.Id = tfp.TranscodeAttemptId
        WHERE ta.TestVariantSetId IS NOT NULL
          AND ta.AttemptDate < %s
          AND ta.FileReplaced IS NOT TRUE
        ORDER BY ta.AttemptDate ASC
        """,
        (Cutoff,),
    )
    print(f"\nCandidate test-mode encoded outputs older than {Days} days: {len(Rows)}")
    if not Rows:
        return

    Ctx = WorkerContext.TryCurrent()
    Translate = Ctx.PathTranslation.ToLocalPath if (Ctx and Ctx.PathTranslation) else (lambda P: P)

    Deleted = 0
    Missing = 0
    Errors = 0
    BytesFreed = 0
    for R in Rows:
        Canonical = R.get('LocalOutputPath') or ''
        if not Canonical:
            Missing += 1
            continue
        Local = Translate(Canonical)
        if not os.path.exists(Local):
            Missing += 1
            continue
        try:
            Size = os.path.getsize(Local)
        except OSError:
            Size = 0
        if DryRun:
            print(f"  WOULD DELETE  ta={R['TranscodeAttemptId']}  ({Size/(1024*1024):.1f} MB)  {Local}")
            BytesFreed += Size
            continue
        try:
            os.remove(Local)
            Deleted += 1
            BytesFreed += Size
            print(f"  DELETED  ta={R['TranscodeAttemptId']}  ({Size/(1024*1024):.1f} MB)  {Local}")
        except OSError as Ex:
            Errors += 1
            print(f"  ERROR    ta={R['TranscodeAttemptId']}  {Local}  -- {Ex}")

    print()
    print(f"Deleted: {Deleted}   Missing-already: {Missing}   Errors: {Errors}")
    print(f"Bytes freed: {BytesFreed/(1024*1024*1024):.2f} GB ({BytesFreed/(1024*1024):.1f} MB)")


if __name__ == "__main__":
    Main(DryRun='--dry-run' in sys.argv or '-n' in sys.argv)
