import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


SEEDS = [
    ('StuckJobDetectionIntervalSec', '120', 'integer', 'Detection loop cadence in seconds.'),
    ('SetupPhaseTimeoutMin', '30', 'integer', 'SetupPhaseDetector timeout (path resolve + attempt record creation).'),
    ('PreEncodePhaseTimeoutMin', '20', 'integer', 'PreEncodePhaseDetector timeout (Demucs pipeline).'),
    ('FrozenProgressThresholdMin', '5', 'integer', 'EncodingPhaseDetector frame-advance staleness threshold (minutes).'),
    ('PostEncodePhaseTimeoutMin', '15', 'integer', 'PostEncodePhaseDetector timeout.'),
    ('VerifyingPhaseTimeoutMin', '60', 'integer', 'VerifyingPhaseDetector timeout (VMAF / checksum).'),
]


def Main():
    Db = DatabaseService()
    Now = datetime.now(timezone.utc)
    for Key, Value, DataType, Description in SEEDS:
        Db.ExecuteNonQuery(
            "INSERT INTO SystemSettings (SettingKey, SettingValue, DataType, Description, LastModified) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (SettingKey) DO NOTHING",
            (Key, Value, DataType, Description, Now),
        )
        print(f"{Key} = {Value!r} ({DataType}): ensured")
    return 0


if __name__ == '__main__':
    sys.exit(Main())
