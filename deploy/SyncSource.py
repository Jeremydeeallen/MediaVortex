"""Filtered source sync to a remote Linux/Docker host for builds.

Reads .deployignore for exclusion patterns (directory and file name globs
matched per path component).  Additive: new source files are included by
default.  Targeted: known artifacts (.git, venv, __pycache__, Tests, etc.)
are excluded.

Uses tar-over-ssh for transport -- no rsync or extra tools needed beyond
ssh (already a deploy prerequisite).

Usage:
    py deploy/SyncSource.py root@10.0.0.42 /tmp/mediavortex-build
    py deploy/SyncSource.py root@10.0.0.42 /tmp/mediavortex-build --dry-run
"""

import fnmatch
import os
import subprocess
import sys
import tarfile
from pathlib import Path


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
            FullPath = os.path.join(DirPath, FileName)
            ArcName = f"{RelDir}/{FileName}" if RelDir else FileName
            # Normalize Windows backslashes for tar portability.
            ArcName = ArcName.replace("\\", "/")
            yield FullPath, ArcName


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def Main():
    import argparse

    Parser = argparse.ArgumentParser(
        description="Sync MediaVortex source to a remote host (filtered)."
    )
    Parser.add_argument("target", help="SSH target, e.g. root@10.0.0.42")
    Parser.add_argument("remote_dir", help="Remote directory, e.g. /tmp/mediavortex-build")
    Parser.add_argument("--dry-run", action="store_true",
                        help="List files that would be synced; do not transfer.")
    Args = Parser.parse_args()

    Target = Args.target
    RemoteDir = Args.remote_dir
    Patterns = _LoadPatterns()
    print(f"Loaded {len(Patterns)} exclusion patterns from .deployignore")

    # Collect file list (used by both dry-run and real sync).
    Files = list(_CollectFiles(ROOT_DIR, Patterns))
    print(f"Collected {len(Files)} files to sync")

    if Args.dry_run:
        for _, ArcName in Files:
            print(f"  {ArcName}")
        return

    # --- 1. Prepare remote directory ----------------------------------------
    print(f"Preparing {Target}:{RemoteDir} ...")
    R = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=5", Target,
         f"rm -rf {RemoteDir} && mkdir -p {RemoteDir}"],
        capture_output=True, text=True, timeout=30,
    )
    if R.returncode != 0:
        print(f"ERROR: Failed to prepare remote dir: {R.stderr.strip()}")
        sys.exit(1)

    # --- 2. Stream tar archive to remote ------------------------------------
    print("Streaming source via tar-over-ssh ...")
    Proc = subprocess.Popen(
        ["ssh", "-o", "ConnectTimeout=5", Target,
         f"tar xf - -C {RemoteDir}"],
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


if __name__ == "__main__":
    Main()
