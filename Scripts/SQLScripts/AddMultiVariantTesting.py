"""Migration: multi-variant test mode for the transcode queue.

Owns: Features/TranscodeJob/multi-variant-testing.feature.md criteria 1, 2, 3, 11.

Three schema changes (additive, idempotent):

1. NEW table TestVariantSets:
   - Id SERIAL PRIMARY KEY
   - Name TEXT UNIQUE NOT NULL
   - Description TEXT NULL
   - VariantsJson JSONB NOT NULL (array of {Name, Label, Crf, FilmGrain, Scale})
   - CreatedAt TIMESTAMP NOT NULL DEFAULT NOW()

2. ALTER TranscodeQueue:
   - ADD TestVariantSetId INT NULL REFERENCES TestVariantSets(Id) ON DELETE SET NULL

3. ALTER TranscodeAttempts:
   - ADD TestVariantSetId INT NULL (no FK -- preserve history across set deletion)
   - ADD TestVariantName TEXT NULL

4. SystemSetting TestModeRetentionDays = 30 (used by CleanTestModeStaging.py)

5. Seed two variant sets:
   - "FG Sweep 1080p CRF32" (4 variants, film-grain=0/4/8/12)
   - "CRF Sweep 1080p FG=4" (4 variants, CRF=25/28/32/35)
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from Core.Database.DatabaseService import DatabaseService


FG_SWEEP_VARIANTS = [
    {"Name": "A", "Label": "FG=0  CRF=32 1080p", "Crf": 32, "FilmGrain": 0,  "Scale": "1920:1080"},
    {"Name": "B", "Label": "FG=4  CRF=32 1080p", "Crf": 32, "FilmGrain": 4,  "Scale": "1920:1080"},
    {"Name": "C", "Label": "FG=8  CRF=32 1080p", "Crf": 32, "FilmGrain": 8,  "Scale": "1920:1080"},
    {"Name": "D", "Label": "FG=12 CRF=32 1080p", "Crf": 32, "FilmGrain": 12, "Scale": "1920:1080"},
]

CRF_SWEEP_VARIANTS = [
    {"Name": "A", "Label": "CRF=25 FG=4 1080p", "Crf": 25, "FilmGrain": 4, "Scale": "1920:1080"},
    {"Name": "B", "Label": "CRF=28 FG=4 1080p", "Crf": 28, "FilmGrain": 4, "Scale": "1920:1080"},
    {"Name": "C", "Label": "CRF=32 FG=4 1080p", "Crf": 32, "FilmGrain": 4, "Scale": "1920:1080"},
    {"Name": "D", "Label": "CRF=35 FG=4 1080p", "Crf": 35, "FilmGrain": 4, "Scale": "1920:1080"},
]

VARIANT_SETS = [
    {"Name": "FG Sweep 1080p CRF32", "Description": "Compare film-grain levels at fixed 1080p CRF32. Use to evaluate the 'plastic vs filmic' look on clean digital sources.", "Variants": FG_SWEEP_VARIANTS},
    {"Name": "CRF Sweep 1080p FG=4", "Description": "Compare CRF levels at fixed 1080p FG=4. Use to find the CRF sweet spot for live-action content.", "Variants": CRF_SWEEP_VARIANTS},
]


def TableExists(Cursor, TableName):
    Cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s AND table_schema = current_schema()",
        (TableName.lower(),),
    )
    return Cursor.fetchone() is not None


def ColumnExists(Cursor, TableName, ColumnName):
    Cursor.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s AND table_schema = current_schema()",
        (TableName.lower(), ColumnName.lower()),
    )
    return Cursor.fetchone() is not None


def Main():
    Db = DatabaseService()
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    try:
        if not TableExists(Cur, 'TestVariantSets'):
            print("  CREATE TestVariantSets")
            Cur.execute("""
                CREATE TABLE TestVariantSets (
                    Id SERIAL PRIMARY KEY,
                    Name TEXT UNIQUE NOT NULL,
                    Description TEXT,
                    VariantsJson JSONB NOT NULL,
                    CreatedAt TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            Conn.commit()
        else:
            print("  EXISTS  TestVariantSets")

        if not ColumnExists(Cur, 'TranscodeQueue', 'TestVariantSetId'):
            print("  ADD     TranscodeQueue.TestVariantSetId")
            Cur.execute("""
                ALTER TABLE TranscodeQueue
                ADD COLUMN TestVariantSetId INT NULL REFERENCES TestVariantSets(Id) ON DELETE SET NULL
            """)
            Conn.commit()
        else:
            print("  EXISTS  TranscodeQueue.TestVariantSetId")

        if not ColumnExists(Cur, 'TranscodeAttempts', 'TestVariantSetId'):
            print("  ADD     TranscodeAttempts.TestVariantSetId")
            Cur.execute("ALTER TABLE TranscodeAttempts ADD COLUMN TestVariantSetId INT NULL")
            Conn.commit()
        else:
            print("  EXISTS  TranscodeAttempts.TestVariantSetId")

        if not ColumnExists(Cur, 'TranscodeAttempts', 'TestVariantName'):
            print("  ADD     TranscodeAttempts.TestVariantName")
            Cur.execute("ALTER TABLE TranscodeAttempts ADD COLUMN TestVariantName TEXT NULL")
            Conn.commit()
        else:
            print("  EXISTS  TranscodeAttempts.TestVariantName")

        Cur.execute("SELECT 1 FROM SystemSettings WHERE SettingKey = 'TestModeRetentionDays' LIMIT 1")
        if not Cur.fetchone():
            print("  ADD     SystemSettings.TestModeRetentionDays = 30")
            Cur.execute("""
                INSERT INTO SystemSettings (SettingKey, SettingValue, Description, DataType, LastModified)
                VALUES ('TestModeRetentionDays', '30',
                        'Days to retain test-mode encoded output files before CleanTestModeStaging.py deletes them. DB rows are preserved indefinitely; only on-disk staged outputs are removed.',
                        'integer', NOW())
            """)
            Conn.commit()
        else:
            print("  EXISTS  SystemSettings.TestModeRetentionDays")

        for VS in VARIANT_SETS:
            Cur.execute("SELECT Id FROM TestVariantSets WHERE Name = %s", (VS['Name'],))
            Row = Cur.fetchone()
            if Row:
                print(f"  EXISTS  TestVariantSets[{VS['Name']!r}] Id={Row[0]}")
            else:
                Cur.execute(
                    "INSERT INTO TestVariantSets (Name, Description, VariantsJson) VALUES (%s, %s, %s) RETURNING Id",
                    (VS['Name'], VS['Description'], json.dumps(VS['Variants'])),
                )
                NewId = Cur.fetchone()[0]
                print(f"  SEED    TestVariantSets[{VS['Name']!r}] Id={NewId} ({len(VS['Variants'])} variants)")
                Conn.commit()

        print("\nDone.\n")
        print("Current TestVariantSets:")
        Cur.execute("SELECT Id, Name, jsonb_array_length(VariantsJson) AS N FROM TestVariantSets ORDER BY Id")
        for Row in Cur.fetchall():
            print(f"  Id={Row[0]:>3}  N={Row[1]}  {Row[2]}")
    finally:
        Cur.close()
        Db.CloseConnection(Conn)


if __name__ == "__main__":
    Main()
