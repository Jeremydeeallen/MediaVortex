# directive: local-staging-cleanup-restore | # see local-staging.S5
import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Core.Database.DatabaseService import DatabaseService


# directive: local-staging-cleanup-restore
def _NumericSubdirs(RootDir):
    out = []
    for Name in os.listdir(RootDir):
        Full = os.path.join(RootDir, Name)
        if not os.path.isdir(Full):
            continue
        try:
            int(Name)
        except ValueError:
            continue
        out.append((int(Name), Full))
    return out


# directive: local-staging-cleanup-restore
def _HasInflight(Db, WorkerName, MediaFileId):
    Rows = Db.ExecuteQuery(
        "SELECT 1 FROM TranscodeAttempts WHERE MediaFileId = %s AND WorkerName = %s AND Success IS NULL LIMIT 1",
        (MediaFileId, WorkerName),
    )
    return bool(Rows)


# directive: local-staging-cleanup-restore
def Main():
    Parser = argparse.ArgumentParser()
    Parser.add_argument('--worker', required=True, help='WorkerName (e.g. I9-2024)')
    Parser.add_argument('--apply', action='store_true', help='Actually delete; default is dry-run')
    Args = Parser.parse_args()

    Db = DatabaseService()
    Rows = Db.ExecuteQuery("SELECT LocalScratchDir FROM Workers WHERE WorkerName = %s", (Args.worker,))
    if not Rows:
        print(f"Worker {Args.worker!r} not found")
        sys.exit(1)
    ScratchDir = (Rows[0].get('localscratchdir') or '').strip()
    if not ScratchDir:
        print(f"Worker {Args.worker!r} has no LocalScratchDir set; nothing to clean")
        sys.exit(0)
    if not os.path.isdir(ScratchDir):
        print(f"LocalScratchDir {ScratchDir!r} does not exist on this host")
        sys.exit(0)

    print(f"Scanning {ScratchDir} on worker {Args.worker} (apply={Args.apply})")
    Numeric = _NumericSubdirs(ScratchDir)
    print(f"Found {len(Numeric)} numeric subdir(s)")

    Terminal = []
    Inflight = []
    for MediaFileId, Full in Numeric:
        if _HasInflight(Db, Args.worker, MediaFileId):
            Inflight.append((MediaFileId, Full))
        else:
            Terminal.append((MediaFileId, Full))

    TotalBytes = 0
    for MediaFileId, Full in Terminal:
        try:
            for Root, _, Files in os.walk(Full):
                for F in Files:
                    try:
                        TotalBytes += os.path.getsize(os.path.join(Root, F))
                    except OSError:
                        pass
        except OSError:
            pass

    print(f"Terminal (safe to remove): {len(Terminal)} -- {TotalBytes/1024/1024/1024:.2f} GB")
    print(f"In-flight (skip): {len(Inflight)}")

    if not Args.apply:
        print("DRY RUN -- pass --apply to remove")
        for MediaFileId, Full in Terminal[:10]:
            print(f"  would remove: {Full}")
        if len(Terminal) > 10:
            print(f"  ... and {len(Terminal)-10} more")
        return

    Removed = 0
    for MediaFileId, Full in Terminal:
        try:
            shutil.rmtree(Full, ignore_errors=False)
            Removed += 1
        except OSError as Ex:
            print(f"  FAIL {Full}: {Ex}")
    print(f"Removed {Removed}/{len(Terminal)} subdirs; reclaimed ~{TotalBytes/1024/1024/1024:.2f} GB")


if __name__ == '__main__':
    Main()
