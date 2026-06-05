"""
SQL Queries Controller
Handles database query execution and common troubleshooting queries
"""

from flask import Blueprint, jsonify, request
from typing import Dict, Any, List
from Repositories.DatabaseManager import DatabaseManager
from Core.Database.DatabaseService import EscapeLikePattern
from Core.Logging.LoggingService import LoggingService

# Create blueprint
SQLQueriesBlueprint = Blueprint('SQLQueries', __name__)

# Shared database manager
SharedDatabaseManager = DatabaseManager()

@SQLQueriesBlueprint.route('/ExecuteQuery', methods=['POST'])
def ExecuteQuery():
    """Execute a custom SQL query."""
    try:
        LoggingService.LogFunctionEntry("ExecuteQuery", "SQLQueriesController")

        data = request.get_json()
        if not data or 'Query' not in data:
            return jsonify({
                "Success": False,
                "ErrorMessage": "Query parameter is required"
            }), 400

        query = data['Query']
        parameters = data.get('Parameters', [])

        # Security check - only allow safe read-only queries
        NormalizedQuery = ' '.join(query.strip().upper().split())
        if not NormalizedQuery.startswith('SELECT'):
            return jsonify({
                "Success": False,
                "ErrorMessage": "Only SELECT queries are allowed for security reasons"
            }), 400

        # Block dangerous patterns even within SELECT statements
        DangerousPatterns = ['INSERT ', 'UPDATE ', 'DELETE ', 'DROP ', 'ALTER ', 'CREATE ',
                             'TRUNCATE ', 'GRANT ', 'REVOKE ', 'EXEC ', 'EXECUTE ',
                             'INTO ', 'COPY ', 'LO_EXPORT', 'LO_IMPORT', 'PG_READ_FILE',
                             'PG_WRITE_FILE', 'PG_EXECUTE_SERVER_PROGRAM']
        for Pattern in DangerousPatterns:
            if Pattern in NormalizedQuery:
                return jsonify({
                    "Success": False,
                    "ErrorMessage": f"Query contains disallowed keyword: {Pattern.strip()}"
                }), 400

        # Block multiple statements (semicolons outside of string literals)
        if ';' in query:
            return jsonify({
                "Success": False,
                "ErrorMessage": "Multiple statements are not allowed"
            }), 400

        # Execute query
        results = SharedDatabaseManager.DatabaseService.ExecuteQuery(query, parameters)

        # Convert results to list of dictionaries
        if results:
            rows = [dict(row) for row in results]
            columns = list(results[0].keys()) if results else []
        else:
            rows = []
            columns = []

        LoggingService.LogInfo(f"Executed query successfully, returned {len(rows)} rows", "SQLQueriesController", "ExecuteQuery")

        return jsonify({
            "Success": True,
            "Results": rows,
            "RowCount": len(rows),
            "Columns": columns if results else []
        })

    except Exception as e:
        error_msg = f"Exception executing query: {str(e)}"
        LoggingService.LogException(error_msg, e, "SQLQueriesController", "ExecuteQuery")
        return jsonify({"Success": False, "ErrorMessage": error_msg}), 500

@SQLQueriesBlueprint.route('/GetServiceStatus', methods=['GET'])
def GetServiceStatus():
    """Get detailed status information for all services."""
    try:
        LoggingService.LogFunctionEntry("GetServiceStatus", "SQLQueriesController")

        query = """
        SELECT ServiceName, Status, HealthStatus, StartTime, LastHealthCheck,
               UptimeSeconds, MemoryUsage, CPUUsage, DatabaseConnection, DiskSpace,
               ErrorCount, MaxErrors, ActiveJobsCount, IsProcessing, LastErrorMessage,
               ProcessId, Version, ServiceType, CreatedAt, UpdatedAt
        FROM ServiceStatus
        ORDER BY ServiceName
        """

        results = SharedDatabaseManager.DatabaseService.ExecuteQuery(query)

        if results:
            rows = [dict(row) for row in results]
        else:
            rows = []

        LoggingService.LogInfo(f"Retrieved status for {len(rows)} services", "SQLQueriesController", "GetServiceStatus")

        return jsonify({
            "Success": True,
            "Services": rows,
            "Count": len(rows)
        })

    except Exception as e:
        error_msg = f"Exception getting service status: {str(e)}"
        LoggingService.LogException(error_msg, e, "SQLQueriesController", "GetServiceStatus")
        return jsonify({"Success": False, "ErrorMessage": error_msg}), 500

