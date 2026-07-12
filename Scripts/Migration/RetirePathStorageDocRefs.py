# directive: transcode-flow-canonical | # see worker-deploy.C14
import os
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SKIP_DIRS = {".claude/directives/closed", ".git", "venv", "__pycache__"}
SKIP_FILES = {"Scripts/Migration/RetirePathStorageDocRefs.py"}
DELETE_FILES = ["path-storage.feature.md", "path-storage.flow.md"]
TEST_SKIP_PATTERNS = ["Tests/Unit/test_"]
HOOK_FILE = ".claude/hooks/pre-edit-standards.ps1"

HOOK_MAP_OLD_TO_NEW = {
    "'Core.PathStorage.ParentDir(path)  -- shape-preserving'": "'Core.Path.LocalPath.LocalDirname(path)  -- local wrapper; use Core.Path.Path for canonical DB paths'",
    "'Core.PathStorage.LastSegment(path)  -- shape-preserving'": "'Core.Path.LocalPath.LocalBasename(path)  -- local wrapper; use Core.Path.Path for canonical DB paths'",
    "'Core.PathStorage.Join(base, child)  -- preserves base shape'": "'Core.Path.LocalPath.LocalJoin(base, child)  -- local wrapper; use Core.Path.Path for canonical DB paths'",
    "'Core.PathStorage.SplitExt(path) or LastSegment+ParentDir'": "'Core.Path.LocalPath.LocalSplitExt(path) or LocalBasename+LocalDirname'",
    "'Core.PathStorage.SplitExt(path)'": "'Core.Path.LocalPath.LocalSplitExt(path)'",
    "'Core.PathStorage.Exists(canonical, worker)  OR  Core.PathStorage.LocalExists(local_path)'": "'Core.Path.Path(sid, rel).Resolve(worker) then Core.Path.LocalPath.LocalExists(local)'",
    "'Core.PathStorage.IsFile(canonical, worker)  OR  Core.PathStorage.LocalIsFile(local_path)'": "'Core.Path.Path(sid, rel).Resolve(worker) then Core.Path.LocalPath.LocalIsFile(local)'",
    "'Core.PathStorage.IsDir(canonical, worker)  OR  Core.PathStorage.LocalIsDir(local_path)'": "'Core.Path.Path(sid, rel).Resolve(worker) then Core.Path.LocalPath.LocalIsDir(local)'",
    "'Core.PathStorage.GetSize(canonical, worker)  OR  Core.PathStorage.LocalGetSize(local_path)'": "'Core.Path.Path(sid, rel).Resolve(worker) then Core.Path.LocalPath.LocalGetSize(local)'",
    "'Core.PathStorage.GetMTime(canonical, worker)  OR  Core.PathStorage.LocalGetMTime(local_path)'": "'Core.Path.Path(sid, rel).Resolve(worker) then Core.Path.LocalPath.LocalGetMTime(local)'",
    "'Core.PathStorage.ToLocal(canonical, worker) if you need a local-absolute path'": "'Core.Path.Path(sid, rel).Resolve(worker) returns a worker-local absolute path'",
    "'Core.PathStorage.Normalize(path)  -- shape-preserving (picks ntpath/posixpath by input shape)'": "'Core.Path.Path constructor normalizes; for local strings use Core.Path.LocalPath'",
    "'Core.PathStorage.PathsEqual(a, b)  -- equality after Normalize; auto-detects case sensitivity from shape'": "'Core.Path.LocalPath.LocalSamePath(a, b) for local strings; Core.Path.Path equality by tuple for canonical'",
}

R6_ERROR_TEMPLATE_OLD = "R6 Path shape: $FilePath line $($I+1) does .replace().split() on a path-named variable. FilePath is a mix of UNC, drive-letter, and POSIX shapes. Path forward: use Core.PathStorage.LastSegment(path) for filename, Core.PathStorage.ParentDir(path) for directory -- both shape-preserving for UNC/drive/POSIX. Run ``/mediavortex-paths`` for the full lookup + canonical-vs-local decision before retrying. See path-storage.feature.md."
R6_ERROR_TEMPLATE_NEW = "R6 Path shape: $FilePath line $($I+1) does .replace().split() on a path-named variable. FilePath is a mix of UNC, drive-letter, and POSIX shapes. Path forward: use Core.Path.LocalPath.LocalBasename(path) for filename, Core.Path.LocalPath.LocalDirname(path) for directory (local strings after Path.Resolve(worker)); for canonical DB paths use Core.Path.Path. Run ``/mediavortex-paths`` for the full lookup + canonical-vs-local decision before retrying. See Core/Path/path.feature.md."

