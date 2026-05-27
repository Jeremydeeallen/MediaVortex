"""Seed __jellyfin__ rows in StorageRootResolutions.

Owns: jellyfin-push-notify.feature.md criterion 2.

Adds one synthetic worker entry (`__jellyfin__`) per StorageRoot mapping
the canonical Windows-shaped prefix to the path Jellyfin sees on its
own host.

Idempotent. The absolute paths below are best-guess based on the Jellyfin
library names recorded in the feature doc (BrainTv, SynologyMovies,
SynologyXXX). Verify against the Jellyfin host's `ls` before relying on
the live notify path.

The push-notify-specific `JellyfinNotifyDryRun` setting was removed
2026-05-27; the Jellyfin host/port/key rows are managed by
Features/Optimization and are not seeded here.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from Core.Database.DatabaseService import DatabaseService


JELLYFIN_WORKER_NAME = '__jellyfin__'

# (StorageRoots.Name, absolute path on the Jellyfin host)
JELLYFIN_RESOLUTIONS = [
    ('media_tv', '/mnt/BrainTv/'),
    ('movies',   '/mnt/SynologyMovies/'),
    ('xxx',      '/mnt/XXX/'),
]


def Main():
    Db = DatabaseService()

    StorageRoots = Db.ExecuteQuery("SELECT Id, Name FROM StorageRoots")
    NameToId = {Row['Name']: Row['Id'] for Row in StorageRoots}

    Missing = [Name for Name, _ in JELLYFIN_RESOLUTIONS if Name not in NameToId]
    if Missing:
        print(f"ERROR: StorageRoots missing: {Missing}")
        print(f"Known roots: {sorted(NameToId.keys())}")
        sys.exit(1)

    for Name, AbsolutePath in JELLYFIN_RESOLUTIONS:
        StorageRootId = NameToId[Name]
        Existing = Db.ExecuteQuery(
            "SELECT Id, AbsolutePath, IsActive FROM StorageRootResolutions "
            "WHERE StorageRootId = %s AND WorkerName = %s",
            (StorageRootId, JELLYFIN_WORKER_NAME),
        )
        if Existing:
            Row = Existing[0]
            if Row['AbsolutePath'] == AbsolutePath and Row['IsActive']:
                print(f"OK     {Name:10s} -> {AbsolutePath} (already seeded)")
                continue
            Db.ExecuteNonQuery(
                "UPDATE StorageRootResolutions SET AbsolutePath = %s, IsActive = TRUE "
                "WHERE Id = %s",
                (AbsolutePath, Row['Id']),
            )
            print(f"UPDATE {Name:10s} -> {AbsolutePath} (was {Row['AbsolutePath']!r}, active={Row['IsActive']})")
        else:
            Db.ExecuteNonQuery(
                "INSERT INTO StorageRootResolutions "
                "(StorageRootId, WorkerName, Platform, AbsolutePath, IsActive) "
                "VALUES (%s, %s, %s, %s, TRUE)",
                (StorageRootId, JELLYFIN_WORKER_NAME, 'linux', AbsolutePath),
            )
            print(f"INSERT {Name:10s} -> {AbsolutePath}")

    print()
    print("Verify resolutions with:")
    print(f"  py Scripts/SQLScripts/QueryDatabase.py sql "
          f"\"SELECT sr.Name, srr.AbsolutePath FROM StorageRootResolutions srr "
          f"JOIN StorageRoots sr ON sr.Id = srr.StorageRootId "
          f"WHERE srr.WorkerName = '{JELLYFIN_WORKER_NAME}' ORDER BY sr.Name\"")


if __name__ == '__main__':
    Main()