@SQLQueriesBlueprint.route('/GetActiveJobs', methods=['GET'])
def GetActiveJobs():
    """Get all active jobs across services."""
    try:
        LoggingService.LogFunctionEntry("GetActiveJobs", "SQLQueriesController")

        query = """
        SELECT Id, ServiceName, JobType, Status, StartedAt, CreatedAt, UpdatedAt,
               QueueId, ProcessId, ThreadId
        FROM ActiveJobs
        ORDER BY StartedAt DESC
        """

        results = SharedDatabaseManager.DatabaseService.ExecuteQuery(query)

        if results:
            rows = [dict(row) for row in results]
        else:
            rows = []

        LoggingService.LogInfo(f"Retrieved {len(rows)} active jobs", "SQLQueriesController", "GetActiveJobs")

        return jsonify({
            "Success": True,
            "ActiveJobs": rows,
            "Count": len(rows)
        })

    except Exception as e:
        error_msg = f"Exception getting active jobs: {str(e)}"
        LoggingService.LogException(error_msg, e, "SQLQueriesController", "GetActiveJobs")
        return jsonify({"Success": False, "ErrorMessage": error_msg}), 500

@SQLQueriesBlueprint.route('/GetTranscodeQueue', methods=['GET'])
def GetTranscodeQueue():
    """Get transcoding queue status."""
    try:
        LoggingService.LogFunctionEntry("GetTranscodeQueue", "SQLQueriesController")

        # directive: path-schema-migration | # see path.S8
        from Core.Path.Path import Path as _PathTQ, PathError as _PETQ
        from Core.Path.PathStorageRoots import GetPrefixMap as _GPMTQ
        _PmTQ = _GPMTQ()
        def _SynthTQ(Sid, Rel):
            if Sid is None:
                return ''
            try:
                return _PathTQ(Sid, Rel or '').CanonicalDisplay(_PmTQ)
            except _PETQ:
                return ''
        query = (
            "SELECT Id, StorageRootId AS TqStorageRootId, RelativePath AS TqRelativePath, "
            "FileName, Directory, SizeMB, Status, Priority, "
            "DateAdded, DateStarted, ProcessingMode "
            "FROM TranscodeQueue "
            "ORDER BY Priority DESC, DateAdded ASC "
            "LIMIT 100"
        )

        results = SharedDatabaseManager.DatabaseService.ExecuteQuery(query)

        if results:
            rows = []
            for row in results:
                _D = dict(row)
                _D['FilePath'] = _SynthTQ(_D.get('tqstoragerootid'), _D.get('tqrelativepath'))
                rows.append(_D)
        else:
            rows = []

        LoggingService.LogInfo(f"Retrieved {len(rows)} transcoding queue items", "SQLQueriesController", "GetTranscodeQueue")

        return jsonify({
            "Success": True,
            "QueueItems": rows,
            "Count": len(rows)
        })

    except Exception as e:
        error_msg = f"Exception getting transcode queue: {str(e)}"
        LoggingService.LogException(error_msg, e, "SQLQueriesController", "GetTranscodeQueue")
        return jsonify({"Success": False, "ErrorMessage": error_msg}), 500

# GetQualityTestQueue endpoint removed - now handled by QualityTestController at /api/QualityTest/Queue

