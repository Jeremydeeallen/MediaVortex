#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


# directive: container-vertical
def RunMigration():
    Db = DatabaseService()
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    try:
        Cur.execute(
            "CREATE TABLE IF NOT EXISTS ContainerComplianceRules ("
            "Id SERIAL PRIMARY KEY, "
            "AcceptableContainersCsv TEXT NOT NULL, "
            "AcceptableAudioCodecsCsv TEXT NOT NULL, "
            "LastUpdated TIMESTAMP DEFAULT NOW()"
            ")"
        )
        Conn.commit()
        Cur.execute("SELECT COUNT(*) FROM ContainerComplianceRules")
        if Cur.fetchone()[0] == 0:
            Cur.execute(
                "INSERT INTO ContainerComplianceRules (AcceptableContainersCsv, AcceptableAudioCodecsCsv) "
                "VALUES ('mp4,mov,m4v', 'aac,ac3,eac3,mp3') "
                "ON CONFLICT DO NOTHING"
            )
            Conn.commit()
            print("Seeded ContainerComplianceRules row 1")
        else:
            print("ContainerComplianceRules already has rows -- skipping seed")
    finally:
        Cur.close()
        Conn.close()


if __name__ == '__main__':
    RunMigration()
