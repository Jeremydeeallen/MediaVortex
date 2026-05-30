"""Backfill ContentSignals for already-probed MediaFiles rows where the
signal columns are NULL.

See Features/ContentSignals/content-signals.feature.md criteria 11-13.

Idempotent. NULL-signal rows only. Pass --dry-run to preview.

Usage:
    py Scripts/SQLScripts/BackfillContentSignals.py --dry-run --limit 10
    py Scripts/SQLScripts/BackfillContentSignals.py --batch-size 50
"""

import argparse
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


def _ResolveLocalPath(Row, WorkerName: str) -> str:
    try:
        from Core.PathStorage import Resolve as PathResolve
        Srid = Row.get("StorageRootId")
        Rel = Row.get("RelativePath")
        if Srid is not None and Rel:
            return PathResolve(Srid, Rel, WorkerName)
    except Exception:
        pass
    return Row.get("FilePath") or ""


def Run(DryRun: bool = False, Limit: int = 0, BatchSize: int = 100) -> int:
    Db = DatabaseService()
    WorkerName = socket.gethostname()

    BaseQuery = (
        "SELECT Id, FilePath, StorageRootId, RelativePath "
        "FROM MediaFiles "
        "WHERE MotionFraction IS NULL "
        "  AND TranscodedByMediaVortex IS NOT TRUE "
        "  AND SizeMB > 0 "
        "ORDER BY Id "
    )

    Counted = Db.ExecuteQuery(
        "SELECT COUNT(*) AS Total FROM MediaFiles "
        "WHERE MotionFraction IS NULL AND TranscodedByMediaVortex IS NOT TRUE AND SizeMB > 0",
        (),
    )
    Total = int(Counted[0].get("Total", 0)) if Counted else 0
    print(f"Candidates with NULL signals: {Total}")
    if DryRun:
        Sample = Db.ExecuteQuery(BaseQuery + "LIMIT 5", ())
        print("Sample (first 5):")
        for R in Sample:
            print(f"  Id={R.get('Id')}  {R.get('FilePath')}")
        print(f"\n[DRY RUN] Would process up to {Limit or Total} rows in batches of {BatchSize}.")
        return 0

    if Total == 0:
        print("Nothing to do.")
        return 0

    from Features.ContentSignals.ContentSignalsService import ContentSignalsService
    from Features.ContentSignals.ContentSignalsRepository import ContentSignalsRepository
    Repo = ContentSignalsRepository()

    Processed = 0
    Succeeded = 0
    Failed = 0
    while True:
        if Limit > 0 and Processed >= Limit:
            break
        Take = min(BatchSize, Limit - Processed) if Limit > 0 else BatchSize
        Rows = Db.ExecuteQuery(BaseQuery + "LIMIT %s", (Take,))
        if not Rows:
            break
        for R in Rows:
            MfId = R.get("Id")
            LocalPath = _ResolveLocalPath(R, WorkerName)
            Signals = ContentSignalsService.ComputeSignals(LocalPath)
            if Signals is None:
                Failed += 1
            else:
                if Repo.WriteSignals(MfId, Signals):
                    Succeeded += 1
                else:
                    Failed += 1
            Processed += 1
            if Processed % 10 == 0:
                print(f"  Progress: {Processed}/{Total} (ok={Succeeded} fail={Failed})", flush=True)
        if not Rows or len(Rows) < Take:
            break

    print(f"Done. processed={Processed}, succeeded={Succeeded}, failed={Failed}")
    return 0


def main():
    Parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    Parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    Parser.add_argument("--limit", type=int, default=0, help="Max rows to process (0 = no limit)")
    Parser.add_argument("--batch-size", type=int, default=100, help="Rows per query batch")
    Args = Parser.parse_args()
    return Run(DryRun=Args.dry_run, Limit=Args.limit, BatchSize=Args.batch_size)


if __name__ == "__main__":
    sys.exit(main())