@SQLQueriesBlueprint.route('/GetErrorSummary', methods=['GET'])
def GetErrorSummary():
    """Get error summary for troubleshooting."""
    try:
        LoggingService.LogFunctionEntry("GetErrorSummary", "SQLQueriesController")

        hours = int(request.args.get('Hours', 24))

        # Get error count by service
        error_query = """
        SELECT Component, LogLevel, COUNT(*) as Count
        FROM Logs
        WHERE Timestamp >= NOW() - INTERVAL '%s hours'
        AND LogLevel IN ('ERROR', 'CRITICAL', 'WARNING')
        GROUP BY Component, LogLevel
        ORDER BY Count DESC
        """

        error_results = SharedDatabaseManager.DatabaseService.ExecuteQuery(error_query, [hours])

        if error_results:
            error_rows = [dict(row) for row in error_results]
        else:
            error_rows = []

        # Get recent errors
        recent_errors_query = """
        SELECT LogLevel, Message, Timestamp, Component, FunctionName
        FROM Logs
        WHERE Timestamp >= NOW() - INTERVAL '%s hours'
        AND LogLevel IN ('ERROR', 'CRITICAL')
        ORDER BY Timestamp DESC
        LIMIT 20
        """

        recent_results = SharedDatabaseManager.DatabaseService.ExecuteQuery(recent_errors_query, [hours])

        if recent_results:
            recent_rows = [dict(row) for row in recent_results]
        else:
            recent_rows = []

        LoggingService.LogInfo(f"Retrieved error summary for last {hours} hours", "SQLQueriesController", "GetErrorSummary")

        return jsonify({
            "Success": True,
            "ErrorSummary": error_rows,
            "RecentErrors": recent_rows,
            "Hours": hours
        })

    except Exception as e:
        error_msg = f"Exception getting error summary: {str(e)}"
        LoggingService.LogException(error_msg, e, "SQLQueriesController", "GetErrorSummary")
        return jsonify({"Success": False, "ErrorMessage": error_msg}), 500

@SQLQueriesBlueprint.route('/GetDatabaseInfo', methods=['GET'])
def GetDatabaseInfo():
    """Get database schema and table information."""
    try:
        LoggingService.LogFunctionEntry("GetDatabaseInfo", "SQLQueriesController")

        # Get table list from PostgreSQL
        tables_query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
        table_results = SharedDatabaseManager.DatabaseService.ExecuteQuery(tables_query)

        tables = []
        if table_results:
            for row in table_results:
                table_name = row['table_name']

                # Get column info from information_schema
                table_info_query = """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """
                info_results = SharedDatabaseManager.DatabaseService.ExecuteQuery(table_info_query, (table_name,))

                # Get primary key columns
                pk_query = """
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                    AND tc.table_schema = 'public'
                    AND tc.table_name = %s
                """
                pk_results = SharedDatabaseManager.DatabaseService.ExecuteQuery(pk_query, (table_name,))
                pk_columns = {r['column_name'] for r in pk_results} if pk_results else set()

                columns = []
                if info_results:
                    for col in info_results:
                        columns.append({
                            "Name": col['column_name'],
                            "Type": col['data_type'],
                            "NotNull": col['is_nullable'] == 'NO',
                            "DefaultValue": col['column_default'],
                            "PrimaryKey": col['column_name'] in pk_columns
                        })

                # Get row count
                count_result = SharedDatabaseManager.DatabaseService.ExecuteScalar(
                    f'SELECT COUNT(*) FROM "{table_name}"'
                )
                row_count = count_result if count_result else 0

                tables.append({
                    "Name": table_name,
                    "Columns": columns,
                    "RowCount": row_count
                })

        LoggingService.LogInfo(f"Retrieved info for {len(tables)} database tables", "SQLQueriesController", "GetDatabaseInfo")

        return jsonify({
            "Success": True,
            "Tables": tables,
            "TableCount": len(tables)
        })

    except Exception as e:
        error_msg = f"Exception getting database info: {str(e)}"
        LoggingService.LogException(error_msg, e, "SQLQueriesController", "GetDatabaseInfo")
        return jsonify({"Success": False, "ErrorMessage": error_msg}), 500

