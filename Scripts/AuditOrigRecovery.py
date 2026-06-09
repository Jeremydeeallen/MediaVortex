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
    "SELECT m.Id, m.FilePath, m.WorkBucket, m.IsCompliant, "
    "EXISTS(SELECT 1 FROM TranscodeAttempts ta "
    "WHERE ta.MediaFileId = m.Id AND ta.Success = TRUE AND ta.FileReplaced = TRUE) "
    "AS HadSuccessfulRemux "
    "FROM MediaFiles m "
    "WHERE m.FilePath ILIKE '%%.mp4' "
    "ORDER BY m.Id"
)


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def BuildPathMap(WorkerName):
    """Worker-local prefix map for canonical -> local translation; raises if no active resolutions."""
    Rows = DatabaseService().ExecuteQuery(PATH_MAP_QUERY, (WorkerName,))
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
def Main():
    """Audit script for bug-0032-era .orig survivors; classifies MediaFiles into four buckets and surfaces stale WorkBucket='Remux' + IsCompliant=true rows."""
    Parser = argparse.ArgumentParser()
    Parser.add_argument("--worker", required=True)
    Parser.add_argument("--sample", type=int, default=10)
    Args = Parser.parse_args()

    PathMap = BuildPathMap(Args.worker)
    print(f"Worker: {Args.worker}")
    print(f"Path map: {PathMap}")
    print()

    Rows = DatabaseService().ExecuteQuery(CANDIDATE_QUERY)
    print(f"Candidate MediaFiles rows (FilePath like %.mp4): {len(Rows):,}")
    print()

    CategoryA, CategoryB, CategoryC, CategoryD, StaleRemuxRows = [], [], [], [], []
    for Row in Rows:
        LocalMp4 = TranslateToLocal(Row["FilePath"], PathMap)
        LocalOrig = LocalMp4 + ".orig"
        Mp4Exists = os.path.exists(LocalMp4)
        OrigExists = os.path.exists(LocalOrig)
        Tup = (Row["Id"], Row["FilePath"], LocalMp4)
        if Mp4Exists and OrigExists:
            (CategoryA if Row["HadSuccessfulRemux"] else CategoryB).append(Tup)
        elif Mp4Exists:
            CategoryC.append(Tup)
        elif not OrigExists:
            CategoryD.append(Tup)
        if Row["WorkBucket"] == "Remux" and Row["IsCompliant"] is True:
            StaleRemuxRows.append(Tup)

    print(f"  (a) .mp4 + .orig both exist, prior successful remux: {len(CategoryA):,}")
    print(f"  (b) .mp4 + .orig both exist, NO successful remux (DATA-LOSS RISK): {len(CategoryB):,}")
    print(f"  (c) .mp4 only, no .orig:                             {len(CategoryC):,}")
    print(f"  (d) neither exists (orphan DB row):                  {len(CategoryD):,}")
    print()
    print(f"Stale WorkBucket='Remux' AND IsCompliant=true:         {len(StaleRemuxRows):,}")
    print()

    for Label, Rs in [("category (a)", CategoryA), ("category (b) DATA-LOSS RISK", CategoryB), ("category (c)", CategoryC), ("category (d)", CategoryD)]:
        if not Rs:
            continue
        Limit = min(Args.sample, len(Rs))
        print(f"Sample of {Label} (first {Limit}):")
        for MediaFileId, _, LocalMp4 in Rs[:Limit]:
            print(f"  id={MediaFileId} {LocalMp4}")
        print()


if __name__ == "__main__":
    Main()
