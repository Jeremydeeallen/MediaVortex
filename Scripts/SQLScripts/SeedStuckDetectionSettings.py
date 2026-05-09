#!/usr/bin/env python3
"""
SeedStuckDetectionSettings.py
Seed SystemSettings rows used by the stuck-job-detection feature.

Owns: stuck-job-detection.feature.md criteria 1 (recurring interval) and
criterion 4 (frozen-progress threshold).

Idempotent. Existing values are NOT overwritten.

Settings seeded:
  StuckJobDetectionIntervalSec   integer  default 120
  FrozenProgressThresholdMin     integer  default 5
"""

import os
import psycopg2
from datetime import datetime, timezone


def GetConnection():
    return psycopg2.connect(
        host=os.environ.get('MEDIAVORTEX_DB_HOST', 'localhost'),
        port=int(os.environ.get('MEDIAVORTEX_DB_PORT', '5432')),
        database=os.environ.get('MEDIAVORTEX_DB_NAME', 'mediavortex'),
        user=os.environ.get('MEDIAVORTEX_DB_USER', 'mediavortex'),
        password=os.environ.get('MEDIAVORTEX_DB_PASSWORD', 'mediavortex'),
    )


SEEDS = [
    ('StuckJobDetectionIntervalSec', '120', 'integer', 'Recurring stuck-job detection cadence in seconds. Default 120.'),
    ('FrozenProgressThresholdMin', '5', 'integer', 'Frame-stagnation threshold in minutes. Default 5.'),
]


def Seed():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        Now = datetime.now(timezone.utc)
        for Key, Value, DataType, Description in SEEDS:
            Cur.execute(
                "SELECT SettingKey FROM SystemSettings WHERE SettingKey = %s LIMIT 1",
                (Key,),
            )
            if Cur.fetchone():
                print(f"{Key}: already present -- skipping")
                continue
            Cur.execute(
                """
                INSERT INTO SystemSettings (SettingKey, SettingValue, DataType, Description, LastModified)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (Key, Value, DataType, Description, Now),
            )
            print(f"{Key} = {Value!r} ({DataType}): inserted")
        Conn.commit()
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    Seed()