@SQLQueriesBlueprint.route('/GetMediaFileComparison', methods=['GET'])
def GetMediaFileComparison():
    """Get side-by-side comparison of original vs transcoded media file."""
    try:
        LoggingService.LogFunctionEntry("GetMediaFileComparison", "SQLQueriesController")

        FileId = request.args.get('FileId', '')
        FilePath = request.args.get('FilePath', '')

        if not FileId and not FilePath:
            return jsonify({
                "Success": False,
                "ErrorMessage": "FileId or FilePath parameter is required"
            }), 400

        # directive: path-schema-migration | # see path.S8
        from Core.Path.Path import Path as _PathMC, PathError as _PEMC
        from Core.Path.PathStorageRoots import GetStorageRoots as _GSRMC, GetPrefixMap as _GPMMC
        _PmMC = _GPMMC()
        def _SynthMC(Sid, Rel):
            if Sid is None:
                return ''
            try:
                return _PathMC(Sid, Rel or '').CanonicalDisplay(_PmMC)
            except _PEMC:
                return ''
        OriginalQueryHead = (
            "SELECT Id, StorageRootId AS OrStorageRootId, RelativePath AS OrRelativePath, "
            "FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps, "
            "Resolution, Codec, DurationMinutes, FrameRate, TotalFrames, CodecProfile, "
            "ColorRange, FieldOrder, HasBFrames, RefFrames, PixelFormat, Level, "
            "AudioChannels, AudioSampleRate, AudioSampleFormat, AudioChannelLayout, "
            "ContainerFormat, OverallBitrate, AssignedProfile "
            "FROM MediaFiles WHERE "
        )

        if FileId:
            OriginalQuery = OriginalQueryHead + "Id = %s"
            OriginalParams = (FileId,)
        else:
            try:
                _MCP = _PathMC.FromLegacyString(FilePath, _GSRMC())
                OriginalQuery = OriginalQueryHead + "StorageRootId = %s AND RelativePath = %s"
                OriginalParams = (_MCP.StorageRootId, _MCP.RelativePath)
            except _PEMC:
                return jsonify({"Success": False, "ErrorMessage": f"FilePath could not be parsed against StorageRoots: {FilePath!r}"}), 400

        OriginalResults = SharedDatabaseManager.DatabaseService.ExecuteQuery(OriginalQuery, OriginalParams)
        if OriginalResults:
            OriginalResults[0] = dict(OriginalResults[0])
            OriginalResults[0]['FilePath'] = _SynthMC(OriginalResults[0].get('orstoragerootid'), OriginalResults[0].get('orrelativepath'))

        if not OriginalResults:
            return jsonify({
                "Success": False,
                "ErrorMessage": "Original file not found"
            }), 404

        OriginalFile = dict(OriginalResults[0])

        # directive: path-schema-migration | # see path.S8
        from Core.Path.Path import Path as _PathSQ1, PathError as _PESQ1
        from Core.Path.PathStorageRoots import GetPrefixMap as _GPMSQ1
        _PmSQ1 = _GPMSQ1()
        def _SynthSQ1(Sid, Rel):
            if Sid is None:
                return ''
            try:
                return _PathSQ1(Sid, Rel or '').CanonicalDisplay(_PmSQ1)
            except _PESQ1:
                return ''
        TranscodedQuery = (
            "SELECT ta.Id, ta.StorageRootId AS TaStorageRootId, ta.RelativePath AS TaRelativePath, "
            "ta.OldSizeBytes, ta.NewSizeBytes, ta.SizeReductionBytes, "
            "ta.SizeReductionPercent, ta.VideoBitrateKbps, ta.AudioBitrateKbps, "
            "ta.ProfileName, ta.Quality, ta.AttemptDate, ta.Success, ta.ErrorMessage, "
            "ta.TranscodeDurationSeconds, ta.FfpmpegCommand, ta.VMAF, "
            "qtr.VMAFScore, qtr.PassesThreshold, qtr.TestDuration, qtr.DateTested, "
            "qtr.Status as QualityTestStatus, qtr.ErrorMessage as QualityTestError "
            "FROM TranscodeAttempts ta "
            "LEFT JOIN QualityTestResults qtr ON ta.Id = qtr.TranscodeAttemptId "
            "WHERE ta.MediaFileId = %s "
            "ORDER BY ta.AttemptDate DESC "
            "LIMIT 1"
        )

        TranscodedResults = SharedDatabaseManager.DatabaseService.ExecuteQuery(TranscodedQuery, (OriginalFile['id'],))

        TranscodedFile = None
        if TranscodedResults:
            TranscodedFile = dict(TranscodedResults[0])
            TranscodedFile['FilePath'] = _SynthSQ1(TranscodedFile.get('tastoragerootid'), TranscodedFile.get('tarelativepath'))

        ArchivedQuery = (
            "SELECT Id, StorageRootId AS ArStorageRootId, RelativePath AS ArRelativePath, "
            "FileName, SizeMB, VideoBitrateKbps, AudioBitrateKbps, "
            "Resolution, Codec, DurationMinutes, FrameRate, TotalFrames, CodecProfile, "
            "ColorRange, FieldOrder, HasBFrames, RefFrames, PixelFormat, Level, "
            "AudioChannels, AudioSampleRate, AudioSampleFormat, AudioChannelLayout, "
            "ContainerFormat, OverallBitrate, TranscodeAttemptId "
            "FROM MediaFilesArchive "
            "WHERE Id = %s "
            "ORDER BY ArchiveDate DESC "
            "LIMIT 1"
        )

        ArchivedResults = SharedDatabaseManager.DatabaseService.ExecuteQuery(ArchivedQuery, (OriginalFile['id'],))

        ArchivedFile = None
        if ArchivedResults:
            ArchivedFile = dict(ArchivedResults[0])
            ArchivedFile['FilePath'] = _SynthSQ1(ArchivedFile.get('arstoragerootid'), ArchivedFile.get('arrelativepath'))

        LoggingService.LogInfo(f"Retrieved media file comparison for: {OriginalFile['filepath']}", "SQLQueriesController", "GetMediaFileComparison")

        return jsonify({
            "Success": True,
            "OriginalFile": OriginalFile,
            "TranscodedFile": TranscodedFile,
            "ArchivedFile": ArchivedFile
        })

    except Exception as e:
        error_msg = f"Exception getting media file comparison: {str(e)}"
        LoggingService.LogException(error_msg, e, "SQLQueriesController", "GetMediaFileComparison")
        return jsonify({"Success": False, "ErrorMessage": error_msg}), 500