# Exemption line for the retired module is dead code -- delete it.
DEAD_EXEMPTION_OLD = "    if ($NormR6 -match '/Core/PathStorage\\.py$') { return $null }\n"

# Regex boundaries preserve PathStorageRoots (live class in Core.Path.PathStorageRoots) untouched.
PROSE_REPLACEMENTS = [
    (re.compile(r"\bCore/PathStorage\.py\b"), "Core/Path/LocalPath.py + Core/Path/Path.py"),
    (re.compile(r"\bCore/PathStorage(?!Roots)\b"), "Core/Path"),
    (re.compile(r"\bCore\.PathStorage(?!Roots)\b"), "Core.Path.LocalPath / Core.Path.Path"),
    (re.compile(r"\bpath-storage\.feature\.md\b"), "Core/Path/path.feature.md"),
    (re.compile(r"\bpath-storage\.flow\.md\b"), "Core/Path/path.feature.md"),
]


# directive: transcode-flow-canonical
def _RelPath(P):
    return P.relative_to(REPO_ROOT).as_posix()


# directive: transcode-flow-canonical
def _IsSkipped(Rel):
    for D in SKIP_DIRS:
        if Rel.startswith(D + "/") or Rel == D:
            return True
    if Rel in SKIP_FILES:
        return True
    for T in TEST_SKIP_PATTERNS:
        if Rel.startswith(T):
            return True
    return False


# directive: transcode-flow-canonical
def _CollectCandidates():
    Candidates = []
    for DirRoot, DirNames, FileNames in os.walk(REPO_ROOT):
        DirNames[:] = [D for D in DirNames if D not in ("__pycache__", ".git", "venv")]
        for FileName in FileNames:
            AbsPath = Path(DirRoot) / FileName
            Rel = _RelPath(AbsPath)
            if _IsSkipped(Rel):
                continue
            if not FileName.endswith((".md", ".ps1", ".json", ".py")):
                continue
            try:
                Content = AbsPath.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "PathStorage" in Content:
                Candidates.append((AbsPath, Rel, Content))
    return Candidates


# directive: transcode-flow-canonical
def _UpdateHookFile(Content):
    Updated = Content
    for Old, New in HOOK_MAP_OLD_TO_NEW.items():
        Updated = Updated.replace(Old, New)
    Updated = Updated.replace(R6_ERROR_TEMPLATE_OLD, R6_ERROR_TEMPLATE_NEW)
    Updated = Updated.replace(DEAD_EXEMPTION_OLD, "")
    for Pat, New in PROSE_REPLACEMENTS:
        Updated = Pat.sub(New, Updated)
    return Updated


# directive: transcode-flow-canonical
def _UpdateProseFile(Content):
    Updated = Content
    for Pat, New in PROSE_REPLACEMENTS:
        Updated = Pat.sub(New, Updated)
    return Updated


# directive: transcode-flow-canonical
def Main(DryRun=False):
    Candidates = _CollectCandidates()
    print(f"Found {len(Candidates)} candidate files referencing PathStorage.")
    WrittenCount = 0
    DeletedCount = 0
    UnchangedCount = 0
    for AbsPath, Rel, Content in Candidates:
        if Path(Rel).name in DELETE_FILES:
            print(f"  DELETE {Rel}")
            if not DryRun:
                AbsPath.unlink()
            DeletedCount += 1
            continue
        Updated = _UpdateHookFile(Content) if Rel == HOOK_FILE else _UpdateProseFile(Content)
        if Updated == Content:
            UnchangedCount += 1
            continue
        BeforeHits = Content.count("PathStorage")
        AfterHits = Updated.count("PathStorage")
        print(f"  WRITE  {Rel}  ({BeforeHits}->{AfterHits} PathStorage hits)")
        if not DryRun:
            AbsPath.write_text(Updated, encoding="utf-8")
        WrittenCount += 1
    print()
    print(f"Summary: WRITE={WrittenCount}  DELETE={DeletedCount}  UNCHANGED={UnchangedCount}")
    if DryRun:
        print("(dry-run -- no files touched)")


if __name__ == "__main__":
    Main(DryRun=("--dry-run" in sys.argv))
