from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from Services.DatabaseService import DatabaseService
from Services.LoggingService import LoggingService
from Core.Database.DatabaseService import EscapeLikePattern


class JellyfinRepository:
    def __init__(self, DatabaseServiceInstance: Optional[DatabaseService] = None):
        self.DatabaseService = DatabaseServiceInstance or DatabaseService()


    def ClearJellyfinOperations(self):
        """Delete all JellyfinOperations records to force full re-import."""
        try:
            self.DatabaseService.ExecuteNonQuery("DELETE FROM JellyfinOperations")
        except Exception as e:
            LoggingService.LogException("Error clearing Jellyfin operations", e, "DatabaseManager", "ClearJellyfinOperations")

    def GetExistingLogFileNames(self) -> set:
        """Get set of all LogFileName values already in the database."""
        try:
            rows = self.DatabaseService.ExecuteQuery("SELECT LogFileName FROM JellyfinOperations")
            return {row['logfilename'] for row in rows}
        except Exception as e:
            LoggingService.LogException("Error getting existing log filenames", e, "DatabaseManager", "GetExistingLogFileNames")
            return set()

    def GetJellyfinOperationCounts(self) -> Dict[str, Any]:
        """Get distinct file count and total log count per operation type, with date range."""
        try:
            query = """
                SELECT OperationType,
                       COUNT(*) as TotalLogs,
                       COUNT(DISTINCT FileName) as DistinctFiles,
                       MIN(LogDate) as OldestDate,
                       MAX(LogDate) as NewestDate
                FROM JellyfinOperations
                GROUP BY OperationType
            """
            rows = self.DatabaseService.ExecuteQuery(query)
            result = {}
            allOldest = []
            allNewest = []
            for row in rows:
                result[row['operationtype']] = {"Distinct": row['distinctfiles'], "Total": row['totallogs']}
                if row['oldestdate']:
                    allOldest.append(row['oldestdate'])
                if row['newestdate']:
                    allNewest.append(row['newestdate'])
            return {
                "Success": True,
                "Counts": result,
                "OldestDate": min(allOldest) if allOldest else None,
                "NewestDate": max(allNewest) if allNewest else None,
                "TotalRecords": sum(r["Total"] for r in result.values())
            }
        except Exception as e:
            LoggingService.LogException("Error getting Jellyfin operation counts", e, "DatabaseManager", "GetJellyfinOperationCounts")
            return {"Success": False, "ErrorMessage": str(e)}

    def GetJellyfinOperationsByType(self, OperationType: str, Limit: int = 100) -> Dict[str, Any]:
        """Get operation details from local DB, grouped by file with play counts."""
        try:
            query = """
                SELECT FileName, FilePath, VideoCodec, AudioCodec, Container, Resolution, Reason,
                       COUNT(*) as PlayCount,
                       MIN(LogDate) as FirstSeen,
                       MAX(LogDate) as LastSeen,
                       SubtitleCodecs,
                       TranscodeActions
                FROM JellyfinOperations
                WHERE OperationType = %s
                GROUP BY FileName, FilePath, VideoCodec, AudioCodec, Container, Resolution, Reason,
                         SubtitleCodecs, TranscodeActions
                ORDER BY LastSeen DESC
                LIMIT %s
            """
            rows = self.DatabaseService.ExecuteQuery(query, (OperationType, Limit))
            files = []
            reasons = {}
            for row in rows:
                reason = row['reason'] or "other"
                files.append({
                    "FileName": row['filename'],
                    "FilePath": row['filepath'],
                    "VideoCodec": row['videocodec'],
                    "AudioCodec": row['audiocodec'],
                    "Container": row['container'],
                    "Resolution": row['resolution'],
                    "Reason": reason,
                    "Count": row['playcount'],
                    "FirstSeen": row['firstseen'],
                    "LastSeen": row['lastseen'],
                    "SubtitleCodecs": row['subtitlecodecs'] or "",
                    "TranscodeActions": row['transcodeactions'] or ""
                })
                if OperationType == "Transcode":
                    reasons[reason] = reasons.get(reason, 0) + row['playcount']

            totalQuery = "SELECT COUNT(*) FROM JellyfinOperations WHERE OperationType = %s"
            totalRow = self.DatabaseService.ExecuteQuery(totalQuery, (OperationType,))
            totalLogs = totalRow[0]['count'] if totalRow else 0

            dateQuery = "SELECT MIN(LogDate), MAX(LogDate) FROM JellyfinOperations WHERE OperationType = %s"
            dateRow = self.DatabaseService.ExecuteQuery(dateQuery, (OperationType,))

            return {
                "Success": True,
                "Files": files,
                "Count": len(files),
                "TotalLogs": totalLogs,
                "OperationType": OperationType,
                "Reasons": reasons,
                "OldestDate": dateRow[0]['min'] if dateRow else None,
                "NewestDate": dateRow[0]['max'] if dateRow else None
            }
        except Exception as e:
            LoggingService.LogException("Error getting Jellyfin operations by type", e, "DatabaseManager", "GetJellyfinOperationsByType")
            return {"Success": False, "ErrorMessage": str(e)}

    def GetStaleJellyfinRecordCount(self) -> int:
        """Count transcode records missing destination format data (need re-import)."""
        try:
            rows = self.DatabaseService.ExecuteQuery("""
                SELECT COUNT(*) FROM JellyfinOperations
                WHERE OperationType = 'Transcode'
                  AND (DestResolution IS NULL OR DestResolution = '')
                  AND (DestProfile IS NULL OR DestProfile = '')
                  AND (DestLevel IS NULL OR DestLevel = '')
            """)
            return rows[0]['count'] if rows else 0
        except Exception as e:
            LoggingService.LogException("Error checking stale records", e, "DatabaseManager", "GetStaleJellyfinRecordCount")
            return 0

    def InsertJellyfinOperation(self, LogFileName: str, OperationType: str, FilePath: str,
                                 FileName: str, VideoCodec: str, AudioCodec: str,
                                 Container: str, Resolution: str, SubtitleCodecs: str,
                                 Reason: str, TranscodeActions: str, LogDate: str) -> bool:
        """Insert a Jellyfin FFmpeg operation log entry. Skips if LogFileName already exists."""
        try:
            query = """
                INSERT INTO JellyfinOperations
                (LogFileName, OperationType, FilePath, FileName, VideoCodec, AudioCodec, Container, Resolution,
                 SubtitleCodecs, Reason, TranscodeActions, LogDate,
                 DestResolution, DestProfile, DestLevel, DestPixelFormat, DestFormat)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (LogFileName) DO NOTHING
            """
            self.DatabaseService.ExecuteNonQuery(query, (
                LogFileName, OperationType, FilePath, FileName,
                VideoCodec, AudioCodec, Container, Resolution, SubtitleCodecs, Reason, TranscodeActions, LogDate,
                "", "", "", "", ""
            ))
            return True
        except Exception as e:
            LoggingService.LogException("Error inserting Jellyfin operation", e, "DatabaseManager", "InsertJellyfinOperation")
            return False

    def InsertJellyfinOperationsBatch(self, Entries: list) -> int:
        """Batch insert Jellyfin operations. Returns count of new rows inserted."""
        try:
            query = """
                INSERT INTO JellyfinOperations
                (LogFileName, OperationType, FilePath, FileName, VideoCodec, AudioCodec, Container, Resolution,
                 SubtitleCodecs, Reason, TranscodeActions, LogDate,
                 DestResolution, DestProfile, DestLevel, DestPixelFormat, DestFormat)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (LogFileName) DO NOTHING
            """
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                cursor.execute("SELECT COUNT(*) FROM JellyfinOperations")
                beforeCount = cursor.fetchone()[0]
                cursor.executemany(query, [
                    (e["LogFileName"], e["OperationType"], e["FilePath"], e["FileName"],
                     e["VideoCodec"], e["AudioCodec"], e["Container"], e["Resolution"],
                     e.get("SubtitleCodecs", ""), e["Reason"], e.get("TranscodeActions", ""), e["LogDate"],
                     e.get("DestResolution", ""), e.get("DestProfile", ""), e.get("DestLevel", ""),
                     e.get("DestPixelFormat", ""), e.get("DestFormat", ""))
                    for e in Entries
                ])
                connection.commit()
                cursor.execute("SELECT COUNT(*) FROM JellyfinOperations")
                afterCount = cursor.fetchone()[0]
                return afterCount - beforeCount
            finally:
                self.DatabaseService.CloseConnection(connection)
        except Exception as e:
            LoggingService.LogException("Error batch inserting Jellyfin operations", e, "DatabaseManager", "InsertJellyfinOperationsBatch")
            return 0