@SQLQueriesBlueprint.route('/GetRecentSuccesses', methods=['GET'])
def GetRecentSuccesses():
    """Get recent successful transcodes."""
    try:
        LoggingService.LogFunctionEntry("GetRecentSuccesses", "SQLQueriesController")

        Limit = int(request.args.get('limit', 15))

        # directive: path-schema-migration | # see path.S8
        from Core.Path.Path import Path as _PathSQ2, PathError as _PESQ2
        from Core.Path.PathStorageRoots import GetPrefixMap as _GPMSQ2
        _PmSQ2 = _GPMSQ2()
        def _SynthSQ2(Sid, Rel):
            if Sid is None:
                return ''
            try:
                return _PathSQ2(Sid, Rel or '').CanonicalDisplay(_PmSQ2)
            except _PESQ2:
                return ''
        query = (
            "SELECT ta.StorageRootId AS TaStorageRootId, ta.RelativePath AS TaRelativePath, "
            "ta.ProfileName, ta.SizeReductionPercent, "
            "ta.TranscodeDurationSeconds, ta.AttemptDate, ta.NewSizeBytes, ta.OldSizeBytes, "
            "ta.VMAF "
            "FROM TranscodeAttempts ta "
            "WHERE ta.Success = TRUE AND ta.FileReplaced = TRUE "
            "ORDER BY ta.AttemptDate DESC "
            "LIMIT %s"
        )

        results = SharedDatabaseManager.DatabaseService.ExecuteQuery(query, [Limit])

        if results:
            rows = []
            for row in results:
                _D = dict(row)
                _D['FilePath'] = _SynthSQ2(_D.get('tastoragerootid'), _D.get('tarelativepath'))
                rows.append(_D)
        else:
            rows = []

        LoggingService.LogInfo(f"Retrieved {len(rows)} recent successful transcodes", "SQLQueriesController", "GetRecentSuccesses")

        return jsonify({
            "Success": True,
            "Results": rows,
            "Count": len(rows)
        })

    except Exception as e:
        error_msg = f"Exception getting recent successes: {str(e)}"
        LoggingService.LogException(error_msg, e, "SQLQueriesController", "GetRecentSuccesses")
        return jsonify({"Success": False, "ErrorMessage": error_msg}), 500

