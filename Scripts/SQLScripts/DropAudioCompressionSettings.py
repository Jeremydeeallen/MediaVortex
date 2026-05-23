#!/usr/bin/env python3
"""
DropAudioCompressionSettings.py
Removes obsolete acompressor + fixed-LRA SystemSettings rows for
linear-loudnorm.feature.md.

Owns: linear-loudnorm.feature.md criterion 4.

The linear-loudnorm feature deletes the acompressor stage entirely
(range compression is handled by loudnorm's dynamic mode when the
predicted-peak math requires it). The SystemSettings rows that drove
acompressor are dead weight; this migration removes them so the
/settings page stops surfacing them.

Also removes the old fixed-LRA setting 'LoudnessRange' -- replaced
by 'MinimumLoudnessRangeLU' (see AddMinimumLoudnessRangeSetting.py),
which is a floor for the *measured-driven* target_LRA, not a fixed
target. The old name was load-bearing in the previous chain and
keeping it would mislead future operators.

Retained: 'TargetLoudness' (-23), 'TruePeak' (-2),
'AudioNormalizationEnabled' (emergency kill switch).

Idempotent.
"""

import os
import psycopg2


OBSOLETE_KEYS = (
    'CompressionThreshold',
    'CompressionRatio',
    'CompressionAttack',
    'CompressionRelease',
    'CompressionMakeup',
    'AudioCompressionEnabled',
    'LoudnessRange',
)


def GetConnection():
    return psycopg2.connect(
        host=os.environ.get('MEDIAVORTEX_DB_HOST', 'localhost'),
        port=int(os.environ.get('MEDIAVORTEX_DB_PORT', '5432')),
        database=os.environ.get('MEDIAVORTEX_DB_NAME', 'mediavortex'),
        user=os.environ.get('MEDIAVORTEX_DB_USER', 'mediavortex'),
        password=os.environ.get('MEDIAVORTEX_DB_PASSWORD', 'mediavortex'),
    )


def DropSettings():
    Conn = GetConnection()
    Cur = Conn.cursor()
    try:
        for Key in OBSOLETE_KEYS:
            Cur.execute(
                "SELECT SettingValue FROM SystemSettings WHERE SettingKey = %s LIMIT 1",
                (Key,),
            )
            Existing = Cur.fetchone()
            if Existing is None:
                print(f"{Key}: not present -- skipping")
                continue
            Cur.execute("DELETE FROM SystemSettings WHERE SettingKey = %s", (Key,))
            print(f"{Key}: deleted (was {Existing[0]!r})")
        Conn.commit()
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    DropSettings()
