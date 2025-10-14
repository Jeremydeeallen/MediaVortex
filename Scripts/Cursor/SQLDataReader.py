"""
SQLDataReader.py - General Database Data Reader Tool
Reads and analyzes data from any table in the MediaVortex database.
"""

import sys
import os
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# Add parent directory to path to import shared services
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
root_dir = os.path.dirname(parent_dir)
sys.path.append(root_dir)

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


class SQLDataReader:
    """General database data reader and analyzer."""
    
    def __init__(self):
        """Initialize the data reader."""
        self.DatabaseManager = DatabaseManager()
    
    def GetAvailableTables(self) -> List[str]:
        """
        Get list of all available tables in the database.
        
        Returns:
            List of table names
        """
        try:
            query = """
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """
            results = self.DatabaseManager.DatabaseService.ExecuteQuery(query)
            if results:
                tables = [row[0] for row in results]
                LoggingService.LogInfo(f"Found {len(tables)} tables in database", "SQLDataReader", "GetAvailableTables")
                return tables
            return []
        except Exception as e:
            LoggingService.LogException("Error getting available tables", e, "SQLDataReader", "GetAvailableTables")
            return []
    
    def GetTableSchema(self, TableName: str) -> List[Dict[str, Any]]:
        """
        Get schema information for a specific table.
        
        Args:
            TableName: Name of the table
        
        Returns:
            List of column information dictionaries
        """
        try:
            query = f"PRAGMA table_info({TableName})"
            results = self.DatabaseManager.DatabaseService.ExecuteQuery(query)
            if results:
                columns = []
                for row in results:
                    columns.append({
                        "ColumnName": row[1],
                        "DataType": row[2],
                        "NotNull": bool(row[3]),
                        "DefaultValue": row[4],
                        "PrimaryKey": bool(row[5])
                    })
                LoggingService.LogInfo(f"Retrieved schema for table {TableName}", "SQLDataReader", "GetTableSchema")
                return columns
            return []
        except Exception as e:
            LoggingService.LogException(f"Error getting schema for table {TableName}", e, "SQLDataReader", "GetTableSchema")
            return []
    
    def ReadTableData(self, TableName: str, Filters: Dict[str, Any] = None, 
                     Limit: int = 100, OrderBy: str = None, 
                     OrderDirection: str = "ASC") -> List[Dict[str, Any]]:
        """
        Read data from any table with optional filters.
        
        Args:
            TableName: Name of the table to query
            Filters: Dictionary of column filters (exact match or LIKE for strings)
            Limit: Maximum number of records to return
            OrderBy: Column name to order by
            OrderDirection: Sort direction (ASC or DESC)
        
        Returns:
            List of table records
        """
        try:
            # Validate table name to prevent SQL injection
            available_tables = self.GetAvailableTables()
            if TableName not in available_tables:
                LoggingService.LogError(f"Table '{TableName}' not found in database", "SQLDataReader", "ReadTableData")
                return []
            
            # Build query with filters
            query = f"SELECT * FROM {TableName} WHERE 1=1"
            params = []
            
            if Filters:
                for column, value in Filters.items():
                    if value is not None:
                        # Check if column exists in table schema
                        schema = self.GetTableSchema(TableName)
                        column_names = [col["ColumnName"] for col in schema]
                        if column not in column_names:
                            LoggingService.LogWarning(f"Column '{column}' not found in table '{TableName}'", "SQLDataReader", "ReadTableData")
                            continue
                        
                        # Use LIKE for string values, exact match for others
                        if isinstance(value, str) and "%" in value:
                            query += f" AND {column} LIKE ?"
                            params.append(value)
                        else:
                            query += f" AND {column} = ?"
                            params.append(value)
            
            # Add ordering
            if OrderBy:
                # Validate order by column
                schema = self.GetTableSchema(TableName)
                column_names = [col["ColumnName"] for col in schema]
                if OrderBy in column_names:
                    query += f" ORDER BY {OrderBy} {OrderDirection}"
                else:
                    LoggingService.LogWarning(f"Order by column '{OrderBy}' not found in table '{TableName}'", "SQLDataReader", "ReadTableData")
            
            # Add limit
            query += f" LIMIT {Limit}"
            
            # Execute query
            results = self.DatabaseManager.DatabaseService.ExecuteQuery(query, params)
            
            if results:
                # Convert sqlite3.Row objects to dictionaries
                dict_results = [dict(row) for row in results]
                LoggingService.LogInfo(f"Retrieved {len(dict_results)} records from {TableName}", "SQLDataReader", "ReadTableData")
                return dict_results
            else:
                LoggingService.LogInfo(f"No records found in {TableName}", "SQLDataReader", "ReadTableData")
                return []
                
        except Exception as e:
            LoggingService.LogException(f"Error reading data from table {TableName}", e, "SQLDataReader", "ReadTableData")
            return []
    
    def ReadLogs(self, LogLevel: str = None, FunctionName: str = None, 
                 Component: str = None, StartDate: str = None, 
                 EndDate: str = None, Limit: int = 100, 
                 OrderBy: str = "DESC", Message: str = None) -> List[Dict[str, Any]]:
        """
        Read logs from database with optional filters (backward compatibility method).
        
        Args:
            LogLevel: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            FunctionName: Filter by function name
            Component: Filter by service name
            StartDate: Start date filter (YYYY-MM-DD format)
            EndDate: End date filter (YYYY-MM-DD format)
            Limit: Maximum number of records to return
            OrderBy: Sort order (ASC or DESC)
            Message: Filter by message content (partial match)
        
        Returns:
            List of log records
        """
        filters = {}
        
        if LogLevel:
            filters["LogLevel"] = LogLevel
        if FunctionName:
            filters["FunctionName"] = f"%{FunctionName}%"
        if Component:
            filters["Component"] = Component
        if StartDate:
            filters["Timestamp"] = f"{StartDate} 00:00:00"
        if EndDate:
            # For end date, we need to handle this differently since we can't use >= and <= in the same filter
            # This is a limitation of the current filter system
            pass
        if Message:
            filters["Message"] = f"%{Message}%"
        
        return self.ReadTableData("Logs", filters, Limit, "Timestamp", OrderBy)
    
    def GetErrorSummary(self, Component: str = None, Hours: int = 24) -> Dict[str, Any]:
        """
        Get error summary for specified time period.
        
        Args:
            Component: Filter by service name
            Hours: Number of hours to look back
        
        Returns:
            Dictionary with error summary
        """
        try:
            # Calculate start time
            start_time = datetime.now() - timedelta(hours=Hours)
            start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
            
            # Build query for error summary
            query = """
                SELECT 
                    LogLevel,
                    Component,
                    FunctionName,
                    COUNT(*) as Count,
                    MAX(Timestamp) as LastOccurrence
                FROM Logs 
                WHERE Timestamp >= ? AND LogLevel IN ('ERROR', 'CRITICAL', 'WARNING')
            """
            params = [start_time_str]
            
            if Component:
                query += " AND Component = ?"
                params.append(Component)
            
            query += " GROUP BY LogLevel, Component, FunctionName ORDER BY Count DESC"
            
            results = self.DatabaseManager.DatabaseService.ExecuteQuery(query, params)
            
            # Convert sqlite3.Row objects to dictionaries
            if results:
                results = [dict(row) for row in results]
            
            # Get total counts by level
            total_query = """
                SELECT 
                    LogLevel,
                    COUNT(*) as Count
                FROM Logs 
                WHERE Timestamp >= ?
            """
            total_params = [start_time_str]
            
            if Component:
                total_query += " AND Component = ?"
                total_params.append(Component)
            
            total_query += " GROUP BY LogLevel"
            
            total_results = self.DatabaseManager.DatabaseService.ExecuteQuery(total_query, total_params)
            
            # Convert sqlite3.Row objects to dictionaries
            if total_results:
                total_results = [dict(row) for row in total_results]
            
            # Build summary
            summary = {
                "TimePeriod": f"Last {Hours} hours",
                "StartTime": start_time_str,
                "EndTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ServiceFilter": Component or "All Services",
                "ErrorBreakdown": results or [],
                "TotalCounts": {row["LogLevel"]: row["Count"] for row in total_results} if total_results else {},
                "TotalErrors": sum(row["Count"] for row in total_results if row["LogLevel"] in ["ERROR", "CRITICAL"]) if total_results else 0,
                "TotalWarnings": sum(row["Count"] for row in total_results if row["LogLevel"] == "WARNING") if total_results else 0
            }
            
            return summary
            
        except Exception as e:
            LoggingService.LogException("Error getting error summary", e, "LogReader", "GetErrorSummary")
            return {"Error": str(e)}
    
    def GetRecentErrors(self, Component: str = None, Limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent error and critical log entries.
        
        Args:
            Component: Filter by service name
            Limit: Maximum number of records to return
        
        Returns:
            List of recent error records
        """
        return self.ReadLogs(
            LogLevel="ERROR",
            Component=Component,
            Limit=Limit,
            OrderBy="DESC"
        ) + self.ReadLogs(
            LogLevel="CRITICAL",
            Component=Component,
            Limit=Limit,
            OrderBy="DESC"
        )
    
    def GetServiceErrors(self, Component: str, Hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get all errors for a specific service.
        
        Args:
            Component: Name of the service
            Hours: Number of hours to look back
        
        Returns:
            List of error records
        """
        try:
            start_time = datetime.now() - timedelta(hours=Hours)
            start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
            
            query = """
                SELECT * FROM Logs 
                WHERE Component = ? 
                AND LogLevel IN ('ERROR', 'CRITICAL', 'WARNING')
                AND Timestamp >= ?
                ORDER BY Timestamp DESC
            """
            
            results = self.DatabaseManager.DatabaseService.ExecuteQuery(query, [Component, start_time_str])
            if results:
                return [dict(row) for row in results]
            return []
            
        except Exception as e:
            LoggingService.LogException(f"Error getting service errors for {Component}", e, "LogReader", "GetServiceErrors")
            return []
    
    def PrintTableData(self, Data: List[Dict[str, Any]], TableName: str = "Data", ShowDetails: bool = True):
        """
        Print table data in a formatted way.
        
        Args:
            Data: List of table records
            TableName: Name of the table being displayed
            ShowDetails: Whether to show detailed information
        """
        if not Data:
            print(f"No data found in {TableName}.")
            return
        
        print(f"\n=== Found {len(Data)} records in {TableName} ===")
        print("-" * 80)
        
        for i, record in enumerate(Data):
            print(f"Record {i+1}:")
            
            # Special formatting for Logs table
            if TableName == "Logs":
                # Format timestamp
                timestamp = record.get("Timestamp", "Unknown")
                if isinstance(timestamp, str):
                    try:
                        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                        timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        pass
                
                # Color coding for log levels
                level = record.get("LogLevel", "UNKNOWN")
                level_colors = {
                    "DEBUG": "\033[36m",    # Cyan
                    "INFO": "\033[32m",     # Green
                    "WARNING": "\033[33m",  # Yellow
                    "ERROR": "\033[31m",    # Red
                    "CRITICAL": "\033[35m"  # Magenta
                }
                color = level_colors.get(level, "")
                reset_color = "\033[0m"
                
                print(f"  {color}[{level}]{reset_color} {timestamp}")
                print(f"  Service: {record.get('Component', 'Unknown')}")
                print(f"  Function: {record.get('FunctionName', 'Unknown')}")
                
                if ShowDetails:
                    message = record.get("Message", "")
                    if message:
                        # Wrap long messages
                        if len(message) > 70:
                            words = message.split()
                            lines = []
                            current_line = ""
                            for word in words:
                                if len(current_line + word) > 70:
                                    if current_line:
                                        lines.append(current_line)
                                    current_line = word
                                else:
                                    current_line += (" " + word) if current_line else word
                            if current_line:
                                lines.append(current_line)
                            for line in lines:
                                print(f"  Message: {line}")
                        else:
                            print(f"  Message: {message}")
                    
                    exception = record.get("Exception", "")
                    if exception:
                        print(f"  Exception: {exception}")
            else:
                # General formatting for other tables
                for key, value in record.items():
                    if value is not None:
                        # Format timestamps
                        if isinstance(value, str) and ("Timestamp" in key or "Date" in key or "Time" in key):
                            try:
                                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                                value = dt.strftime("%Y-%m-%d %H:%M:%S")
                            except:
                                pass
                        
                        # Truncate long values
                        if isinstance(value, str) and len(str(value)) > 100:
                            value = str(value)[:97] + "..."
                        
                        print(f"  {key}: {value}")
            
            print("-" * 80)
    
    def PrintLogs(self, Logs: List[Dict[str, Any]], ShowDetails: bool = True):
        """
        Print logs in a formatted way (backward compatibility method).
        
        Args:
            Logs: List of log records
            ShowDetails: Whether to show detailed information
        """
        self.PrintTableData(Logs, "Logs", ShowDetails)
    
    def FindCaseInsensitiveDuplicates(self, TableName: str, ColumnName: str) -> List[Dict[str, Any]]:
        """
        Find records where column values differ only by case.
        
        Args:
            TableName: Name of the table to search
            ColumnName: Name of the column to check for case-insensitive duplicates
        
        Returns:
            List of duplicate groups with case-insensitive matches
        """
        try:
            # Validate table name
            available_tables = self.GetAvailableTables()
            if TableName not in available_tables:
                LoggingService.LogError(f"Table '{TableName}' not found in database", "SQLDataReader", "FindCaseInsensitiveDuplicates")
                return []
            
            # Validate column name
            schema = self.GetTableSchema(TableName)
            column_names = [col["ColumnName"] for col in schema]
            if ColumnName not in column_names:
                LoggingService.LogError(f"Column '{ColumnName}' not found in table '{TableName}'", "SQLDataReader", "FindCaseInsensitiveDuplicates")
                return []
            
            # Find case-insensitive duplicates
            query = f"""
                SELECT 
                    LOWER({ColumnName}) as LowerValue,
                    COUNT(*) as Count,
                    GROUP_CONCAT(Id) as Ids,
                    GROUP_CONCAT({ColumnName}) as OriginalValues
                FROM {TableName}
                GROUP BY LOWER({ColumnName})
                HAVING COUNT(*) > 1
                ORDER BY Count DESC
            """
            
            results = self.DatabaseManager.DatabaseService.ExecuteQuery(query)
            if results:
                duplicates = [dict(row) for row in results]
                LoggingService.LogInfo(f"Found {len(duplicates)} case-insensitive duplicate groups in {TableName}.{ColumnName}", "SQLDataReader", "FindCaseInsensitiveDuplicates")
                return duplicates
            else:
                LoggingService.LogInfo(f"No case-insensitive duplicates found in {TableName}.{ColumnName}", "SQLDataReader", "FindCaseInsensitiveDuplicates")
                return []
                
        except Exception as e:
            LoggingService.LogException(f"Error finding case-insensitive duplicates in {TableName}.{ColumnName}", e, "SQLDataReader", "FindCaseInsensitiveDuplicates")
            return []
    
    def FindExactDuplicates(self, TableName: str, ColumnName: str) -> List[Dict[str, Any]]:
        """
        Find exact duplicate values in a column.
        
        Args:
            TableName: Name of the table to search
            ColumnName: Name of the column to check for exact duplicates
        
        Returns:
            List of duplicate groups with exact matches
        """
        try:
            # Validate table name
            available_tables = self.GetAvailableTables()
            if TableName not in available_tables:
                LoggingService.LogError(f"Table '{TableName}' not found in database", "SQLDataReader", "FindExactDuplicates")
                return []
            
            # Validate column name
            schema = self.GetTableSchema(TableName)
            column_names = [col["ColumnName"] for col in schema]
            if ColumnName not in column_names:
                LoggingService.LogError(f"Column '{ColumnName}' not found in table '{TableName}'", "SQLDataReader", "FindExactDuplicates")
                return []
            
            # Find exact duplicates
            query = f"""
                SELECT 
                    {ColumnName} as Value,
                    COUNT(*) as Count,
                    GROUP_CONCAT(Id) as Ids
                FROM {TableName}
                GROUP BY {ColumnName}
                HAVING COUNT(*) > 1
                ORDER BY Count DESC
            """
            
            results = self.DatabaseManager.DatabaseService.ExecuteQuery(query)
            if results:
                duplicates = [dict(row) for row in results]
                LoggingService.LogInfo(f"Found {len(duplicates)} exact duplicate groups in {TableName}.{ColumnName}", "SQLDataReader", "FindExactDuplicates")
                return duplicates
            else:
                LoggingService.LogInfo(f"No exact duplicates found in {TableName}.{ColumnName}", "SQLDataReader", "FindExactDuplicates")
                return []
                
        except Exception as e:
            LoggingService.LogException(f"Error finding exact duplicates in {TableName}.{ColumnName}", e, "SQLDataReader", "FindExactDuplicates")
            return []
    
    def VerifyFileOnDisk(self, FilePath: str) -> Dict[str, Any]:
        """
        Verify if a file exists on disk and get its actual size.
        
        Args:
            FilePath: Path to the file to verify
        
        Returns:
            Dictionary with file verification results
        """
        try:
            import os
            if os.path.exists(FilePath):
                file_size = os.path.getsize(FilePath)
                file_size_mb = file_size / (1024 * 1024)
                return {
                    "Exists": True,
                    "SizeBytes": file_size,
                    "SizeMB": round(file_size_mb, 2),
                    "Error": None
                }
            else:
                return {
                    "Exists": False,
                    "SizeBytes": None,
                    "SizeMB": None,
                    "Error": "File not found on disk"
                }
        except Exception as e:
            return {
                "Exists": False,
                "SizeBytes": None,
                "SizeMB": None,
                "Error": str(e)
            }
    
    def AnalyzeMediaFilesDuplicates(self) -> Dict[str, Any]:
        """
        Comprehensive analysis of MediaFiles table duplicates.
        
        Returns:
            Dictionary with detailed duplicate analysis and recommendations
        """
        try:
            LoggingService.LogInfo("Starting comprehensive MediaFiles duplicate analysis", "SQLDataReader", "AnalyzeMediaFilesDuplicates")
            
            # Find case-insensitive duplicates on FilePath
            case_insensitive_duplicates = self.FindCaseInsensitiveDuplicates("MediaFiles", "FilePath")
            
            # Find exact duplicates on FilePath
            exact_duplicates = self.FindExactDuplicates("MediaFiles", "FilePath")
            
            # Get detailed information for each duplicate group
            detailed_analysis = []
            
            # Process case-insensitive duplicates
            for duplicate_group in case_insensitive_duplicates:
                ids = [int(id_str) for id_str in duplicate_group["Ids"].split(",")]
                
                # Get detailed records for this duplicate group
                query = f"""
                    SELECT Id, FilePath, TranscodedByMediaVortex, LastScannedDate, SizeMB, Codec, Resolution
                    FROM MediaFiles 
                    WHERE Id IN ({','.join(map(str, ids))})
                    ORDER BY TranscodedByMediaVortex DESC, LastScannedDate DESC
                """
                
                records = self.DatabaseManager.DatabaseService.ExecuteQuery(query)
                if records:
                    records = [dict(row) for row in records]
                    
                    # Check if any non-transcoded files exist in archive
                    archive_check = []
                    disk_verification = []
                    for record in records:
                        if not record.get("TranscodedByMediaVortex", False):
                            archive_query = """
                                SELECT COUNT(*) as ArchiveCount
                                FROM MediaFilesArchive
                                WHERE FilePath = ?
                            """
                            archive_result = self.DatabaseManager.DatabaseService.ExecuteQuery(archive_query, (record["FilePath"],))
                            archive_count = archive_result[0]["ArchiveCount"] if archive_result else 0
                            archive_check.append({
                                "FilePath": record["FilePath"],
                                "InArchive": archive_count > 0
                            })
                        
                        # Verify file exists on disk and check size
                        disk_check = self.VerifyFileOnDisk(record["FilePath"])
                        disk_verification.append({
                            "FilePath": record["FilePath"],
                            "DatabaseSizeMB": record.get("SizeMB", 0),
                            "DiskExists": disk_check["Exists"],
                            "DiskSizeMB": disk_check["SizeMB"],
                            "SizeMatch": abs((record.get("SizeMB", 0) or 0) - (disk_check["SizeMB"] or 0)) < 0.1 if disk_check["Exists"] else False,
                            "Error": disk_check["Error"]
                        })
                    
                    # Determine which record to keep
                    transcoded_records = [r for r in records if r.get("TranscodedByMediaVortex", False)]
                    if transcoded_records:
                        keep_record = transcoded_records[0]  # Keep first transcoded record
                        keep_reason = "Has TranscodedByMediaVortex = TRUE"
                    else:
                        keep_record = records[0]  # Keep most recent
                        keep_reason = "Most recent LastScannedDate"
                    
                    # Records to delete
                    delete_records = [r for r in records if r["Id"] != keep_record["Id"]]
                    
                    detailed_analysis.append({
                        "Type": "Case-Insensitive",
                        "LowerPath": duplicate_group["LowerValue"],
                        "Count": duplicate_group["Count"],
                        "AllRecords": records,
                        "KeepRecord": keep_record,
                        "KeepReason": keep_reason,
                        "DeleteRecords": delete_records,
                        "ArchiveCheck": archive_check,
                        "DiskVerification": disk_verification,
                        "SafeToDelete": all(check["InArchive"] for check in archive_check if not any(r["Id"] == check["FilePath"] for r in transcoded_records))
                    })
            
            # Process exact duplicates
            for duplicate_group in exact_duplicates:
                ids = [int(id_str) for id_str in duplicate_group["Ids"].split(",")]
                
                # Get detailed records for this duplicate group
                query = f"""
                    SELECT Id, FilePath, TranscodedByMediaVortex, LastScannedDate, SizeMB, Codec, Resolution
                    FROM MediaFiles 
                    WHERE Id IN ({','.join(map(str, ids))})
                    ORDER BY TranscodedByMediaVortex DESC, LastScannedDate DESC
                """
                
                records = self.DatabaseManager.DatabaseService.ExecuteQuery(query)
                if records:
                    records = [dict(row) for row in records]
                    
                    # Check if any non-transcoded files exist in archive
                    archive_check = []
                    disk_verification = []
                    for record in records:
                        if not record.get("TranscodedByMediaVortex", False):
                            archive_query = """
                                SELECT COUNT(*) as ArchiveCount
                                FROM MediaFilesArchive
                                WHERE FilePath = ?
                            """
                            archive_result = self.DatabaseManager.DatabaseService.ExecuteQuery(archive_query, (record["FilePath"],))
                            archive_count = archive_result[0]["ArchiveCount"] if archive_result else 0
                            archive_check.append({
                                "FilePath": record["FilePath"],
                                "InArchive": archive_count > 0
                            })
                        
                        # Verify file exists on disk and check size
                        disk_check = self.VerifyFileOnDisk(record["FilePath"])
                        disk_verification.append({
                            "FilePath": record["FilePath"],
                            "DatabaseSizeMB": record.get("SizeMB", 0),
                            "DiskExists": disk_check["Exists"],
                            "DiskSizeMB": disk_check["SizeMB"],
                            "SizeMatch": abs((record.get("SizeMB", 0) or 0) - (disk_check["SizeMB"] or 0)) < 0.1 if disk_check["Exists"] else False,
                            "Error": disk_check["Error"]
                        })
                    
                    # Determine which record to keep
                    transcoded_records = [r for r in records if r.get("TranscodedByMediaVortex", False)]
                    if transcoded_records:
                        keep_record = transcoded_records[0]  # Keep first transcoded record
                        keep_reason = "Has TranscodedByMediaVortex = TRUE"
                    else:
                        keep_record = records[0]  # Keep most recent
                        keep_reason = "Most recent LastScannedDate"
                    
                    # Records to delete
                    delete_records = [r for r in records if r["Id"] != keep_record["Id"]]
                    
                    detailed_analysis.append({
                        "Type": "Exact",
                        "FilePath": duplicate_group["Value"],
                        "Count": duplicate_group["Count"],
                        "AllRecords": records,
                        "KeepRecord": keep_record,
                        "KeepReason": keep_reason,
                        "DeleteRecords": delete_records,
                        "ArchiveCheck": archive_check,
                        "DiskVerification": disk_verification,
                        "SafeToDelete": all(check["InArchive"] for check in archive_check if not any(r["Id"] == check["FilePath"] for r in transcoded_records))
                    })
            
            # Summary statistics
            total_duplicates = len(detailed_analysis)
            total_records_to_delete = sum(len(group["DeleteRecords"]) for group in detailed_analysis)
            safe_to_delete = sum(1 for group in detailed_analysis if group["SafeToDelete"])
            needs_archive_check = total_duplicates - safe_to_delete
            
            analysis_result = {
                "Summary": {
                    "TotalDuplicateGroups": total_duplicates,
                    "TotalRecordsToDelete": total_records_to_delete,
                    "SafeToDelete": safe_to_delete,
                    "NeedsArchiveCheck": needs_archive_check
                },
                "CaseInsensitiveDuplicates": len(case_insensitive_duplicates),
                "ExactDuplicates": len(exact_duplicates),
                "DetailedAnalysis": detailed_analysis
            }
            
            LoggingService.LogInfo(f"MediaFiles duplicate analysis complete: {total_duplicates} groups, {total_records_to_delete} records to delete", "SQLDataReader", "AnalyzeMediaFilesDuplicates")
            return analysis_result
            
        except Exception as e:
            LoggingService.LogException("Error analyzing MediaFiles duplicates", e, "SQLDataReader", "AnalyzeMediaFilesDuplicates")
            return {"Error": str(e)}
    
    def PrintDuplicateAnalysis(self, Analysis: Dict[str, Any]):
        """
        Print detailed duplicate analysis results.
        
        Args:
            Analysis: Results from AnalyzeMediaFilesDuplicates
        """
        if "Error" in Analysis:
            print(f"\nError in analysis: {Analysis['Error']}")
            return
        
        summary = Analysis.get("Summary", {})
        print(f"\n=== MEDIAFILES DUPLICATE ANALYSIS ===")
        print(f"Total Duplicate Groups: {summary.get('TotalDuplicateGroups', 0)}")
        print(f"Total Records to Delete: {summary.get('TotalRecordsToDelete', 0)}")
        print(f"Safe to Delete: {summary.get('SafeToDelete', 0)}")
        print(f"Need Archive Check: {summary.get('NeedsArchiveCheck', 0)}")
        print(f"Case-Insensitive Duplicates: {Analysis.get('CaseInsensitiveDuplicates', 0)}")
        print(f"Exact Duplicates: {Analysis.get('ExactDuplicates', 0)}")
        
        detailed_analysis = Analysis.get("DetailedAnalysis", [])
        if detailed_analysis:
            print(f"\n=== DETAILED DUPLICATE GROUPS ===")
            
            for i, group in enumerate(detailed_analysis, 1):
                print(f"\n--- Group {i}: {group['Type']} Duplicate ---")
                
                if group["Type"] == "Case-Insensitive":
                    print(f"Lower Path: {group['LowerPath']}")
                else:
                    print(f"Exact Path: {group['FilePath']}")
                
                print(f"Count: {group['Count']}")
                print(f"Keep Record ID: {group['KeepRecord']['Id']} ({group['KeepReason']})")
                print(f"Delete Record IDs: {[r['Id'] for r in group['DeleteRecords']]}")
                print(f"Safe to Delete: {group['SafeToDelete']}")
                
                if group["ArchiveCheck"]:
                    print("Archive Status:")
                    for check in group["ArchiveCheck"]:
                        status = "✓" if check["InArchive"] else "✗"
                        print(f"  {status} {check['FilePath']}")
                
                if group.get("DiskVerification"):
                    print("Disk Verification:")
                    for disk_check in group["DiskVerification"]:
                        exists_status = "✓" if disk_check["DiskExists"] else "✗"
                        size_status = "✓" if disk_check["SizeMatch"] else "✗"
                        print(f"  {exists_status} {disk_check['FilePath']}")
                        if disk_check["DiskExists"]:
                            print(f"    DB Size: {disk_check['DatabaseSizeMB']}MB, Disk Size: {disk_check['DiskSizeMB']}MB, Match: {size_status}")
                        else:
                            print(f"    Error: {disk_check['Error']}")
                
                print("\nAll Records in Group:")
                for record in group["AllRecords"]:
                    transcoded_marker = " [TRANSCODED]" if record.get("TranscodedByMediaVortex", False) else ""
                    print(f"  ID {record['Id']}: {record['FilePath']}{transcoded_marker}")
                    print(f"    LastScanned: {record.get('LastScannedDate', 'N/A')}")
                    print(f"    Size: {record.get('SizeMB', 'N/A')}MB, Codec: {record.get('Codec', 'N/A')}, Resolution: {record.get('Resolution', 'N/A')}")
    
    def ShowUsageExamples(self):
        """Display usage examples for the SQLDataReader tool."""
        examples = """
=== SQLDataReader Usage Examples ===

1. List all available tables:
   py SQLDataReader.py --list-tables

2. Show schema for a specific table:
   py SQLDataReader.py --schema MediaFiles

3. Query a specific table with basic filters:
   py SQLDataReader.py --table MediaFiles --limit 10
   py SQLDataReader.py --table TranscodeQueue --filter Status "Pending" --limit 5

4. Query with ordering:
   py SQLDataReader.py --table MediaFiles --order-by SizeMB --order DESC --limit 20

5. Multiple filters:
   py SQLDataReader.py --table MediaFiles --filter Resolution "1080p" --filter Codec "H.264" --limit 10

6. Log-specific queries (backward compatibility):
   py SQLDataReader.py --level ERROR --limit 20
   py SQLDataReader.py --service "TranscodeService" --level WARNING
   py SQLDataReader.py --summary --hours 48

7. Show recent errors:
   py SQLDataReader.py --recent-errors --limit 10

8. Query specific service errors:
   py SQLDataReader.py --service-errors "QualityTestService" --hours 12

9. Find case-insensitive duplicates:
   py SQLDataReader.py --find-duplicates MediaFiles FilePath

10. Find exact duplicates:
    py SQLDataReader.py --find-exact-duplicates MediaFiles FilePath

11. Analyze MediaFiles duplicates (comprehensive):
    py SQLDataReader.py --analyze-mediafiles-duplicates

=== Common Tables to Explore ===
- MediaFiles: All scanned media files
- TranscodeQueue: Files waiting to be transcoded
- TranscodeAttempts: History of transcoding attempts
- QualityTestResults: Quality test results
- Logs: System logs
- Profiles: Transcoding profiles
- ProfileThresholds: Quality thresholds for profiles
- ServiceStatus: Status of all services
- SystemSettings: System configuration
- RootFolders: Monitored root folders
"""
        print(examples)


def main():
    """Main entry point for SQLDataReader script."""
    parser = argparse.ArgumentParser(description="MediaVortex Database Data Reader")
    
    # General table operations
    parser.add_argument("--table", help="Table name to query")
    parser.add_argument("--list-tables", action="store_true", help="List all available tables")
    parser.add_argument("--schema", help="Show schema for specified table")
    parser.add_argument("--limit", type=int, default=100, help="Maximum number of records")
    parser.add_argument("--order-by", help="Column name to order by")
    parser.add_argument("--order", choices=["ASC", "DESC"], default="ASC", help="Sort order")
    parser.add_argument("--no-details", action="store_true", help="Hide detailed content")
    parser.add_argument("--examples", action="store_true", help="Show usage examples")
    
    # Filter options (generic)
    parser.add_argument("--filter", action="append", nargs=2, metavar=("COLUMN", "VALUE"), 
                       help="Add column filter (can be used multiple times)")
    
    # Log-specific options (backward compatibility)
    parser.add_argument("--level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], 
                       help="Filter by log level (Logs table only)")
    parser.add_argument("--function", help="Filter by function name (Logs table only)")
    parser.add_argument("--service", help="Filter by service name (Logs table only)")
    parser.add_argument("--start-date", help="Start date filter (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="End date filter (YYYY-MM-DD)")
    parser.add_argument("--message", help="Filter by message content (Logs table only)")
    parser.add_argument("--summary", action="store_true", help="Show error summary (Logs table only)")
    parser.add_argument("--hours", type=int, default=24, help="Hours to look back for summary")
    parser.add_argument("--recent-errors", action="store_true", help="Show recent errors only (Logs table only)")
    parser.add_argument("--service-errors", help="Show errors for specific service (Logs table only)")
    
    # Duplicate detection options
    parser.add_argument("--find-duplicates", nargs=2, metavar=("TABLE", "COLUMN"), 
                       help="Find case-insensitive duplicates in specified table and column")
    parser.add_argument("--find-exact-duplicates", nargs=2, metavar=("TABLE", "COLUMN"), 
                       help="Find exact duplicates in specified table and column")
    parser.add_argument("--analyze-mediafiles-duplicates", action="store_true", 
                       help="Run comprehensive MediaFiles duplicate analysis")
    
    args = parser.parse_args()
    
    try:
        reader = SQLDataReader()
        
        if args.examples:
            # Show usage examples
            reader.ShowUsageExamples()
            return
        
        if args.list_tables:
            # List all available tables
            tables = reader.GetAvailableTables()
            print("\n=== Available Tables ===")
            for table in tables:
                print(f"  {table}")
            return
        
        if args.schema:
            # Show table schema
            schema = reader.GetTableSchema(args.schema)
            if schema:
                print(f"\n=== Schema for {args.schema} ===")
                for column in schema:
                    pk_marker = " (PRIMARY KEY)" if column["PrimaryKey"] else ""
                    not_null_marker = " NOT NULL" if column["NotNull"] else ""
                    default_marker = f" DEFAULT {column['DefaultValue']}" if column["DefaultValue"] else ""
                    print(f"  {column['ColumnName']}: {column['DataType']}{pk_marker}{not_null_marker}{default_marker}")
            else:
                print(f"Table '{args.schema}' not found or no schema available.")
            return
        
        if args.summary:
            # Show error summary (Logs table only)
            summary = reader.GetErrorSummary(args.service, args.hours)
            print("\n=== ERROR SUMMARY ===")
            print(f"Time Period: {summary.get('TimePeriod', 'Unknown')}")
            print(f"Service Filter: {summary.get('ServiceFilter', 'All Services')}")
            print(f"Total Errors: {summary.get('TotalErrors', 0)}")
            print(f"Total Warnings: {summary.get('TotalWarnings', 0)}")
            
            if summary.get("ErrorBreakdown"):
                print("\nError Breakdown:")
                for error in summary["ErrorBreakdown"]:
                    print(f"  {error['LogLevel']} - {error['Component']} - {error['FunctionName']}: {error['Count']} occurrences")
            
            if summary.get("TotalCounts"):
                print("\nTotal Counts by Level:")
                for level, count in summary["TotalCounts"].items():
                    print(f"  {level}: {count}")
        
        elif args.recent_errors:
            # Show recent errors (Logs table only)
            errors = reader.GetRecentErrors(args.service, args.limit)
            reader.PrintLogs(errors, not args.no_details)
        
        elif args.service_errors:
            # Show errors for specific service (Logs table only)
            errors = reader.GetServiceErrors(args.service_errors, args.hours)
            reader.PrintLogs(errors, not args.no_details)
        
        elif args.analyze_mediafiles_duplicates:
            # Run comprehensive MediaFiles duplicate analysis
            analysis = reader.AnalyzeMediaFilesDuplicates()
            reader.PrintDuplicateAnalysis(analysis)
        
        elif args.find_duplicates:
            # Find case-insensitive duplicates
            table_name, column_name = args.find_duplicates
            duplicates = reader.FindCaseInsensitiveDuplicates(table_name, column_name)
            if duplicates:
                print(f"\n=== CASE-INSENSITIVE DUPLICATES IN {table_name.upper()}.{column_name.upper()} ===")
                for i, duplicate in enumerate(duplicates, 1):
                    print(f"\nGroup {i}:")
                    print(f"  Lower Value: {duplicate['LowerValue']}")
                    print(f"  Count: {duplicate['Count']}")
                    print(f"  IDs: {duplicate['Ids']}")
                    print(f"  Original Values: {duplicate['OriginalValues']}")
            else:
                print(f"No case-insensitive duplicates found in {table_name}.{column_name}")
        
        elif args.find_exact_duplicates:
            # Find exact duplicates
            table_name, column_name = args.find_exact_duplicates
            duplicates = reader.FindExactDuplicates(table_name, column_name)
            if duplicates:
                print(f"\n=== EXACT DUPLICATES IN {table_name.upper()}.{column_name.upper()} ===")
                for i, duplicate in enumerate(duplicates, 1):
                    print(f"\nGroup {i}:")
                    print(f"  Value: {duplicate['Value']}")
                    print(f"  Count: {duplicate['Count']}")
                    print(f"  IDs: {duplicate['Ids']}")
            else:
                print(f"No exact duplicates found in {table_name}.{column_name}")
        
        elif args.table:
            # Query specific table
            filters = {}
            
            # Add generic filters
            if args.filter:
                for column, value in args.filter:
                    filters[column] = value
            
            # Add log-specific filters if table is Logs
            if args.table == "Logs":
                if args.level:
                    filters["LogLevel"] = args.level
                if args.function:
                    filters["FunctionName"] = f"%{args.function}%"
                if args.service:
                    filters["Component"] = args.service
                if args.start_date:
                    filters["Timestamp"] = f"{args.start_date} 00:00:00"
                if args.message:
                    filters["Message"] = f"%{args.message}%"
            
            data = reader.ReadTableData(
                TableName=args.table,
                Filters=filters,
                Limit=args.limit,
                OrderBy=args.order_by,
                OrderDirection=args.order
            )
            reader.PrintTableData(data, args.table, not args.no_details)
        
        else:
            # Default: show recent logs (backward compatibility)
            logs = reader.ReadLogs(
                LogLevel=args.level,
                FunctionName=args.function,
                Component=args.service,
                StartDate=args.start_date,
                EndDate=args.end_date,
                Limit=args.limit,
                OrderBy=args.order,
                Message=args.message
            )
            reader.PrintLogs(logs, not args.no_details)
    
    except Exception as e:
        print(f"Error running SQLDataReader: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
