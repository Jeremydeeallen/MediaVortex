import argparse
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService
from Features.Compliance.Services.ComplianceRecomputeService import ComplianceRecomputeService


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C25
def Run():
    Parser = argparse.ArgumentParser(description="Backfill MediaFiles.WorkBucket via ComplianceEvaluator")
    Parser.add_argument('--dry-run', action='store_true', help='Evaluate but do not write to MediaFiles')
    Parser.add_argument('--limit', type=int, default=None, help='Maximum total rows to process')
    Parser.add_argument('--batch-size', type=int, default=500, help='Rows per batch (default 500)')
    Args = Parser.parse_args()

    DB = DatabaseService()
    Service = ComplianceRecomputeService(DB)

    Rows = DB.ExecuteQuery("SELECT COUNT(*) AS N FROM MediaFiles WHERE ComplianceEvaluatedAt IS NULL")
    Remaining = int(Rows[0]['n'])
    print(f"MediaFiles with ComplianceEvaluatedAt IS NULL: {Remaining}")
    if Args.limit is not None:
        Remaining = min(Remaining, Args.limit)
        print(f"--limit {Args.limit} -> processing at most {Remaining} rows")
    if Args.dry_run:
        print("--dry-run: no DB writes")

    Processed = 0
    Totals = {'Bucketed': {}, 'GateBlocked': {}, 'Evaluated': 0}
    while Processed < Remaining:
        Take = min(Args.batch_size, Remaining - Processed)
        IdRows = DB.ExecuteQuery("SELECT Id FROM MediaFiles WHERE ComplianceEvaluatedAt IS NULL ORDER BY Id LIMIT %s", (Take,))
        if not IdRows:
            break
        Ids = [int(R['Id']) for R in IdRows]
        Result = Service.Recompute(Ids, DryRun=Args.dry_run)
        Totals['Evaluated'] += Result['Evaluated']
        for K, V in Result['Bucketed'].items():
            Totals['Bucketed'][K] = Totals['Bucketed'].get(K, 0) + V
        for K, V in Result['GateBlocked'].items():
            Totals['GateBlocked'][K] = Totals['GateBlocked'].get(K, 0) + V
        Processed += Result['Evaluated']
        print(f"  batch: evaluated {Result['Evaluated']} (total {Processed}/{Remaining}); buckets={Result['Bucketed']}; gates={Result['GateBlocked']}")
        if Args.dry_run:
            break

    print("")
    print(f"Done. Evaluated={Totals['Evaluated']}; Bucketed={Totals['Bucketed']}; GateBlocked={Totals['GateBlocked']}")

    AfterRows = DB.ExecuteQuery("SELECT COUNT(*) AS N FROM MediaFiles WHERE ComplianceEvaluatedAt IS NULL")
    print(f"Remaining MediaFiles with ComplianceEvaluatedAt IS NULL: {AfterRows[0]['n']}")


if __name__ == '__main__':
    Run()
