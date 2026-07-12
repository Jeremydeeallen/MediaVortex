# directive: transcode-flow-canonical | # see worker-deploy.C14
import fnmatch
import os
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from Core.Path.LocalPath import LocalJoin


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
IGNORE_FILE = ROOT_DIR / ".deployignore"


# ---------------------------------------------------------------------------
# Pattern loading and matching
# ---------------------------------------------------------------------------

def _LoadPatterns() -> list:
    """Load glob patterns from .deployignore (one per line, # = comment)."""
    if not IGNORE_FILE.exists():
        print(f"WARNING: {IGNORE_FILE} not found -- syncing everything")
        return []
    Patterns = []
    for Line in IGNORE_FILE.read_text(encoding="utf-8").splitlines():
        Stripped = Line.strip()
        if Stripped and not Stripped.startswith("#"):
            Patterns.append(Stripped)
    return Patterns


def _MatchesAny(Name: str, Patterns: list) -> bool:
    """True if *Name* matches any fnmatch pattern in the list."""
    return any(fnmatch.fnmatch(Name, P) for P in Patterns)


def _CollectFiles(RootDir: Path, Patterns: list):
    """Walk the tree, prune excluded dirs, yield (abs_path, tar_arcname)."""
    for DirPath, DirNames, FileNames in os.walk(RootDir):
        # Prune directories in-place so os.walk skips them entirely.
        DirNames[:] = sorted(
            D for D in DirNames if not _MatchesAny(D, Patterns)
        )

        RelDir = os.path.relpath(DirPath, RootDir)
        if RelDir == ".":
            RelDir = ""

        for FileName in FileNames:
            if _MatchesAny(FileName, Patterns):
                continue
            FullPath = LocalJoin(DirPath, FileName)
            ArcName = f"{RelDir}/{FileName}" if RelDir else FileName
            # Normalize Windows backslashes for tar portability.
            ArcName = ArcName.replace("\\", "/")
            yield FullPath, ArcName


# directive: transcode-flow-canonical
def _PruneStale(Target, RemoteDir, Files):
    """Delete remote files not present in the local manifest. Directory tree preserved."""
    Manifest = {ArcName for _, ArcName in Files}
    List = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=5", Target, f"cd {RemoteDir} && find . -type f -printf '%P\\n'"],
        capture_output=True, text=True, timeout=60,
    )
    if List.returncode != 0:
        print(f"WARNING: prune skipped -- remote find failed: {List.stderr.strip()}")
        return
    RemoteFiles = {L.strip() for L in List.stdout.splitlines() if L.strip()}
    Stale = sorted(RemoteFiles - Manifest)
    if not Stale:
        print("Prune: no stale files.")
        return
    print(f"Prune: removing {len(Stale)} stale file(s) ...")
    Rm = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=5", Target, f"cd {RemoteDir} && xargs -0 -r rm -f --"],
        input="\0".join(Stale) + "\0",
        capture_output=True, text=True, timeout=120,
    )
    if Rm.returncode != 0:
        print(f"WARNING: prune partial -- rm failed: {Rm.stderr.strip()}")
        return
    print(f"Prune: {len(Stale)} file(s) removed.")


def Main():
    import argparse

    Parser = argparse.ArgumentParser(description="Sync MediaVortex source to a remote host (filtered).")
    Parser.add_argument("target", help="SSH target, e.g. root@10.0.0.42")
    Parser.add_argument("remote_dir", help="Remote directory, e.g. /tmp/mediavortex-build")
    Parser.add_argument("--dry-run", action="store_true", help="List files that would be synced; do not transfer.")
    Parser.add_argument("--prune", action="store_true", help="After sync, delete remote files not present in the local manifest. Requires workers to be stopped; orchestrators own the lifecycle guard.")
    Args = Parser.parse_args()

    Target = Args.target
    RemoteDir = Args.remote_dir
    Patterns = _LoadPatterns()
    print(f"Loaded {len(Patterns)} exclusion patterns from .deployignore")

    Files = list(_CollectFiles(ROOT_DIR, Patterns))
    print(f"Collected {len(Files)} files to sync")

    if Args.dry_run:
        for _, ArcName in Files:
            print(f"  {ArcName}")
        return

    # directive: transcode-flow-canonical -- mkdir -p only; NEVER rm -rf (would invalidate a live worker's cwd inode). Stale files handled by --prune below.
    print(f"Preparing {Target}:{RemoteDir} (in-place; preserving directory inode) ...")
    R = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=5", Target, f"mkdir -p {RemoteDir}"],
        capture_output=True, text=True, timeout=30,
    )
    if R.returncode != 0:
        print(f"ERROR: Failed to prepare remote dir: {R.stderr.strip()}")
        sys.exit(1)

    print("Streaming source via tar-over-ssh ...")
    Proc = subprocess.Popen(
        ["ssh", "-o", "ConnectTimeout=5", Target, f"tar xf - -C {RemoteDir}"],
        stdin=subprocess.PIPE,
    )
    try:
        with tarfile.open(fileobj=Proc.stdin, mode="w|") as Tar:
            for FullPath, ArcName in Files:
                Tar.add(FullPath, arcname=ArcName)
    finally:
        Proc.stdin.close()
    ExitCode = Proc.wait()
    if ExitCode != 0:
        print(f"ERROR: Remote tar extraction failed (exit {ExitCode})")
        sys.exit(1)

    print(f"Done -- {len(Files)} files synced to {Target}:{RemoteDir}")

    if Args.prune:
        _PruneStale(Target, RemoteDir, Files)


if __name__ == "__main__":
    Main()
