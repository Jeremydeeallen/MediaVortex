"""Complete a partial-replacement state for a TranscodeAttempt.

When `_ProcessCompleteFileReplacement` crashes after the staged file has
already been renamed to its final `-mv.<ext>` location, the attempt is left
in a half-finished state:

  - File on disk: renamed to `<basename>-mv.<ext>` ✓
  - `<basename>.<origext>.orig` backup: in place ✓
  - TranscodeAttempts.FileReplaced: still FALSE ✗
  - TranscodeAttempts.FileReplacedDate / ReplacementType: NULL ✗
  - MediaFiles.FilePath: still points at the old name (pre-replacement) ✗
  - MediaFiles metadata: stale (not re-probed yet) ✗
  - `.orig` backup: not settled (deleted or renamed to .old.<ext>) ✗

This script finishes the remaining steps for a specified TranscodeAttempt.
Idempotent: if any step is already done, it is skipped.

Pre-req: stop the worker before running. Direct DB writes; the running
worker poller could race against it.

Usage:
    py Scripts/Smoke/RecoverPartialReplacement.py <TranscodeAttemptId>
"""

import sys
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from Core.Database.DatabaseService import DatabaseService
from Repositories.DatabaseManager import DatabaseManager
from Features.FileReplacement.FileReplacementBusinessService import FileReplacementBusinessService
from Core.WorkerContext import WorkerContext


def Step(N, Title):
    print(f"\n[{N}] {Title}")


def Fail(Reason):
    print(f"FAIL: {Reason}")
    sys.exit(1)


