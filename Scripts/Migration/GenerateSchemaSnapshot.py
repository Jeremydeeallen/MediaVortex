# directive: transcode-flow-canonical
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.SchemaChecker import SchemaChecker


# directive: transcode-flow-canonical
def Main():
    Checker = SchemaChecker()
    Snapshot = Checker.QueryLive()
    Checker.WriteSnapshot(Snapshot)
    TableCount = len(Snapshot)
    ColumnCount = sum(len(Cols) for Cols in Snapshot.values())
    print(f"Wrote {Checker.SnapshotPath} -- {TableCount} tables, {ColumnCount} columns.")


if __name__ == '__main__':
    Main()
