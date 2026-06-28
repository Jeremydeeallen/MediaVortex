from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Core.Querying import PagedQuery, PagedQueryResult
from Features.WorkBucket.Domain.BucketKey import BucketKey
from Features.WorkBucket.Domain.FilterSpec import FilterSpec
from Features.WorkBucket.Domain.Series import Series
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Domain.SortSpec import SortSpec


# directive: work-transcode-unified | # see work-bucket.C1
class SeriesQueryRepository:

    # directive: work-transcode-unified | # see work-bucket.C1
    def __init__(self, Db: DatabaseService = None):
        self.Db = Db or DatabaseService()

    # directive: work-transcode-unified | # see work-bucket.C1, work-bucket.C2, work-bucket.C6
    def ListSeriesByBucket(
        self,
        Bucket: BucketKey,
        Query: PagedQuery,
        Sort: SortSpec,
        Filter: FilterSpec,
    ) -> PagedQueryResult:
        FilterClause, FilterParams = Filter.ToSqlFragments()
        Offset = Query.Offset()
        RequestedLimit = Query.Limit()
        Limit = min(RequestedLimit, 200)
        if RequestedLimit > 200:
            LoggingService.LogWarning(f"PageSize {RequestedLimit} exceeds cap; clamped to 200", "SeriesQueryRepository", "ListSeriesByBucket")
        Sql = (
            "SELECT * FROM ("
            "  SELECT mf.StorageRootId AS StorageRootId,"
            "         split_part(mf.RelativePath, '/', 1) AS RelativePath,"
            "         split_part(mf.RelativePath, '/', 1) AS ShowName,"
            "         COUNT(*)::int AS FileCount,"
            "         ROUND(SUM(mf.SizeMB)::numeric / 1024, 1)::float AS TotalGB,"
            "         MODE() WITHIN GROUP (ORDER BY mf.ResolutionCategory) AS CommonResolution,"
            "         MODE() WITHIN GROUP (ORDER BY mf.Codec) AS CommonCodec,"
            "         sp.AssignedProfile AS AssignedProfile,"
            "         EXISTS ("
            "           SELECT 1 FROM TranscodeQueue tq"
            "             JOIN MediaFiles m2 ON m2.Id = tq.MediaFileId"
            "            WHERE tq.Status = 'Pending'"
            "              AND m2.StorageRootId = mf.StorageRootId"
            "              AND split_part(m2.RelativePath, '/', 1) = split_part(mf.RelativePath, '/', 1)"
            "              AND m2.WorkBucket = mf.WorkBucket"
            "         ) AS AnyInQueue,"
            "         COUNT(*) OVER () AS __TotalCount"
            "    FROM MediaFiles mf"
            "    LEFT JOIN SeriesProfiles sp"
            "      ON sp.StorageRootId = mf.StorageRootId"
            "     AND sp.RelativePath = split_part(mf.RelativePath, '/', 1)"
            "   WHERE mf.WorkBucket = %s "
            f"   {FilterClause} "
            "   GROUP BY mf.StorageRootId, split_part(mf.RelativePath, '/', 1), sp.AssignedProfile"
            "   HAVING COUNT(*) > 0"
            ") agg "
            f"ORDER BY {Sort.ToSql()} "
            "LIMIT %s OFFSET %s"
        )
        Params = (Bucket.BucketName,) + FilterParams + (Limit, Offset)
        Rows = self.Db.ExecuteQuery(Sql, Params)
        TotalCount = int(Rows[0]['__totalcount']) if Rows else 0
        SeriesList = [
            Series(
                Identity=SeriesIdentity(
                    StorageRootId=int(R['storagerootid']),
                    RelativePath=R['relativepath'],
                ),
                Bucket=Bucket,
                ShowName=R['showname'],
                FileCount=int(R['filecount']),
                TotalGB=float(R['totalgb']) if R['totalgb'] is not None else 0.0,
                CommonResolution=R.get('commonresolution'),
                CommonCodec=R.get('commoncodec'),
                AssignedProfile=R.get('assignedprofile'),
                AnyInQueue=bool(R.get('anyinqueue')),
            )
            for R in Rows
        ]
        return PagedQueryResult(
            Rows=SeriesList,
            TotalCount=TotalCount,
            Page=Query.Page,
            PageSize=Query.PageSize,
        )
