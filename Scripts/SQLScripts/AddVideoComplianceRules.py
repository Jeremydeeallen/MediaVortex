#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


# directive: video-vertical-and-bpp
def RunMigration():
    Db = DatabaseService()
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    try:
        Cur.execute(
            "CREATE TABLE IF NOT EXISTS VideoComplianceRules ("
            "Id SERIAL PRIMARY KEY, "
            "AcceptableVideoCodecsCsv TEXT NOT NULL, "
            "EstimatedSavingsMBThreshold INTEGER NOT NULL, "
            "PreventUpscale BOOLEAN NOT NULL, "
            "ResolutionExceedsProfileTarget BOOLEAN NOT NULL, "
            "MinSourceBpp DOUBLE PRECISION NOT NULL, "
            "LastUpdated TIMESTAMP DEFAULT NOW()"
            ")"
        )
        Conn.commit()
        Cur.execute("SELECT COUNT(*) FROM VideoComplianceRules")
        if Cur.fetchone()[0] == 0:
            # from: IDEAS.md
            MinBpp = 0.04
            Cur.execute(
                "INSERT INTO VideoComplianceRules (AcceptableVideoCodecsCsv, EstimatedSavingsMBThreshold, PreventUpscale, ResolutionExceedsProfileTarget, MinSourceBpp) "
                "SELECT AcceptableVideoCodecsCsv, EstimatedSavingsMBThreshold, PreventUpscale, ResolutionExceedsProfileTarget, %s "
                "FROM TranscodeRules ORDER BY Id LIMIT 1 "
                "ON CONFLICT DO NOTHING",
                (MinBpp,),
            )
            Conn.commit()
            print("Seeded VideoComplianceRules row 1 (copied from TranscodeRules + MinSourceBpp=0.04)")
        else:
            print("VideoComplianceRules already has rows -- skipping seed")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
