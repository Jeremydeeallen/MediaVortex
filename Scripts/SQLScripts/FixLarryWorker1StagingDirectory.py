"""Phase-1 pragmatic fix for the cross-worker staging-path drift.

larry-worker-1 was provisioned with `StagingDirectory='/staging/larry-worker-1'`
(container-local). Workers 2/3/4 use `/mnt/media_tv/MediaVortex/Staging`
(shared NFS, visible to all containers).

Until Phase 2 retires the column entirely, this script aligns worker-1
with the others so a VMAF claim from another worker can read worker-1's
staged output. Idempotent.

Usage:
    py Scripts/SQLScripts/FixLarryWorker1StagingDirectory.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from Core.Database.DatabaseService import DatabaseService


SHARED_STAGING = "/mnt/media_tv/MediaVortex/Staging"


def Main():
    Db = DatabaseService()

    Rows = Db.ExecuteQuery(
        "SELECT WorkerName, StagingDirectory FROM Workers WHERE WorkerName = %s",
        ("larry-worker-1",),
    )
    if not Rows:
        print("larry-worker-1 not registered. Nothing to fix.")
        return

    Current = Rows[0]['StagingDirectory']
    print(f"Current larry-worker-1.StagingDirectory = {Current!r}")

    if Current == SHARED_STAGING:
        print("Already correct. No change.")
        return

    Db.ExecuteNonQuery(
        "UPDATE Workers SET StagingDirectory = %s WHERE WorkerName = %s",
        (SHARED_STAGING, "larry-worker-1"),
    )
    print(f"Updated to {SHARED_STAGING}.")
    print("Recreate the larry-worker-1 container so the new value is read at boot:")
    print("  ssh root@10.0.0.42 'cd /opt/mediavortex && docker compose up -d --force-recreate larry-worker-1'")


if __name__ == "__main__":
    Main()
