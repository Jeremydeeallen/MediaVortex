"""Migration: VMAF still-capture policy SystemSettings rows.

Owns: Features/QualityTesting/vmaf-comparison-slider.feature.md criteria 11-15.

Idempotent. Three SystemSettings rows that drive auto-capture of comparison
stills on VMAF-test completion:

    VmafStillCapturePolicy        ('All' | 'UncharacterizedProfiles' | 'Off')
    VmafStillCaptureTimestamps    ('60,300,600,900')   seconds, comma-separated
    VmafStillCaptureMinSamples    ('10')               used by UncharacterizedProfiles

Default on first install: VmafStillCapturePolicy=All (capture for every test).
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from Core.Database.DatabaseService import DatabaseService


DEFAULTS = [
    {
        'Key': 'VmafStillCapturePolicy',
        'Value': 'All',
        'Description': (
            "Controls whether comparison stills are auto-generated when a VMAF "
            "test completes. Values: All (every test), UncharacterizedProfiles "
            "(only when the profile+resolution combo has < VmafStillCaptureMinSamples "
            "prior completed VMAF tests), Off (no auto-capture; lazy on-demand only)."
        ),
        'DataType': 'string',
    },
    {
        'Key': 'VmafStillCaptureTimestamps',
        'Value': '60,300,600,900',
        'Description': (
            "Comma-separated list of timestamps (seconds) at which auto-capture "
            "extracts comparison stills. Timestamps past file duration are skipped."
        ),
        'DataType': 'string',
    },
    {
        'Key': 'VmafStillCaptureMinSamples',
        'Value': '10',
        'Description': (
            "When VmafStillCapturePolicy=UncharacterizedProfiles, this is the "
            "minimum prior-completed-VMAF-test count per (ProfileName, source "
            "ResolutionCategory) below which auto-capture fires."
        ),
        'DataType': 'integer',
    },
]


def Main():
    Db = DatabaseService()
    Inserted = 0
    Existing = 0
    for Row in DEFAULTS:
        Found = Db.ExecuteQuery(
            "SELECT 1 FROM SystemSettings WHERE SettingKey = %s LIMIT 1",
            (Row['Key'],),
        )
        if Found:
            Existing += 1
            print(f"  EXISTS  {Row['Key']}")
            continue
        Db.ExecuteNonQuery(
            """
            INSERT INTO SystemSettings (SettingKey, SettingValue, Description, DataType, LastModified)
            VALUES (%s, %s, %s, %s, NOW())
            """,
            (Row['Key'], Row['Value'], Row['Description'], Row['DataType']),
        )
        Inserted += 1
        print(f"  ADDED   {Row['Key']} = {Row['Value']}")

    print(f"\nDone. Inserted {Inserted}, already existed {Existing}.")

    print("\nCurrent values:")
    for Row in Db.ExecuteQuery(
        "SELECT SettingKey, SettingValue, DataType FROM SystemSettings WHERE SettingKey LIKE 'VmafStillCapture%%' ORDER BY SettingKey"
    ):
        print(f"  {Row['SettingKey']:30}  ({Row['DataType']}) = {Row['SettingValue']}")


if __name__ == "__main__":
    Main()