@SQLQueriesBlueprint.route('/GetRecentScanRuns', methods=['GET'])
def GetRecentScanRuns():
    """Recent scan completions for the Operations dashboard (directive 2026-05-28).

    "Real failure" classification:
      - Always include Status='Completed'
      - Include Status='Failed' UNLESS ErrorMessage matches a housekeeping
        pattern (zombie clear, application restart, deploy-time stuck cleanup,
        operator soft-stop). These are admin actions, not failures the operator
        needs to investigate.
      - Exclude Status='Stopped' entirely -- soft-stop is an operator action.

    The pattern list is intentionally explicit so future additions are one
    line in this file. If the operator starts seeing noise on Operations,
    add the matching substring here.
    """
    try:
        LoggingService.LogFunctionEntry("GetRecentScanRuns", "SQLQueriesController")

        Limit = int(request.args.get('limit', 15))
        if Limit < 1:
            Limit = 15
        if Limit > 50:
            Limit = 50

        # Housekeeping patterns -- substrings matched case-insensitively
        # against ScanJobs.ErrorMessage. Failed rows matching ANY of these
        # are admin actions, not real failures.
        HousekeepingPatterns = [
            '%Application restarted%',
            '%Zombie%',
            '%pre-redeploy%',
            '%Stuck scan cleaned by StuckJobDetectionService%',
            '%post-deploy mass clear%',
            '%post-redeploy mass clear%',
            '%Stopped pre-redeploy%',
            '%cleared post-restart%',
            '%cleared post-deploy%',
        ]

        # Build NOT ILIKE ALL (pattern1, pattern2, ...) clause
        NotLikeClauses = " AND ".join(["sj.ErrorMessage NOT ILIKE %s"] * len(HousekeepingPatterns))

        # The filter applies to BOTH Completed and Failed rows. A scan that
        # was interrupted by an Application restart is marked Status='Completed'
        # with ErrorMessage='Application restarted' (known quirk per
        # FileScanning.flow.md). Operators don't want that in their success
        # list either -- the partial counts are not a real success.
        Query = f"""
            SELECT sj.RootFolderPath, sj.WorkerName, sj.Status,
                   sj.StartTime, sj.EndTime,
                   EXTRACT(EPOCH FROM (sj.EndTime - sj.StartTime))::int AS DurationSec,
                   sj.NewFiles, sj.UpdatedFiles, sj.DeletedFiles, sj.ProcessedFiles,
                   sj.ErrorMessage
            FROM ScanJobs sj
            WHERE sj.EndTime IS NOT NULL
              AND sj.Status IN ('Completed', 'Failed')
              AND (sj.ErrorMessage IS NULL OR ({NotLikeClauses}))
            ORDER BY sj.EndTime DESC
            LIMIT %s
        """
        Params = HousekeepingPatterns + [Limit]
        Results = SharedDatabaseManager.DatabaseService.ExecuteQuery(Query, Params)
        Rows = [dict(R) for R in (Results or [])]

        LoggingService.LogInfo(f"Retrieved {len(Rows)} recent scan runs", "SQLQueriesController", "GetRecentScanRuns")

        return jsonify({"Success": True, "Results": Rows, "Count": len(Rows)})

    except Exception as e:
        error_msg = f"Exception getting recent scan runs: {str(e)}"
        LoggingService.LogException(error_msg, e, "SQLQueriesController", "GetRecentScanRuns")
        return jsonify({"Success": False, "ErrorMessage": error_msg}), 500


