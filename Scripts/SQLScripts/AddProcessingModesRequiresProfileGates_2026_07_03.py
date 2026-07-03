# directive: transcode-flow-canonical | # see transcode.ST2

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: transcode-flow-canonical | # see transcode.ST2
def RunMigration():
    Db = DatabaseService()
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    try:
        Cur.execute(
            "ALTER TABLE ProcessingModes "
            "ADD COLUMN IF NOT EXISTS RequiresProfileGates BOOLEAN NOT NULL DEFAULT FALSE"
        )
        Cur.execute(
            "UPDATE ProcessingModes SET RequiresProfileGates = TRUE "
            "WHERE Name = 'Transcode' AND RequiresProfileGates IS DISTINCT FROM TRUE"
        )
        UpdatedCount = Cur.rowcount
        Conn.commit()

        Cur.execute("SELECT Name, RequiresProfileGates FROM ProcessingModes ORDER BY Name")
        Rows = Cur.fetchall()
        Summary = ", ".join(f"{R[0]}={R[1]}" for R in Rows)
        print(f"Migration complete -- {UpdatedCount} row(s) backfilled; {Summary}")
    except Exception:
        Conn.rollback()
        raise
    finally:
        Cur.close()
        Db.CloseConnection(Conn)


if __name__ == '__main__':
    RunMigration()
