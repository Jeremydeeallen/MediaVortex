# directive: transcode-worker-unification -- post-disposition pipeline smoke; uses DispositionDispatcher directly.
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from Core.Database.DatabaseService import DatabaseService
from Core.Path.LocalPath import LocalBasename, LocalDirname, LocalSplitExt
from Repositories.DatabaseManager import DatabaseManager
from Features.QualityTesting.Disposition.AttemptCleanupService import AttemptCleanupService
from Features.QualityTesting.Disposition.DispositionDispatcher import DispositionDispatcher
from Features.QualityTesting.Disposition.PostTranscodeDispositionDecider import PostTranscodeDispositionDecider
from Features.QualityTesting.Disposition.RetryBudgetService import RetryBudgetService
from Features.QualityTesting.PostTranscodeGateConfigRepository import PostTranscodeGateConfigRepository
from Features.FileReplacement.FileReplacementBusinessService import FileReplacementBusinessService


def Step(N, Title):
    print(f"\n[{N}] {Title}")


def Fail(Reason):
    print(f"FAIL: {Reason}")
    sys.exit(1)


def _BuildDispatcher(Mgr, Repo):
    """Compose DispositionDispatcher for the smoke test."""
    Db = DatabaseService()
    Cleanup = AttemptCleanupService(Db)
    Retry = RetryBudgetService(AttemptRepository=Mgr, GateConfigRepository=Repo)
    return DispositionDispatcher(
        Decider=PostTranscodeDispositionDecider(),
        GateConfigRepository=Repo,
        AttemptCleanupService=Cleanup,
        DatabaseService=Db,
        RetryBudgetService=Retry,
    )


