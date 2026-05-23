#!/usr/bin/env python3
"""
AddMinimumLoudnessRangeSetting.py
Seeds SystemSettings('MinimumLoudnessRangeLU', '11') for linear-loudnorm.feature.md.

Owns: linear-loudnorm.feature.md criterion 3.

This is the LRA floor used at command-build time as
    target_LRA = max(SourceLoudnessRangeLU, MinimumLoudnessRangeLU)

The 11 default puts MediaVortex in the same range Netflix / Apple TV+
use for playback normalization. Broadcast TV stays in linear mode
(transparent); cinematic content trips dynamic mode and gets measured
range compression. Operator-tunable from 5 (aggressive night mode) to
18 (full cinematic dynamics) per the feature doc's Runbook.

Idempotent. Existing value (if any) is NOT overwritten -- if the
operator has tuned the floor, this seed leaves it alone.
"""

import os
import psycopg2
from datetime import datetime, timezone


DEFAULT_FLOOR_LU = '11'


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
            "SELECT SettingValue FROM SystemSettings WHERE SettingKey = 'MinimumLoudnessRangeLU' LIMIT 1"
        )
        Existing = Cur.fetchone()
        if Existing:
            print(f"MinimumLoudnessRangeLU already set to {Existing[0]!r} -- skipping seed")
            return

        Now = datetime.now(timezone.utc)
        Cur.execute(
            """
            INSERT INTO SystemSettings (SettingKey, SettingValue, DataType, Description, LastModified)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                'MinimumLoudnessRangeLU',
                DEFAULT_FLOOR_LU,
                'integer',
                (
                    'LRA floor (LU). target_LRA = max(SourceLoudnessRangeLU, floor). '
                    'Higher = more dynamic range preserved (movie-night); '
                    'lower = more range compression (night-mode-friendly). '
                    'See Features/LoudnessAnalysis/linear-loudnorm.feature.md Runbook.'
                ),
                Now,
            ),
        )
        Conn.commit()
        print(f"Seeded MinimumLoudnessRangeLU = {DEFAULT_FLOOR_LU}")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    Seed()
