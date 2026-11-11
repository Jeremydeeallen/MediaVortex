from pathlib import Path

from Core.Path.LocalPath import LocalExists, LocalJoin

ProjectRoot = str(Path(__file__).resolve().parent.parent)


# directive: farm-server | # see startup.S5 -- .git/HEAD on a git checkout, VERSION on a deployed tree (git archive ships no .git); worker-lifecycle-invariants.md I3
def ResolveCodeVersion(Root: str = ProjectRoot) -> tuple:
    BuildInfoFile = LocalJoin(Root, "BUILD_INFO")
    BuildInfo = _ReadText(BuildInfoFile) if LocalExists(BuildInfoFile) else None

    HeadFile = LocalJoin(Root, ".git", "HEAD")
    if LocalExists(HeadFile):
        Head = _ReadText(HeadFile).strip()
        if Head.startswith("ref: "):
            RefFile = LocalJoin(Root, ".git", Head[5:])
            if LocalExists(RefFile):
                Sha = _ReadText(RefFile).strip()
                if Sha:
                    return (Sha[:64], BuildInfo)
        elif Head:
            return (Head[:64], BuildInfo)

    VersionFile = LocalJoin(Root, "VERSION")
    if LocalExists(VersionFile):
        Sha = _ReadText(VersionFile).strip()
        if Sha:
            return (Sha[:64], BuildInfo)

    return ("unknown", None)


# directive: farm-server | # see startup.S5
def _ReadText(FilePath: str) -> str:
    with open(FilePath, "r", encoding="utf-8") as Fh:
        return Fh.read()
