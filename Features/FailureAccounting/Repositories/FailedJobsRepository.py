from typing import List, Optional
from Core.Database.BaseRepository import BaseRepository
from Core.Database.DatabaseService import DatabaseService
from Core.Database.DatabaseService import EscapeLikePattern
from Core.Logging.LoggingService import LoggingService
from Features.FailureAccounting.Models.FailedJobRow import FailedJobRow


# directive: table-renderer-service | # see shared-table-renderer.S9
class _FailedJobsSearchFilter:
    """IQueryFilter that ILIKEs FileName + RelativePath in the outer SELECT."""

    # directive: table-renderer-service | # see shared-table-renderer.S9
    def __init__(self, EscapedPattern):
        self.Pattern = "%" + EscapedPattern + "%"

    # directive: table-renderer-service | # see shared-table-renderer.S9
    def ToClause(self):
        return "(LOWER(mf.FileName) LIKE LOWER(%s) ESCAPE '!' OR LOWER(COALESCE(mf.RelativePath,'')) LIKE LOWER(%s) ESCAPE '!')"

    # directive: table-renderer-service | # see shared-table-renderer.S9
    def Params(self):
        return (self.Pattern, self.Pattern)


# directive: failure-accounting | # see failure-accounting.C7
class FailedJobsRepository(BaseRepository):
    """SOT for the /FailedJobs surface. Reads capped jobs + writes the operator-Reset audit row."""

    # directive: failure-accounting | # see failure-accounting.C7
    def GetCappedJobs(self, Limit: int = 100, Offset: int = 0, Search: Optional[str] = None, SortBy: str = 'LastAttemptDate', SortDir: str = 'DESC') -> List[FailedJobRow]:
        """Return MediaFiles whose consecutive Success=FALSE failure count meets or exceeds FailureBudgetConfig.MaxEncodeFailures."""
        SafeSortCols = {
            'LastAttemptDate': 'last_attempt',
            'FailureCount': 'fail_count',
            'FileName': 'mf.FileName',
            'AssignedProfile': 'mf.AssignedProfile',
            'SizeMB': 'mf.SizeMB',
        }
        SortCol = SafeSortCols.get(SortBy, 'last_attempt')
        SortOrder = 'ASC' if str(SortDir).upper() == 'ASC' else 'DESC'

        Params: list = []
        SearchClause = ""
        if Search:
            EscapedSearch = EscapeLikePattern(Search)
            SearchClause = " AND (LOWER(mf.FileName) LIKE LOWER(%s) ESCAPE '!' OR LOWER(COALESCE(mf.RelativePath,'')) LIKE LOWER(%s) ESCAPE '!')"
            Params.extend(['%' + EscapedSearch + '%', '%' + EscapedSearch + '%'])

        Query = (
            "WITH ranked AS ("
            "  SELECT ta.MediaFileId, "
            "         COUNT(*) AS fail_count, "
            "         MAX(ta.AttemptDate) AS last_attempt, "
            "         (ARRAY_AGG(ta.ErrorMessage ORDER BY ta.AttemptDate DESC))[1] AS last_error, "
            "         (ARRAY_AGG(ta.WorkerName ORDER BY ta.AttemptDate DESC))[1] AS last_worker "
            "    FROM TranscodeAttempts ta "
            "    JOIN MediaFiles mf ON mf.Id = ta.MediaFileId "
            "   WHERE ta.Success = FALSE "
            "     AND ta.AttemptDate > GREATEST("
            "       COALESCE((SELECT MAX(AttemptDate) FROM TranscodeAttempts WHERE MediaFileId = ta.MediaFileId AND Success = TRUE), 'epoch'::timestamp), "
            "       COALESCE(mf.LastFailureResetAt, 'epoch'::timestamp)"
            "     ) "
            "   GROUP BY ta.MediaFileId"
            ") "
            "SELECT mf.Id AS MediaFileId, mf.FileName, COALESCE(mf.RelativePath, '') AS FilePath, "
            "       r.fail_count, r.last_error, r.last_attempt, mf.AssignedProfile, r.last_worker, "
            "       mf.SizeMB, mf.LastFailureResetAt "
            "  FROM ranked r "
            "  JOIN MediaFiles mf ON mf.Id = r.MediaFileId "
            " WHERE r.fail_count >= COALESCE((SELECT MaxEncodeFailures FROM FailureBudgetConfig WHERE Id = 1), 3) "
            + SearchClause +
            " ORDER BY " + SortCol + " " + SortOrder + ", mf.Id DESC "
            " LIMIT %s OFFSET %s"
        )
        Params.extend([int(Limit), int(Offset)])
        Rows = self.ExecuteQuery(Query, tuple(Params))
        return [
            FailedJobRow(
                MediaFileId=int(R['MediaFileId']),
                FileName=R.get('FileName') or '',
                FilePath=R.get('FilePath') or '',
                FailureCount=int(R.get('fail_count') or 0),
                LastErrorMessage=R.get('last_error'),
                LastAttemptDate=R.get('last_attempt'),
                AssignedProfile=R.get('AssignedProfile'),
                LastWorkerName=R.get('last_worker'),
                SizeMB=float(R['SizeMB']) if R.get('SizeMB') is not None else None,
                LastFailureResetAt=R.get('LastFailureResetAt'),
            )
            for R in Rows
        ]

    # directive: failure-accounting | # see failure-accounting.C7
    def CountCapped(self) -> int:
        """Count distinct MediaFiles at or over the cap. Used by the nav-badge."""
        Rows = self.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM ("
            "  SELECT ta.MediaFileId "
            "    FROM TranscodeAttempts ta "
            "    JOIN MediaFiles mf ON mf.Id = ta.MediaFileId "
            "   WHERE ta.Success = FALSE "
            "     AND ta.AttemptDate > GREATEST("
            "       COALESCE((SELECT MAX(AttemptDate) FROM TranscodeAttempts WHERE MediaFileId = ta.MediaFileId AND Success = TRUE), 'epoch'::timestamp), "
            "       COALESCE(mf.LastFailureResetAt, 'epoch'::timestamp)"
            "     ) "
            "   GROUP BY ta.MediaFileId "
            "  HAVING COUNT(*) >= COALESCE((SELECT MaxEncodeFailures FROM FailureBudgetConfig WHERE Id = 1), 3)"
            ") capped"
        )
        return int(Rows[0]['n']) if Rows else 0

    # directive: failure-accounting | # see failure-accounting.C7
    def ResetFailureBudget(self, MediaFileId: int, OperatorName: str) -> None:
        """Write FailureBudgetResets audit row + bump MediaFiles.LastFailureResetAt. Two writes; if either fails, log and let exception propagate."""
        Prior = self.ExecuteQuery(
            "SELECT COUNT(*) AS n FROM TranscodeAttempts ta JOIN MediaFiles mf ON mf.Id = ta.MediaFileId "
            "WHERE ta.MediaFileId = %s AND ta.Success = FALSE "
            "AND ta.AttemptDate > GREATEST("
            "  COALESCE((SELECT MAX(AttemptDate) FROM TranscodeAttempts WHERE MediaFileId = %s AND Success = TRUE), 'epoch'::timestamp), "
            "  COALESCE(mf.LastFailureResetAt, 'epoch'::timestamp)"
            ")",
            (int(MediaFileId), int(MediaFileId)),
        )
        PriorCount = int(Prior[0]['n']) if Prior else 0

        self.ExecuteNonQuery(
            "INSERT INTO FailureBudgetResets (MediaFileId, OperatorName, PriorFailureCount) VALUES (%s, %s, %s)",
            (int(MediaFileId), OperatorName or 'unknown', PriorCount),
        )
        self.ExecuteNonQuery(
            "UPDATE MediaFiles SET LastFailureResetAt = NOW() WHERE Id = %s",
            (int(MediaFileId),),
        )
        LoggingService.LogInfo(
            "FailureBudget reset for MediaFileId=" + str(MediaFileId) + " by " + str(OperatorName) + " (prior failures=" + str(PriorCount) + ")",
            "FailedJobsRepository", "ResetFailureBudget"
        )

    # directive: failure-accounting | # see failure-accounting.C7
    def GetAttemptHistory(self, MediaFileId: int) -> list:
        """Full TranscodeAttempts history for a MediaFile for the surface modal."""
        return self.ExecuteQuery(
            "SELECT Id, AttemptDate, Success, ProfileName, WorkerName, ErrorMessage, "
            "VMAF, TranscodeDurationSeconds, OldSizeBytes, NewSizeBytes "
            "FROM TranscodeAttempts WHERE MediaFileId = %s ORDER BY AttemptDate DESC LIMIT 100",
            (int(MediaFileId),),
        )

    # directive: table-renderer-service | # see shared-table-renderer.S9
    FailedJobsSortWhitelist = {
        "LastAttemptDate": "r.last_attempt",
        "FailureCount": "r.fail_count",
        "FileName": "mf.FileName",
        "AssignedProfile": "mf.AssignedProfile",
        "SizeMB": "mf.SizeMB",
    }

    # directive: table-renderer-service | # see shared-table-renderer.S9
    def BuildFailedJobsSearchFilter(self, SearchTerm):
        """Return an IQueryFilter that ILIKEs FileName + RelativePath; returns None when empty."""
        if not SearchTerm:
            return None
        return _FailedJobsSearchFilter(EscapeLikePattern(SearchTerm))

    # directive: table-renderer-service | # see shared-table-renderer.S9
    def GetFailedJobsPaged(self, Query):
        """Paged capped-jobs query routed through PagedQueryBuilder with window-count strategy."""
        from Core.Querying import PagedQueryBuilder, PagedQueryResult, PagedQueryConfig, CountStrategy
        try:
            Cfg = PagedQueryConfig(DefaultPageSize=100, MaxPageSize=500)
            Builder = PagedQueryBuilder(self.DatabaseService, Cfg)
            RowsSelect = (
                "WITH ranked AS ("
                "  SELECT ta.MediaFileId, "
                "         COUNT(*) AS fail_count, "
                "         MAX(ta.AttemptDate) AS last_attempt, "
                "         (ARRAY_AGG(ta.ErrorMessage ORDER BY ta.AttemptDate DESC))[1] AS last_error, "
                "         (ARRAY_AGG(ta.WorkerName ORDER BY ta.AttemptDate DESC))[1] AS last_worker "
                "    FROM TranscodeAttempts ta "
                "    JOIN MediaFiles mf ON mf.Id = ta.MediaFileId "
                "   WHERE ta.Success = FALSE "
                "     AND ta.AttemptDate > GREATEST("
                "       COALESCE((SELECT MAX(AttemptDate) FROM TranscodeAttempts WHERE MediaFileId = ta.MediaFileId AND Success = TRUE), 'epoch'::timestamp), "
                "       COALESCE(mf.LastFailureResetAt, 'epoch'::timestamp)"
                "     ) "
                "   GROUP BY ta.MediaFileId"
                ") "
                "SELECT mf.Id AS MediaFileId, mf.FileName, COALESCE(mf.RelativePath, '') AS FilePath, "
                "       r.fail_count AS FailureCount, r.last_error AS LastErrorMessage, "
                "       r.last_attempt AS LastAttemptDate, mf.AssignedProfile, "
                "       r.last_worker AS LastWorkerName, mf.SizeMB, mf.LastFailureResetAt, "
                "       COUNT(*) OVER () AS __TotalCount "
                "  FROM ranked r "
                "  JOIN MediaFiles mf ON mf.Id = r.MediaFileId"
            )
            StaticWhere = (
                "r.fail_count >= COALESCE((SELECT MaxEncodeFailures FROM FailureBudgetConfig WHERE Id = 1), 3)",
                (),
            )
            Result = Builder.Execute(
                RowsSelect=RowsSelect,
                Query=Query,
                StaticWhere=StaticWhere,
                CountStrategyChoice=CountStrategy.WINDOW,
            )
            return Result
        except Exception as Ex:
            LoggingService.LogException("Exception getting paged failed jobs", Ex, "FailedJobsRepository", "GetFailedJobsPaged")
            from Core.Querying import PagedQueryResult as _PQR
            return _PQR(Rows=[], TotalCount=0, Page=Query.Page, PageSize=Query.PageSize)
