import argparse
import os
import sys

ScriptDir = os.path.dirname(os.path.abspath(__file__))
RepoRoot = os.path.dirname(ScriptDir)
if RepoRoot not in sys.path:
    sys.path.insert(0, RepoRoot)

from Core.Database.DatabaseService import DatabaseService


PATH_MAP_QUERY = (
    "SELECT sr.CanonicalPrefix, srr.AbsolutePath "
    "FROM StorageRootResolutions srr "
    "JOIN StorageRoots sr ON sr.Id = srr.StorageRootId "
    "WHERE srr.WorkerName = %s AND srr.IsActive = TRUE"
)

CANDIDATE_QUERY = (
    "SELECT m.Id, m.FilePath, "
    "EXISTS(SELECT 1 FROM TranscodeAttempts ta "
    "WHERE ta.MediaFileId = m.Id AND ta.Success = TRUE AND ta.FileReplaced = TRUE) "
    "AS HadSuccessfulRemux "
    "FROM MediaFiles m "
    "WHERE m.FilePath ILIKE '%%.mp4' "
    "ORDER BY m.Id"
)

CLEAR_COMPLIANCE_SQL = (
    "UPDATE MediaFiles SET WorkBucket = NULL, OperationsNeededCsv = NULL, "
    "ComplianceGateBlocked = NULL, IsCompliant = NULL, ComplianceEvaluatedAt = NULL "
    "WHERE Id = %s"
)

FLAG_ORPHAN_SQL = (
    "UPDATE MediaFiles SET AdmissionDeferReason = 'manual_review_orig_recovery_orphan' "
    "WHERE Id = %s"
)


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def BuildPathMap(Db, WorkerName):
    """Worker-local prefix map for canonical -> local translation; raises if no active resolutions."""
    Rows = Db.ExecuteQuery(PATH_MAP_QUERY, (WorkerName,))
    if not Rows:
        raise RuntimeError(f"No StorageRootResolutions rows for worker '{WorkerName}'")
    return {Row["CanonicalPrefix"]: Row["AbsolutePath"] for Row in Rows}


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def TranslateToLocal(CanonicalPath, PathMap):
    """Substitute canonical prefix for the worker-local prefix; case-insensitive prefix match."""
    if not CanonicalPath:
        return CanonicalPath
    for Prefix, LocalPrefix in PathMap.items():
        if CanonicalPath.upper().startswith(Prefix.upper()):
            Tail = CanonicalPath[len(Prefix):]
            if "/" in LocalPrefix and "\\" in Tail:
                Tail = Tail.replace("\\", "/")
            return LocalPrefix + Tail
    return CanonicalPath


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def RecoverAtRiskFile(Db, MediaFileId, LocalMp4, Execute):
    """Restore the original .orig file over the failed .mp4 and clear compliance flags so next compliance recompute reassesses."""
    LocalOrig = LocalMp4 + ".orig"
    if not os.path.exists(LocalMp4) or not os.path.exists(LocalOrig):
        return "skip_disk_state_changed"
    if not Execute:
        return "dry_run"
    os.remove(LocalMp4)
    os.rename(LocalOrig, LocalMp4)
    Db.ExecuteNonQuery(CLEAR_COMPLIANCE_SQL, (MediaFileId,))
    return "recovered"


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def FlagOrphan(Db, MediaFileId, Execute):
    """Flag a MediaFile whose disk artifacts are missing for manual operator review."""
    if not Execute:
        return "dry_run"
    Db.ExecuteNonQuery(FLAG_ORPHAN_SQL, (MediaFileId,))
    return "flagged"


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def Main():
    """Recovery script for bug-0032-era .orig survivors; defaults to dry-run -- pass --execute to commit."""
    Parser = argparse.ArgumentParser()
    Parser.add_argument("--worker", required=True)
    Parser.add_argument("--execute", action="store_true", help="Apply changes (default is dry-run)")
    Args = Parser.parse_args()

    if Args.execute:
        print("EXECUTE MODE: workers MUST be paused before running. Disk renames + DB writes will commit.")
        print()
    else:
        print("DRY-RUN MODE. Pass --execute to apply.")
        print()

    Db = DatabaseService()
    PathMap = BuildPathMap(Db, Args.worker)
    print(f"Worker: {Args.worker}")
    print(f"Path map: {PathMap}")
    print()

    Unreachable = [P for P in PathMap.values() if not os.path.isdir(P)]
    if Unreachable:
        print(f"ABORT: storage roots not reachable: {Unreachable}")
        print("Refusing to scan -- every file would look 'missing' and get falsely flagged.")
        sys.exit(2)

    Rows = Db.ExecuteQuery(CANDIDATE_QUERY)

    AtRisk = []
    Orphans = []
    for Row in Rows:
        LocalMp4 = TranslateToLocal(Row["FilePath"], PathMap)
        LocalOrig = LocalMp4 + ".orig"
        Mp4Exists = os.path.exists(LocalMp4)
        OrigExists = os.path.exists(LocalOrig)
        if Mp4Exists and OrigExists and not Row["HadSuccessfulRemux"]:
            AtRisk.append((Row["Id"], Row["FilePath"], LocalMp4))
        elif not Mp4Exists and not OrigExists:
            Orphans.append((Row["Id"], Row["FilePath"]))

    print(f"At-risk recovery candidates: {len(AtRisk)}")
    print(f"Orphan flag candidates:      {len(Orphans)}")
    print()

    print("--- At-risk recovery ---")
    for MediaFileId, _, LocalMp4 in AtRisk:
        Result = RecoverAtRiskFile(Db, MediaFileId, LocalMp4, Args.execute)
        print(f"  id={MediaFileId} {Result}: {LocalMp4}")
    print()

    print("--- Orphan flagging ---")
    FlaggedCount = 0
    for MediaFileId, _ in Orphans:
        Result = FlagOrphan(Db, MediaFileId, Args.execute)
        if Result == "flagged":
            FlaggedCount += 1
    if Args.execute:
        print(f"  {FlaggedCount} of {len(Orphans)} orphans flagged with AdmissionDeferReason='manual_review_orig_recovery_orphan'")
    else:
        print(f"  {len(Orphans)} orphans would be flagged")
    print()

    if not Args.execute:
        print("Re-run with --execute to apply.")


if __name__ == "__main__":
    Main()
