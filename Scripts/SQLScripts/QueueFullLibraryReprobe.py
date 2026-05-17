#!/usr/bin/env python3
"""
QueueFullLibraryReprobe.py
One-time helper for media-tabs-and-loudness.feature.md criterion 13.

Flags every MediaFiles row for reprobe by setting NeedsReprobe=TRUE. The
existing MediaProbe batch loop then picks them up in priority order on the
next pass (or workers that poll for unmeasured probe rows).

Idempotent: rows already flagged stay flagged; rows that have already been
reprobed since the previous run are not re-flagged unless this script is
re-run after some have cleared.

Filters (optional):
  --drive T:       Restrict to a drive letter
  --show-folder    Restrict to a show subpath
  --dry-run        Report the count that would be flagged without writing

Examples:
    python QueueFullLibraryReprobe.py                    # whole library
    python QueueFullLibraryReprobe.py --drive T:         # all of T:\\
    python QueueFullLibraryReprobe.py --show-folder Westworld
    python QueueFullLibraryReprobe.py --dry-run
"""

import argparse
import os
import psycopg2


def GetConnection():
    return psycopg2.connect(
        host=os.environ.get('MEDIAVORTEX_DB_HOST', 'localhost'),
        port=int(os.environ.get('MEDIAVORTEX_DB_PORT', '5432')),
        database=os.environ.get('MEDIAVORTEX_DB_NAME', 'mediavortex'),
        user=os.environ.get('MEDIAVORTEX_DB_USER', 'mediavortex'),
        password=os.environ.get('MEDIAVORTEX_DB_PASSWORD', 'mediavortex'),
    )


def EscapeLike(Value: str) -> str:
    return Value.replace('!', '!!').replace('%', '!%').replace('_', '!_')


def Run(Drive: str, ShowFolder: str, DryRun: bool):
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        Clauses = ['NeedsReprobe = FALSE']
        Params = []
        if Drive:
            Clauses.append("FilePath LIKE %s ESCAPE '!'")
            Params.append(f"{EscapeLike(Drive)}%")
        if ShowFolder:
            Clauses.append("FilePath LIKE %s ESCAPE '!'")
            Params.append(f"%{EscapeLike(ShowFolder)}%")
        Where = ' AND '.join(Clauses)

        Cur.execute(f"SELECT COUNT(*) FROM MediaFiles WHERE {Where}", tuple(Params))
        Eligible = Cur.fetchone()[0]
        print(f"Eligible rows (NeedsReprobe=FALSE, matching filters): {Eligible}")

        if DryRun:
            print("DRY RUN -- no changes.")
            return

        Cur.execute(
            f"UPDATE MediaFiles SET NeedsReprobe = TRUE WHERE {Where}",
            tuple(Params),
        )
        Flagged = Cur.rowcount
        Conn.commit()
        print(f"Flagged {Flagged} rows for reprobe.")
        print()
        print("Next step: the MediaProbe batch loop on any worker with ScanEnabled / "
              "ProbeEnabled will pick these up on its next pass. Each reprobe also "
              "re-measures loudness via the MediaProbe loudness integration.")
    finally:
        Cur.close()
        Conn.close()


def Main():
    Parser = argparse.ArgumentParser(description='One-time full-library reprobe')
    Parser.add_argument('--drive', default='', help="e.g. 'T:'")
    Parser.add_argument('--show-folder', default='', help='Subpath match (e.g. Westworld)')
    Parser.add_argument('--dry-run', action='store_true')
    Args = Parser.parse_args()
    Run(Args.drive, Args.show_folder, Args.dry_run)


if __name__ == '__main__':
    Main()