def Main(TranscodeAttemptId: int):
    Db = DatabaseService()
    Mgr = DatabaseManager()
    Replacement = FileReplacementBusinessService(Mgr)
    Ctx = WorkerContext.Current()

    Step(1, f"Snapshot attempt {TranscodeAttemptId}")
    Rows = Db.ExecuteQuery(
        "SELECT FilePath, Disposition, DispositionReason, VMAF, FileReplaced FROM TranscodeAttempts WHERE Id = %s",
        (TranscodeAttemptId,),
    )
    if not Rows:
        Fail(f"TranscodeAttempt {TranscodeAttemptId} not found.")
    A = Rows[0]
    print(f"    FilePath        = {A['FilePath']}")
    print(f"    Disposition     = {A['Disposition']}")
    print(f"    VMAF            = {A['VMAF']}")
    print(f"    FileReplaced    = {A['FileReplaced']}")

    if A['FileReplaced']:
        print("    Already FileReplaced=TRUE. Nothing to do.")
        return

    if A['Disposition'] not in ('Replace', 'BypassReplace'):
        Fail(f"Disposition is {A['Disposition']}; expected Replace or BypassReplace. Run the smoke script first.")

    Step(2, "Compute canonical paths")
    OriginalCanonical = A['FilePath']
    OriginalDir = os.path.dirname(OriginalCanonical)
    OriginalBase = os.path.splitext(os.path.basename(OriginalCanonical))[0]
    OriginalExt = os.path.splitext(os.path.basename(OriginalCanonical))[1]
    NewCanonical = os.path.join(OriginalDir, OriginalBase + "-mv.mp4")
    OrigBackupCanonical = OriginalCanonical + ".orig"
    print(f"    Original (canonical)          = {OriginalCanonical}")
    print(f"    Original .orig backup         = {OrigBackupCanonical}")
    print(f"    New (canonical, -mv)          = {NewCanonical}")

    Step(3, "Translate to local paths and verify on disk")
    if Ctx and Ctx.PathTranslation:
        Translate = Ctx.PathTranslation.ToLocalPath
    else:
        Translate = lambda P: P
    LocalNew = Translate(NewCanonical)
    LocalOrigBackup = Translate(OrigBackupCanonical)
    print(f"    Local -mv path                = {LocalNew}")
    print(f"    Local .orig path              = {LocalOrigBackup}")
    if not os.path.exists(LocalNew):
        Fail(f"Expected -mv file not found at {LocalNew}. Cannot recover -- file may need manual inspection.")
    print("    -mv file exists on disk.")

    Step(4, "Re-probe + update MediaFiles")
    UpdateResult = Replacement._UpdateMediaFilesAfterReplacement(OriginalCanonical, NewCanonical)
    if UpdateResult.get('Success'):
        print("    MediaFiles row updated successfully.")
    else:
        # Match the existing tolerance in _ProcessCompleteFileReplacement: MediaFiles
        # update failure is non-fatal -- DB row will reconcile on next probe.
        print(f"    MediaFiles update failed (non-fatal): {UpdateResult}")

    Step(5, "Settle .orig backup per KeepSource")
    KeepSource = Mgr.GetKeepSourceSetting(TranscodeAttemptId)
    print(f"    KeepSource = {KeepSource}")
    if os.path.exists(LocalOrigBackup):
        if KeepSource:
            LegacyOldLocal = LocalOrigBackup[:-len(".orig")] + ".old" + OriginalExt
            LegacyOldLocal = os.path.splitext(LocalOrigBackup)[0]  # strips .orig
            # Above might double-strip; recompute cleanly:
            BasePart = os.path.basename(LocalOrigBackup)
            if BasePart.endswith(OriginalExt + ".orig"):
                LegacyOldLocal = os.path.join(
                    os.path.dirname(LocalOrigBackup),
                    BasePart[:-(len(OriginalExt) + len(".orig"))] + ".old" + OriginalExt
                )
            else:
                # Fallback path computation
                LegacyOldLocal = LocalOrigBackup.replace(".orig", ".old")
            try:
                os.rename(LocalOrigBackup, LegacyOldLocal)
                print(f"    Renamed .orig -> {LegacyOldLocal}")
            except OSError as Ex:
                print(f"    NOTE: could not rename .orig (left at {LocalOrigBackup}): {Ex}")
        else:
            try:
                os.remove(LocalOrigBackup)
                print(f"    Deleted .orig backup at {LocalOrigBackup}")
            except OSError as Ex:
                print(f"    NOTE: could not delete .orig (left at {LocalOrigBackup}): {Ex}")
    else:
        print("    No .orig backup present; nothing to settle.")

    Step(6, "Mark TranscodeAttempts FileReplaced=TRUE + ReplacementType")
    ReplType = 'Bypass' if A['Disposition'] == 'BypassReplace' else 'Auto'
    Db.ExecuteNonQuery(
        """
        UPDATE TranscodeAttempts
        SET FileReplaced = TRUE,
            FileReplacedDate = %s,
            ReplacementType = %s
        WHERE Id = %s
        """,
        (datetime.now(timezone.utc), ReplType, TranscodeAttemptId),
    )
    print(f"    FileReplaced=TRUE, ReplacementType={ReplType}")

    Step(7, "Clean up TemporaryFilePaths row")
    Db.ExecuteNonQuery(
        "DELETE FROM TemporaryFilePaths WHERE TranscodeAttemptId = %s",
        (TranscodeAttemptId,),
    )
    print(f"    Deleted TemporaryFilePaths row for attempt {TranscodeAttemptId}")

    Step(8, "Verify")
    Rows = Db.ExecuteQuery(
        "SELECT FilePath, Disposition, DispositionReason, VMAF, FileReplaced, FileReplacedDate, ReplacementType FROM TranscodeAttempts WHERE Id = %s",
        (TranscodeAttemptId,),
    )
    V = Rows[0]
    print(f"    Disposition       = {V['Disposition']}")
    print(f"    Reason            = {V['DispositionReason']}")
    print(f"    VMAF              = {V['VMAF']}")
    print(f"    FileReplaced      = {V['FileReplaced']}")
    print(f"    FileReplacedDate  = {V['FileReplacedDate']}")
    print(f"    ReplacementType   = {V['ReplacementType']}")

    print("\nPASS")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    Main(int(sys.argv[1]))
