# directive: transcode-worker-unification | # see worker-loop.C3

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: transcode-worker-unification | # see worker-loop.C3
def RunMigration():
    Db = DatabaseService()
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    try:
        Cur.execute(
            "ALTER TABLE PostTranscodeGateConfig "
            "ADD COLUMN IF NOT EXISTS WorkerHeartbeatWindowSec INTEGER NOT NULL DEFAULT 90"
        )
        Cur.execute(
            "ALTER TABLE PostTranscodeGateConfig "
            "ADD COLUMN IF NOT EXISTS RetranscodeVmafThreshold INTEGER NOT NULL DEFAULT 80"
        )
        Cur.execute(
            "ALTER TABLE PostTranscodeGateConfig "
            "ADD COLUMN IF NOT EXISTS FileReplacementCanReplaceThreshold INTEGER NOT NULL DEFAULT 90"
        )

        Conn.commit()

        Cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='posttranscodegateconfig' "
            "ORDER BY ordinal_position"
        )
        Columns = [Row[0] for Row in Cur.fetchall()]
        NewCols = {'workerheartbeatwindowsec', 'retranscodevmafthreshold', 'filereplacementcanreplacethreshold'}
        Present = NewCols.intersection({C.lower() for C in Columns})

        if Present == NewCols:
            print(f"Migration complete -- PostTranscodeGateConfig now has columns: {', '.join(sorted(Columns))}.")
        else:
            Missing = NewCols - Present
            print(f"WARNING: expected columns missing: {Missing}. Inspect manually.")
    except Exception:
        Conn.rollback()
        raise
    finally:
        Cur.close()
        Db.CloseConnection(Conn)


if __name__ == '__main__':
    RunMigration()
