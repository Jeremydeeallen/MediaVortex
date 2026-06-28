# directive: work-transcode-unified | # see work-bucket.C3

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Repositories.SeriesProfileRepository import SeriesProfileRepository


# directive: work-transcode-unified | # see work-bucket.C3
def Run(DryRun: bool = False, Limit: int = 0, BatchSize: int = 500) -> int:
    Db = DatabaseService()
    SeriesRepo = SeriesProfileRepository(Db)

    Counted = Db.ExecuteQuery(
        "SELECT COUNT(*) AS Total FROM MediaFiles "
        "WHERE AssignedProfile IS NULL AND AssignedProfileSource IS NULL "
        "AND TranscodedByMediaVortex IS NOT TRUE AND SizeMB > 0",
        (),
    )
    Total = int(Counted[0].get("Total", 0)) if Counted else 0
    print(f"Candidates (NULL AssignedProfile, untranscoded, sized > 0): {Total}")

    if DryRun:
        from Features.ContentClassifier.ContentClassifierService import ContentClassifierService
        Svc = ContentClassifierService()
        from Features.ContentClassifier.ContentClassifierRepository import ContentClassifierRepository
        Repo = ContentClassifierRepository()
        Rules = Repo.GetActiveRules()
        Sample = Db.ExecuteQuery(
            "SELECT Id, StorageRootId, RelativePath FROM MediaFiles "
            "WHERE AssignedProfile IS NULL AND AssignedProfileSource IS NULL "
            "AND TranscodedByMediaVortex IS NOT TRUE AND SizeMB > 0 "
            "ORDER BY Id LIMIT %s",
            (min(Limit or 100, 100),),
        )
        DryHits = {}
        DrySeriesHits = 0
        DrySkipped = 0
        DryUnmatched = 0
        for R in Sample:
            try:
                StorageRootId = R.get("StorageRootId")
                RelPath = R.get("RelativePath") or ""
                if StorageRootId is not None and RelPath:
                    Identity = SeriesIdentity.FromMediaFilePath(int(StorageRootId), RelPath)
                    if SeriesRepo.GetProfile(Identity):
                        DrySeriesHits += 1
                        continue
            except Exception as Ex:
                LoggingService.LogException(
                    f"BackfillProfileAssignments series cascade failed for MediaFile {R.get('Id')} (dry-run)",
                    Ex,
                    "BackfillProfileAssignments",
                    "RunDry",
                )
            Media = Repo.GetMediaFileForClassification(R.get("Id"))
            if not Media or Media.get("AssignedProfile"):
                DrySkipped += 1
                continue
            Matched = Svc._Walk(Rules, Media)
            if not Matched:
                DryUnmatched += 1
            else:
                DryHits[Matched.RuleName] = DryHits.get(Matched.RuleName, 0) + 1
        print(f"\n[DRY RUN sample of {len(Sample)}] would assign:")
        print(f"  series-cascade hits: {DrySeriesHits}")
        for K, V in sorted(DryHits.items()):
            print(f"  {V:>6}  {K}")
        print(f"  skipped: {DrySkipped}, unmatched: {DryUnmatched}")
        return 0

    if Total == 0:
        print("Nothing to do.")
        return 0

    from Features.ContentClassifier.ContentClassifierService import ContentClassifierService
    Svc = ContentClassifierService()

    Processed = 0
    HitCounts = {}
    SeriesHitTotal = 0
    SkippedTotal = 0
    UnmatchedTotal = 0

    while True:
        if Limit > 0 and Processed >= Limit:
            break
        Take = min(BatchSize, Limit - Processed) if Limit > 0 else BatchSize
        Rows = Db.ExecuteQuery(
            "SELECT Id, StorageRootId, RelativePath FROM MediaFiles "
            "WHERE AssignedProfile IS NULL AND AssignedProfileSource IS NULL "
            "AND TranscodedByMediaVortex IS NOT TRUE AND SizeMB > 0 "
            "ORDER BY Id LIMIT %s",
            (Take,),
        )
        if not Rows:
            break

        Residual = []
        for R in Rows:
            try:
                StorageRootId = R.get("StorageRootId")
                RelPath = R.get("RelativePath") or ""
                CascadeProfile = None
                if StorageRootId is not None and RelPath:
                    Identity = SeriesIdentity.FromMediaFilePath(int(StorageRootId), RelPath)
                    CascadeProfile = SeriesRepo.GetProfile(Identity)
                if CascadeProfile:
                    Db.ExecuteNonQuery(
                        "UPDATE MediaFiles "
                        "SET AssignedProfile = %s, AssignedProfileSource = 'series', LastModifiedDate = NOW() "
                        "WHERE Id = %s AND AssignedProfile IS NULL",
                        (CascadeProfile, int(R.get("Id"))),
                    )
                    SeriesHitTotal += 1
                    continue
            except Exception as Ex:
                LoggingService.LogException(
                    f"BackfillProfileAssignments series cascade failed for MediaFile {R.get('Id')}",
                    Ex,
                    "BackfillProfileAssignments",
                    "RunBatch",
                )
            Residual.append(R.get("Id"))

        if Residual:
            Result = Svc.ClassifyAndAssignBatch(Residual)
            for K, V in Result.get("HitCounts", {}).items():
                HitCounts[K] = HitCounts.get(K, 0) + V
            SkippedTotal += Result.get("Skipped", 0)
            UnmatchedTotal += Result.get("Unmatched", 0)

        Processed += len(Rows)
        print(f"  Progress: {Processed}/{Total}", flush=True)
        if len(Rows) < Take:
            break

    print(f"\nDone. processed={Processed}")
    print(f"  series-cascade hits: {SeriesHitTotal}")
    print(f"  per-rule hits:")
    for K, V in sorted(HitCounts.items(), key=lambda T: -T[1]):
        print(f"    {V:>6}  {K}")
    print(f"  skipped (already-assigned): {SkippedTotal}")
    print(f"  unmatched: {UnmatchedTotal}")
    return 0


# directive: work-transcode-unified | # see work-bucket.C3
def main():
    Parser = argparse.ArgumentParser(description="Backfill MediaFiles.AssignedProfile via SeriesProfiles cascade then ContentClassificationRules.")
    Parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    Parser.add_argument("--limit", type=int, default=0, help="Max rows to process (0 = no limit)")
    Parser.add_argument("--batch-size", type=int, default=500, help="Rows per batch")
    Args = Parser.parse_args()
    return Run(DryRun=Args.dry_run, Limit=Args.limit, BatchSize=Args.batch_size)


if __name__ == "__main__":
    sys.exit(main())
