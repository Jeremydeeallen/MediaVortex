"""
SQL Queries Controller
Handles database query execution and common troubleshooting queries
"""

from flask import Blueprint, jsonify, request
from typing import Dict, Any, List
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService

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
        
        # Security check - only allow SELECT queries for safety
        if not query.strip().upper().startswith('SELECT'):
            return jsonify({
                "Success": False,
                "ErrorMessage": "Only SELECT queries are allowed for security reasons"
            }), 400
        
        # Execute query
        results = SharedDatabaseManager.DatabaseService.ExecuteQuery(query, parameters)
        
        # Convert results to list of dictionaries
        if results:
            rows = [dict(row) for row in results]
            # Get column names from the first row (sqlite3.Row objects)
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

@SQLQueriesBlueprint.route('/GetServiceLogs', methods=['GET'])
def GetServiceLogs():
    """Get recent logs for a specific service."""
    try:
        LoggingService.LogFunctionEntry("GetServiceLogs", "SQLQueriesController")
        
        service_name = request.args.get('ServiceName', '')
        hours = int(request.args.get('Hours', 2))
        log_level = request.args.get('LogLevel', '')
        limit = int(request.args.get('Limit', 50))
        
        # Build query
        query = """
        SELECT LogLevel, Message, Timestamp, Component, FunctionName
        FROM Logs 
        WHERE Timestamp >= datetime('now', '-{} hours')
        """.format(hours)
        
        parameters = []
        
        if service_name:
            query += " AND Component LIKE ?"
            # Use more specific wildcard patterns for better matching
            if service_name == "TranscodeService":
                parameters.append("%Transcode%")
            elif service_name == "QualityTestingService" or service_name == "QualityCompareService":
                parameters.append("%Quality%")
            elif service_name == "SystemOrchestratorService":
                parameters.append("%SystemOrchestrator%")
            else:
                parameters.append(f"%{service_name}%")
        
        if log_level:
            query += " AND LogLevel = ?"
            parameters.append(log_level)
        
        query += " ORDER BY Timestamp DESC LIMIT ?"
        parameters.append(limit)
        
        results = SharedDatabaseManager.DatabaseService.ExecuteQuery(query, parameters)
        
        if results:
            rows = [dict(row) for row in results]
        else:
            rows = []
        
        LoggingService.LogInfo(f"Retrieved {len(rows)} log entries for service: {service_name}", "SQLQueriesController", "GetServiceLogs")
        
        return jsonify({
            "Success": True,
            "Logs": rows,
            "Count": len(rows)
        })
        
    except Exception as e:
        error_msg = f"Exception getting service logs: {str(e)}"
        LoggingService.LogException(error_msg, e, "SQLQueriesController", "GetServiceLogs")
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
        
        query = """
        SELECT Id, FilePath, FileName, Directory, SizeMB, Status, Priority, 
               DateAdded, DateStarted, DateCompleted, ProfileId, ErrorMessage, Progress
        FROM TranscodeQueue
        ORDER BY Priority DESC, DateAdded ASC
        LIMIT 100
        """
        
        results = SharedDatabaseManager.DatabaseService.ExecuteQuery(query)
        
        if results:
            rows = [dict(row) for row in results]
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

@SQLQueriesBlueprint.route('/GetQualityTestQueue', methods=['GET'])
def GetQualityTestQueue():
    """Get quality testing queue status."""
    try:
        LoggingService.LogFunctionEntry("GetQualityTestQueue", "SQLQueriesController")
        
        query = """
        SELECT Id, TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, FileName, 
               Status, Priority, DateAdded, DateStarted, DateCompleted, 
               VMAFScore, ErrorMessage, RetryCount, MaxRetries, StrategyType, StrategyId
        FROM QualityTestingQueue
        ORDER BY Priority DESC, DateAdded ASC
        LIMIT 100
        """
        
        results = SharedDatabaseManager.DatabaseService.ExecuteQuery(query)
        
        if results:
            rows = [dict(row) for row in results]
        else:
            rows = []
        
        LoggingService.LogInfo(f"Retrieved {len(rows)} quality test queue items", "SQLQueriesController", "GetQualityTestQueue")
        
        return jsonify({
            "Success": True,
            "QueueItems": rows,
            "Count": len(rows)
        })
        
    except Exception as e:
        error_msg = f"Exception getting quality test queue: {str(e)}"
        LoggingService.LogException(error_msg, e, "SQLQueriesController", "GetQualityTestQueue")
        return jsonify({"Success": False, "ErrorMessage": error_msg}), 500

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
        WHERE Timestamp >= datetime('now', '-{} hours')
        AND LogLevel IN ('ERROR', 'CRITICAL', 'WARNING')
        GROUP BY Component, LogLevel
        ORDER BY Count DESC
        """.format(hours)
        
        error_results = SharedDatabaseManager.DatabaseService.ExecuteQuery(error_query)
        
        if error_results:
            error_rows = [dict(row) for row in error_results]
        else:
            error_rows = []
        
        # Get recent errors
        recent_errors_query = """
        SELECT LogLevel, Message, Timestamp, Component, FunctionName
        FROM Logs 
        WHERE Timestamp >= datetime('now', '-{} hours')
        AND LogLevel IN ('ERROR', 'CRITICAL')
        ORDER BY Timestamp DESC
        LIMIT 20
        """.format(hours)
        
        recent_results = SharedDatabaseManager.DatabaseService.ExecuteQuery(recent_errors_query)
        
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
        
        # Get table list
        tables_query = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        table_results = SharedDatabaseManager.DatabaseService.ExecuteQuery(tables_query)
        
        tables = []
        if table_results:
            for row in table_results:
                table_name = row[0]
                
                # Get table info
                table_info_query = f"PRAGMA table_info({table_name})"
                info_results = SharedDatabaseManager.DatabaseService.ExecuteQuery(table_info_query)
                
                columns = []
                if info_results:
                    for col in info_results:
                        columns.append({
                            "Name": col[1],
                            "Type": col[2],
                            "NotNull": bool(col[3]),
                            "DefaultValue": col[4],
                            "PrimaryKey": bool(col[5])
                        })
                
                # Get row count
                count_query = f"SELECT COUNT(*) FROM {table_name}"
                count_result = SharedDatabaseManager.DatabaseService.ExecuteQuery(count_query)
                row_count = count_result[0][0] if count_result else 0
                
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
