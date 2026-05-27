"""Stamp VERSION + BUILD_INFO files into a MediaVortex repo root.

Writes two sibling files alongside this script's parent (or an explicit --target):

  <root>/VERSION       single-line full SHA from `git rev-parse HEAD` of <source>
  <root>/BUILD_INFO    three lines: commit, built_at (UTC ISO), built_by (hostname)

Both deploy scripts (`deploy/deploy-linux-worker.py` via Docker build-arg,
`deploy/deploy-windows-worker.py` via this helper) produce the same artifact
shape so `WorkerService.Main._ResolveWorkerVersion` has one reader.

The dev workstation never benefits from a local stamp -- the dev workstation
is the SOURCE of HEAD, not a deploy target -- so VERSION + BUILD_INFO are in
`.gitignore` and only written into target trees (the temp tar staging dir on
Windows deploy, or `/opt/mediavortex/` inside the Docker build context).

Usage:
  py Scripts/StampVersion.py                        # stamp THIS repo from THIS repo's HEAD
  py Scripts/StampVersion.py --target /tmp/build    # stamp /tmp/build from THIS repo's HEAD
  py Scripts/StampVersion.py --source /other/repo   # stamp THIS repo from /other/repo's HEAD
  py Scripts/StampVersion.py --sha abc1234          # stamp THIS repo with literal SHA
"""

from __future__ import annotations

import argparse
import datetime as _dt
import socket
import subprocess
import sys
from pathlib import Path

ScriptDir = Path(__file__).resolve().parent
RepoRoot = ScriptDir.parent


def _ResolveHead(SourceRoot: Path) -> str:
    """Return the full SHA of HEAD at SourceRoot, or empty string on any failure."""
    try:
        R = subprocess.run(
            ["git", "-C", str(SourceRoot), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if R.returncode == 0:
            return (R.stdout or "").strip()
    except Exception:
        pass
    return ""


def Stamp(TargetRoot: Path, Sha: str, BuiltBy: str | None = None) -> tuple[Path, Path]:
    """Write VERSION + BUILD_INFO to TargetRoot. Returns (version_path, build_info_path).

    Raises if Sha is empty -- never write an empty/garbage version.
    """
    if not Sha:
        raise ValueError("Sha is empty; refusing to stamp")

    TargetRoot.mkdir(parents=True, exist_ok=True)
    VersionPath = TargetRoot / "VERSION"
    BuildInfoPath = TargetRoot / "BUILD_INFO"

    Now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    Host = BuiltBy or socket.gethostname()

    VersionPath.write_text(Sha + "\n", encoding="utf-8")
    BuildInfoPath.write_text(
        f"commit={Sha}\nbuilt_at={Now}\nbuilt_by={Host}\n",
        encoding="utf-8",
    )
    return VersionPath, BuildInfoPath


def Main(Argv: list | None = None) -> int:
    Parser = argparse.ArgumentParser(
        description="Stamp VERSION + BUILD_INFO into a MediaVortex repo root.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    Parser.add_argument(
        "--target", default=str(RepoRoot),
        help=f"Repo root to stamp (default: {RepoRoot}).",
    )
    Parser.add_argument(
        "--source", default=str(RepoRoot),
        help=f"Git repo to read HEAD from (default: {RepoRoot}).",
    )
    Parser.add_argument(
        "--sha", default=None,
        help="Use this literal SHA instead of resolving from --source.",
    )
    Parser.add_argument(
        "--built-by", default=None,
        help="Override the built_by hostname (default: dev workstation hostname).",
    )
    Parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress success-line output.",
    )
    Args = Parser.parse_args(Argv)

    Sha = Args.sha or _ResolveHead(Path(Args.source))
    if not Sha:
        print(f"[FAIL] could not resolve HEAD at {Args.source}; pass --sha explicitly",
              file=sys.stderr)
        return 1

    try:
        VPath, BPath = Stamp(Path(Args.target), Sha, BuiltBy=Args.built_by)
    except ValueError as Ex:
        print(f"[FAIL] {Ex}", file=sys.stderr)
        return 1

    if not Args.quiet:
        print(f"stamped {VPath} ({Sha[:7]})")
        print(f"stamped {BPath}")
    return 0


if __name__ == "__main__":
    sys.exit(Main())
