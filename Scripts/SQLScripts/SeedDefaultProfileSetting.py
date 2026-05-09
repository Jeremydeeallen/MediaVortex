#!/usr/bin/env python3
"""
SeedDefaultProfileSetting.py
Seed SystemSettings('DefaultProfileName') with the operator's chosen default.

Owns: transcode-vs-remux-routing.feature.md criterion 1.

The seeded value must exist in Profiles.ProfileName. The script verifies
this before INSERTing -- if the named profile doesn't exist, it errors
loudly so the operator can correct the value.

Idempotent. Existing values are NOT overwritten.
"""

import os
import sys
import psycopg2
from datetime import datetime, timezone


DEFAULT_PROFILE_NAME = 'SVT-AV1 P6 FG8 >480p'


def GetConnection():
    return psycopg2.connect(
        host=os.environ.get('MEDIAVORTEX_DB_HOST', 'localhost'),
        port=int(os.environ.get('MEDIAVORTEX_DB_PORT', '5432')),
        database=os.environ.get('MEDIAVORTEX_DB_NAME', 'mediavortex'),
        user=os.environ.get('MEDIAVORTEX_DB_USER', 'mediavortex'),
        password=os.environ.get('MEDIAVORTEX_DB_PASSWORD', 'mediavortex'),
    )


def Seed():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        Cur.execute(
            "SELECT SettingValue FROM SystemSettings WHERE SettingKey = 'DefaultProfileName' LIMIT 1"
        )
        Existing = Cur.fetchone()
        if Existing:
            print(f"DefaultProfileName already set to {Existing[0]!r} -- skipping seed")
            return

        Cur.execute("SELECT 1 FROM Profiles WHERE ProfileName = %s LIMIT 1", (DEFAULT_PROFILE_NAME,))
        if Cur.fetchone() is None:
            print(
                f"ERROR: profile {DEFAULT_PROFILE_NAME!r} does not exist in Profiles table.",
                file=sys.stderr,
            )
            print(
                "Either create the profile first or change DEFAULT_PROFILE_NAME at the top of this script.",
                file=sys.stderr,
            )
            sys.exit(1)

        Now = datetime.now(timezone.utc)
        Cur.execute(
            """
            INSERT INTO SystemSettings (SettingKey, SettingValue, DataType, Description, LastModified)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                'DefaultProfileName',
                DEFAULT_PROFILE_NAME,
                'string',
                'Library-wide default profile name. ShowSettings.AssignedProfile per-show overrides this.',
                Now,
            ),
        )
        Conn.commit()
        print(f"Seeded DefaultProfileName = {DEFAULT_PROFILE_NAME!r}")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    Seed()