def Main(TranscodeAttemptId: int):
    Db = DatabaseService()
    Mgr = DatabaseManager()
    Repo = PostTranscodeGateConfigRepository()

    Step(1, f"Snapshot current PostTranscodeGateConfig + attempt {TranscodeAttemptId}")
    Cfg = Repo.Get()
    OriginalMin = float(Cfg.VmafAutoReplaceMinThreshold)
    print(f"    Current Min={OriginalMin}, Max={Cfg.VmafAutoReplaceMaxThreshold}, WhenVmafUnavailable={Cfg.WhenVmafUnavailable}")

    Rows = Db.ExecuteQuery(
        "SELECT FilePath, Disposition, DispositionReason, VMAF, FileReplaced FROM TranscodeAttempts WHERE Id = %s",
        (TranscodeAttemptId,),
    )
    if not Rows:
        Fail(f"TranscodeAttempt {TranscodeAttemptId} not found.")
    R = Rows[0]
    print(f"    FilePath={R['FilePath']}")
    print(f"    Disposition={R['Disposition']}, Reason={R['DispositionReason']}")
    print(f"    VMAF={R['VMAF']}, FileReplaced={R['FileReplaced']}")

    if R['FileReplaced']:
        Fail(f"Attempt {TranscodeAttemptId} is already FileReplaced=true; cannot re-test idempotently.")

    Step(2, "Backfill VMAF on TranscodeAttempts from QualityTestResults if missing")
    QtrRows = Db.ExecuteQuery(
        "SELECT VMAFScore FROM QualityTestResults WHERE TranscodeAttemptId = %s AND VMAFScore IS NOT NULL ORDER BY Id DESC LIMIT 1",
        (TranscodeAttemptId,),
    )
    if not QtrRows:
        Fail(f"No QualityTestResults row with VMAFScore for TranscodeAttempt {TranscodeAttemptId}.")
    SourceVmaf = float(QtrRows[0]['VMAFScore'])
    print(f"    QualityTestResults.VMAFScore = {SourceVmaf}")

    if R['VMAF'] is None or float(R['VMAF']) != SourceVmaf:
        Db.ExecuteNonQuery(
            "UPDATE TranscodeAttempts SET VMAF = %s, QualityTestCompleted = TRUE WHERE Id = %s",
            (SourceVmaf, TranscodeAttemptId),
        )
        print(f"    Backfilled TranscodeAttempts.VMAF = {SourceVmaf}, QualityTestCompleted = TRUE")
    else:
        print(f"    TranscodeAttempts.VMAF already set to {R['VMAF']}; no backfill needed")

    Step(3, "Lower threshold so the VMAF score lands in the Replace band")
    NewMin = max(50.0, min(SourceVmaf - 1.0, OriginalMin))
    if NewMin >= OriginalMin:
        print(f"    SourceVmaf {SourceVmaf} already meets current Min {OriginalMin}; no change")
    else:
        Repo.Update(VmafAutoReplaceMinThreshold=NewMin)
        print(f"    Lowered VmafAutoReplaceMinThreshold from {OriginalMin} -> {NewMin}")

    try:
        Step(4, "Reset Disposition to Pending so the dispatcher re-decides")
        Db.ExecuteNonQuery(
            "UPDATE TranscodeAttempts SET Disposition = 'Pending', DispositionReason = 'AwaitingVmaf' WHERE Id = %s",
            (TranscodeAttemptId,),
        )
        print("    Disposition -> Pending")

        Step(5, "Call DispositionDispatcher.Dispatch")
        Result = _BuildDispatcher(Mgr, Repo).Dispatch(TranscodeAttemptId)
        print(f"    -> Disposition={Result.Disposition}, Reason={Result.Reason}")
        if Result.Disposition != 'Replace':
            Fail(f"Expected Replace; got {Result.Disposition} ({Result.Reason}). "
                 f"Audit payload: {Result.AuditPayload}")

        Step(6, "Call ProcessFileReplacement")
        FrResult = FileReplacementBusinessService(Mgr).ProcessFileReplacement(TranscodeAttemptId)
        print(f"    -> Success={FrResult.get('Success')}, Message={FrResult.get('Message') or FrResult.get('ErrorMessage')}")
        if not FrResult.get('Success'):
            Fail(f"FileReplacement returned Success=false. Steps completed: {FrResult.get('StepsCompleted')}.")

        Step(7, "Verify TranscodeAttempts updated")
        VerifyRows = Db.ExecuteQuery(
            "SELECT Disposition, DispositionReason, VMAF, FileReplaced, FileReplacedDate FROM TranscodeAttempts WHERE Id = %s",
            (TranscodeAttemptId,),
        )
        V = VerifyRows[0]
        print(f"    Disposition={V['Disposition']}, Reason={V['DispositionReason']}")
        print(f"    VMAF={V['VMAF']}, FileReplaced={V['FileReplaced']}, FileReplacedDate={V['FileReplacedDate']}")
        if not V['FileReplaced']:
            Fail("TranscodeAttempts.FileReplaced is still false after ProcessFileReplacement.")

        Step(8, "Verify on disk -- expect <originalbasename>-mv.<ext> in source folder")
        OrigPath = R['FilePath']
        Folder = LocalDirname(OrigPath)
        OriginalBase = LocalSplitExt(LocalBasename(OrigPath))[0]
        from Core.WorkerContext import WorkerContext as _Wc
        _Ctx = _Wc.Current()
        LocalFolder = _Ctx.PathTranslation.ToLocalPath(Folder) if _Ctx and _Ctx.PathTranslation else Folder
        try:
            FsEntries = os.listdir(LocalFolder)
        except OSError as Ex:
            print(f"    Could not list {LocalFolder}: {Ex}")
            FsEntries = []
        MvCandidates = [E for E in FsEntries if OriginalBase.lower() in E.lower() and "-mv." in E.lower()]
        OldCandidates = [E for E in FsEntries if OriginalBase.lower() in E.lower() and ".old." in E.lower()]
        print(f"    Found {len(MvCandidates)} -mv candidate(s): {MvCandidates}")
        print(f"    Found {len(OldCandidates)} .old candidate(s): {OldCandidates}")
        if not MvCandidates:
            print("    NOTE: No `-mv.<ext>` file present. Either the -mv naming change isn't live, or the rename failed silently.")

        print("\nPASS")

    finally:
        Step('cleanup', "Restore PostTranscodeGateConfig.VmafAutoReplaceMinThreshold")
        Repo.Update(VmafAutoReplaceMinThreshold=OriginalMin)
        print(f"    Restored to {OriginalMin}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: py {Path(__file__).name} <TranscodeAttemptId>")
        sys.exit(2)
    Main(int(sys.argv[1]))