@SQLQueriesBlueprint.route('/GetStuckJobs', methods=['GET'])
def GetStuckJobs():
    """Get jobs stuck in processing."""
    try:
        LoggingService.LogFunctionEntry("GetStuckJobs", "SQLQueriesController")

        # directive: path-schema-migration | # see path.S8
        from Core.Path.Path import Path as _PathSJ, PathError as _PESJ
        from Core.Path.PathStorageRoots import GetPrefixMap as _GPMSJ
        _PmSJ = _GPMSJ()
        def _SynthSJ(Sid, Rel):
            if Sid is None:
                return ''
            try:
                return _PathSJ(Sid, Rel or '').CanonicalDisplay(_PmSJ)
            except _PESJ:
                return ''
        StuckJobs = []

        TranscodeQuery = (
            "SELECT 'TranscodeQueue' as jobtype, Id, "
            "StorageRootId AS TqStorageRootId, RelativePath AS TqRelativePath, "
            "FileName, Status, DateStarted, "
            "EXTRACT(EPOCH FROM (NOW() - DateStarted)) / 60 as durationminutes "
            "FROM TranscodeQueue "
            "WHERE Status = 'Running' AND DateStarted < NOW() - INTERVAL '1 hour' "
            "ORDER BY DateStarted ASC"
        )

        TranscodeResults = SharedDatabaseManager.DatabaseService.ExecuteQuery(TranscodeQuery)

        for row in TranscodeResults:
            StuckJobs.append({
                "JobType": row['jobtype'],
                "JobId": row['id'],
                "FilePath": _SynthSJ(row.get('tqstoragerootid'), row.get('tqrelativepath')),
                "FileName": row['filename'],
                "Status": row['status'],
                "StartedAt": str(row['datestarted']),
                "Duration": row['durationminutes']
            })

        # Get stuck active jobs
        ActiveJobsQuery = """
        SELECT 'ActiveJob' as jobtype, Id, ServiceName, JobType as jobtypename, Status, StartedAt,
               EXTRACT(EPOCH FROM (NOW() - StartedAt)) / 60 as durationminutes
        FROM ActiveJobs
        WHERE Status = 'Running' AND StartedAt < NOW() - INTERVAL '1 hour'
        ORDER BY StartedAt ASC
        """

        ActiveJobsResults = SharedDatabaseManager.DatabaseService.ExecuteQuery(ActiveJobsQuery)

        for row in ActiveJobsResults:
            StuckJobs.append({
                "JobType": row['jobtype'],
                "JobId": row['id'],
                "FilePath": row['servicename'],
                "FileName": row['jobtypename'],
                "Status": row['status'],
                "StartedAt": str(row['startedat']),
                "Duration": row['durationminutes']
            })

        # Get stuck quality testing jobs
        QualityTestQuery = """
        SELECT 'QualityTest' as jobtype, Id, TranscodeAttemptId, OriginalFilePath,
               DateStarted,
               EXTRACT(EPOCH FROM (NOW() - DateStarted)) / 60 as durationminutes
        FROM QualityTestingQueue
        WHERE DateStarted IS NOT NULL AND DateCompleted IS NULL
              AND DateStarted < NOW() - INTERVAL '2 hours'
        ORDER BY DateStarted ASC
        """

        QualityTestResults = SharedDatabaseManager.DatabaseService.ExecuteQuery(QualityTestQuery)

        for row in QualityTestResults:
            StuckJobs.append({
                "JobType": row['jobtype'],
                "JobId": row['id'],
                "FilePath": row['originalfilepath'],
                "FileName": f"QualityTest-{row['transcodeattemptid']}",
                "Status": "Running",
                "StartedAt": str(row['datestarted']),
                "Duration": row['durationminutes']
            })

        LoggingService.LogInfo(f"Retrieved {len(StuckJobs)} stuck jobs", "SQLQueriesController", "GetStuckJobs")

        return jsonify({
            "Success": True,
            "StuckJobs": StuckJobs,
            "Count": len(StuckJobs)
        })

    except Exception as e:
        error_msg = f"Exception getting stuck jobs: {str(e)}"
        LoggingService.LogException(error_msg, e, "SQLQueriesController", "GetStuckJobs")
        return jsonify({"Success": False, "ErrorMessage": error_msg}), 500
