import io
import sys
import gzip
from datetime import datetime
from pathlib import Path as PyPath

sys.path.insert(0, str(PyPath(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


# directive: path-schema-migration | # see path.S8
TARGETS = ["MediaFiles", "MediaFilesArchive", "TranscodeQueue", "TranscodeAttempts", "TemporaryFilePaths", "ShowSettings"]


# directive: path-schema-migration | # see path.S8
def _GetColumns(Cur, Table: str):
    """Ordered column list for the table."""
    Cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE LOWER(table_name) = LOWER(%s) ORDER BY ordinal_position",
        (Table,),
    )
    return [R[0] if not isinstance(R, dict) else R["column_name"] for R in Cur.fetchall()]


# directive: path-schema-migration | # see path.S8
def _CountRows(Cur, Table: str) -> int:
    """Row count for the table."""
    Cur.execute(f"SELECT COUNT(*) FROM {Table}")
    Row = Cur.fetchone()
    if isinstance(Row, dict):
        return int(list(Row.values())[0])
    return int(Row[0])


# directive: path-schema-migration | # see path.S8
def Run(OutputPath: str) -> int:
    """Logical backup of the 6 affected tables; COPY TO STDOUT plain-CSV, gzip-compressed."""
    Db = DatabaseService()
    Conn = Db.GetConnection()
    try:
        Cur = Conn.cursor()
        TotalRows = 0
        with gzip.open(OutputPath, "wt", encoding="utf-8", newline="") as Out:
            Out.write("-- MediaVortex path_schema backup\n")
            Out.write(f"-- Generated: {datetime.now().isoformat()}\n")
            Out.write(f"-- Tables: {', '.join(TARGETS)}\n")
            Out.write("-- Restore: zcat <file> | psql -h 10.0.0.15 -U mediavortex -d mediavortex\n\n")
            for Table in TARGETS:
                Cols = _GetColumns(Cur, Table)
                RowCount = _CountRows(Cur, Table)
                ColList = ", ".join(Cols)
                Out.write(f"-- ====== {Table} ({RowCount:,} rows, {len(Cols)} cols) ======\n")
                Out.write(f"COPY {Table} ({ColList}) FROM STDIN WITH (FORMAT csv, HEADER true);\n")
                Buf = io.StringIO()
                Cur.copy_expert(
                    f"COPY {Table} ({ColList}) TO STDOUT WITH (FORMAT csv, HEADER true)",
                    Buf,
                )
                Out.write(Buf.getvalue())
                Out.write("\\.\n\n")
                TotalRows += RowCount
                print(f"  {Table:<22}: {RowCount:>10,} rows, {len(Cols)} cols dumped")
        print(f"\nBackup written: {OutputPath}")
        print(f"Total rows backed up: {TotalRows:,}")
        return 0
    finally:
        Db.CloseConnection(Conn)


if __name__ == "__main__":
    Stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OutputPath = sys.argv[1] if len(sys.argv) > 1 else f"path_schema_pre_{Stamp}.sql.gz"
    sys.exit(Run(OutputPath))
