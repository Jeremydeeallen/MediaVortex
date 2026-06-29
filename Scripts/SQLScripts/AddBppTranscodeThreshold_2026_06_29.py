# directive: transcode-worker-unification

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


def ColumnExists(Cur, TableName, ColumnName):
    Cur.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=%s AND column_name=%s",
        (TableName.lower(), ColumnName.lower()),
    )
    return Cur.fetchone() is not None


def RunMigration():
    Db = DatabaseService()
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    try:
        HasNew = ColumnExists(Cur, 'videocompliancerules', 'bpptranscodethreshold')
        HasMin = ColumnExists(Cur, 'videocompliancerules', 'minsourcebpp')
        HasMax = ColumnExists(Cur, 'videocompliancerules', 'maxsourcebpp')

        if not HasNew:
            Cur.execute("ALTER TABLE VideoComplianceRules ADD COLUMN BppTranscodeThreshold DOUBLE PRECISION")
            print("Added BppTranscodeThreshold column.")

        if HasMax:
            Cur.execute("UPDATE VideoComplianceRules SET BppTranscodeThreshold = COALESCE(BppTranscodeThreshold, MaxSourceBpp)")
        Cur.execute("UPDATE VideoComplianceRules SET BppTranscodeThreshold = COALESCE(BppTranscodeThreshold, 0.05)")
        Cur.execute("ALTER TABLE VideoComplianceRules ALTER COLUMN BppTranscodeThreshold SET NOT NULL")
        Cur.execute("ALTER TABLE VideoComplianceRules ALTER COLUMN BppTranscodeThreshold SET DEFAULT 0.05")

        if HasMin:
            Cur.execute("ALTER TABLE VideoComplianceRules RENAME COLUMN MinSourceBpp TO MinSourceBpp_DEPRECATED_2026_06_29")
            print("Renamed MinSourceBpp -> MinSourceBpp_DEPRECATED_2026_06_29.")
        if HasMax:
            Cur.execute("ALTER TABLE VideoComplianceRules RENAME COLUMN MaxSourceBpp TO MaxSourceBpp_DEPRECATED_2026_06_29")
            print("Renamed MaxSourceBpp -> MaxSourceBpp_DEPRECATED_2026_06_29.")

        Conn.commit()

        Cur.execute("SELECT BppTranscodeThreshold FROM VideoComplianceRules ORDER BY Id LIMIT 1")
        Row = Cur.fetchone()
        print(f"Migration complete. BppTranscodeThreshold = {Row[0] if Row else 'NULL'}")
    except Exception:
        Conn.rollback()
        raise
    finally:
        Cur.close()
        Db.CloseConnection(Conn)


if __name__ == '__main__':
    RunMigration()
