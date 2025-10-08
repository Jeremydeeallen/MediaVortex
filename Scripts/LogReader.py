"""
LogReader.py - Database Log Analysis Tool
Reads and analyzes logs from the MediaVortex database log table.
"""

import sys
import os
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# Add parent directory to path to import shared services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


class LogReader:
    """Database log reader and analyzer."""
    
    def __init__(self):
        """Initialize the log reader."""
        self.DatabaseManager = DatabaseManager()
    
    def ReadLogs(self, LogLevel: str = None, FunctionName: str = None, 
                 Component: str = None, StartDate: str = None, 
                 EndDate: str = None, Limit: int = 100, 
                 OrderBy: str = "DESC", Message: str = None) -> List[Dict[str, Any]]:
        """
        Read logs from database with optional filters.
        
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
        try:
            # Build query with filters
            query = "SELECT * FROM Logs WHERE 1=1"
            params = []
            
            if LogLevel:
                query += " AND LogLevel = ?"
                params.append(LogLevel)
            
            if FunctionName:
                query += " AND FunctionName LIKE ?"
                params.append(f"%{FunctionName}%")
            
            if Component:
                query += " AND Component = ?"
                params.append(Component)
            
            if StartDate:
                query += " AND Timestamp >= ?"
                params.append(f"{StartDate} 00:00:00")
            
            if EndDate:
                query += " AND Timestamp <= ?"
                params.append(f"{EndDate} 23:59:59")
            
            if Message:
                query += " AND Message LIKE ?"
                params.append(f"%{Message}%")
            
            # Add ordering and limit
            query += f" ORDER BY Timestamp {OrderBy}"
            query += f" LIMIT {Limit}"
            
            # Execute query
            results = self.DatabaseManager.DatabaseService.ExecuteQuery(query, params)
            
            if results:
                # Convert sqlite3.Row objects to dictionaries
                dict_results = [dict(row) for row in results]
                LoggingService.LogInfo(f"Retrieved {len(dict_results)} log records", "LogReader", "ReadLogs")
                return dict_results
            else:
                LoggingService.LogInfo("No log records found", "LogReader", "ReadLogs")
                return []
                
        except Exception as e:
            LoggingService.LogException("Error reading logs from database", e, "LogReader", "ReadLogs")
            return []
    
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
    
    def PrintLogs(self, Logs: List[Dict[str, Any]], ShowDetails: bool = True):
        """
        Print logs in a formatted way.
        
        Args:
            Logs: List of log records
            ShowDetails: Whether to show detailed information
        """
        if not Logs:
            print("No logs found.")
            return
        
        print(f"\n=== Found {len(Logs)} log entries ===")
        print("-" * 80)
        
        for log in Logs:
            # Format timestamp
            timestamp = log.get("Timestamp", "Unknown")
            if isinstance(timestamp, str):
                try:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    pass
            
            # Color coding for log levels
            level = log.get("LogLevel", "UNKNOWN")
            level_colors = {
                "DEBUG": "\033[36m",    # Cyan
                "INFO": "\033[32m",     # Green
                "WARNING": "\033[33m",  # Yellow
                "ERROR": "\033[31m",    # Red
                "CRITICAL": "\033[35m"  # Magenta
            }
            color = level_colors.get(level, "")
            reset_color = "\033[0m"
            
            print(f"{color}[{level}]{reset_color} {timestamp}")
            print(f"  Service: {log.get('Component', 'Unknown')}")
            print(f"  Function: {log.get('FunctionName', 'Unknown')}")
            
            if ShowDetails:
                message = log.get("Message", "")
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
                
                exception = log.get("Exception", "")
                if exception:
                    print(f"  Exception: {exception}")
            
            print("-" * 80)


def main():
    """Main entry point for LogReader script."""
    parser = argparse.ArgumentParser(description="MediaVortex Log Reader")
    parser.add_argument("--level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], 
                       help="Filter by log level")
    parser.add_argument("--function", help="Filter by function name (partial match)")
    parser.add_argument("--service", help="Filter by service name")
    parser.add_argument("--start-date", help="Start date filter (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="End date filter (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=100, help="Maximum number of records")
    parser.add_argument("--order", choices=["ASC", "DESC"], default="DESC", help="Sort order")
    parser.add_argument("--message", help="Filter by message content (partial match)")
    parser.add_argument("--summary", action="store_true", help="Show error summary")
    parser.add_argument("--hours", type=int, default=24, help="Hours to look back for summary")
    parser.add_argument("--recent-errors", action="store_true", help="Show recent errors only")
    parser.add_argument("--service-errors", help="Show errors for specific service")
    parser.add_argument("--no-details", action="store_true", help="Hide detailed message content")
    
    args = parser.parse_args()
    
    try:
        reader = LogReader()
        
        if args.summary:
            # Show error summary
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
            # Show recent errors
            errors = reader.GetRecentErrors(args.service, args.limit)
            reader.PrintLogs(errors, not args.no_details)
        
        elif args.service_errors:
            # Show errors for specific service
            errors = reader.GetServiceErrors(args.service_errors, args.hours)
            reader.PrintLogs(errors, not args.no_details)
        
        else:
            # Show filtered logs
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
        print(f"Error running LogReader: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
