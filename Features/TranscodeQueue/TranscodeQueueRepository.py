#!/usr/bin/env python3
"""TranscodeQueueRepository.py - Repository for transcode queue data access"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService
from Features.TranscodeQueue.Models.TranscodeQueueModel import TranscodeQueueModel


class TranscodeQueueRepository(BaseRepository):
    """Repository for transcode queue CRUD operations."""

    def _MapRowToQueueItem(self, row) -> TranscodeQueueModel:
        """Map a database row to a TranscodeQueueModel."""
        return TranscodeQueueModel(
            Id=row['Id'],
            FilePath=row['FilePath'],
            FileName=row['FileName'],
            Directory=row['Directory'],
            SizeBytes=row['SizeBytes'],
            SizeMB=row['SizeMB'],
            Priority=row['Priority'],
            Status=row['Status'],
            DateAdded=self.ConvertStringToDateTime(row['DateAdded']) if row.get('DateAdded') else None,
            DateStarted=self.ConvertStringToDateTime(row['DateStarted']) if row.get('DateStarted') else None,
            ProcessingMode=row.get('ProcessingMode') or 'Transcode'
        )

    def ConvertStringToDateTime(self, DateString) -> Optional[datetime]:
        """Convert date string from database to datetime object. Pass through if already datetime."""
        if not DateString:
            return None
        if isinstance(DateString, datetime):
            return DateString
        try:
            if 'T' in DateString:
                return datetime.fromisoformat(DateString.replace('Z', '+00:00'))
            else:
                return datetime.strptime(DateString, '%Y-%m-%d %H:%M:%S.%f')
        except (ValueError, AttributeError):
            try:
                return datetime.strptime(DateString, '%Y-%m-%d %H:%M:%S')
            except (ValueError, AttributeError):
                LoggingService.LogWarning(f"Failed to convert date string to datetime: {DateString}", "TranscodeQueueRepository", "ConvertStringToDateTime")
                return None

    _QUEUE_SELECT_COLS = """Id, FilePath, FileName, Directory, SizeBytes, SizeMB, Priority, Status, DateAdded, DateStarted, ProcessingMode"""

    def GetAllTranscodeQueueItems(self) -> List[TranscodeQueueModel]:
        """Get all transcoding queue items."""
        query = f"SELECT {self._QUEUE_SELECT_COLS} FROM TranscodeQueue ORDER BY Priority DESC, DateAdded ASC"
        rows = self.ExecuteQuery(query)
        return [self._MapRowToQueueItem(row) for row in rows]

    def GetTranscodeQueueItemById(self, ItemId: int) -> Optional[TranscodeQueueModel]:
        """Get a specific transcoding queue item by ID."""
        query = f"SELECT {self._QUEUE_SELECT_COLS} FROM TranscodeQueue WHERE Id = %s"
        rows = self.ExecuteQuery(query, (ItemId,))
        if not rows:
            return None
        return self._MapRowToQueueItem(rows[0])

    def SaveTranscodeQueueItem(self, QueueItem: TranscodeQueueModel) -> int:
        """Save a transcoding queue item (insert or update) and return the item ID."""
        try:
            LoggingService.LogFunctionEntry("SaveTranscodeQueueItem", "TranscodeQueueRepository", QueueItem.Id, QueueItem.FilePath, QueueItem.Status)
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                if QueueItem.Id is None:
                    LoggingService.LogInfo("Inserting new transcoding queue item...", "TranscodeQueueRepository", "SaveTranscodeQueueItem")
                    query = """
                        INSERT INTO TranscodeQueue
                        (FilePath, FileName, Directory, SizeBytes, SizeMB, Priority, Status, DateAdded, DateStarted, ProcessingMode)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING Id
                    """
                    parameters = (
                        QueueItem.FilePath, QueueItem.FileName, QueueItem.Directory,
                        QueueItem.SizeBytes, QueueItem.SizeMB, QueueItem.Priority,
                        QueueItem.Status, QueueItem.DateAdded, QueueItem.DateStarted,
                        QueueItem.ProcessingMode
                    )
                    cursor.execute(query, parameters)
                    itemId = cursor.fetchone()[0]
                    connection.commit()
                    LoggingService.LogInfo(f"Queue item inserted with ID: {itemId}", "TranscodeQueueRepository", "SaveTranscodeQueueItem")
                    return itemId
                else:
                    LoggingService.LogInfo(f"Updating existing queue item with ID: {QueueItem.Id}", "TranscodeQueueRepository", "SaveTranscodeQueueItem")
                    query = """
                        UPDATE TranscodeQueue
                        SET FilePath = %s, FileName = %s, Directory = %s, SizeBytes = %s, SizeMB = %s,
                            Priority = %s, Status = %s, DateAdded = %s, DateStarted = %s, ProcessingMode = %s
                        WHERE Id = %s
                    """
                    parameters = (
                        QueueItem.FilePath, QueueItem.FileName, QueueItem.Directory,
                        QueueItem.SizeBytes, QueueItem.SizeMB, QueueItem.Priority,
                        QueueItem.Status, QueueItem.DateAdded, QueueItem.DateStarted,
                        QueueItem.ProcessingMode, QueueItem.Id
                    )
                    cursor.execute(query, parameters)
                    connection.commit()
                    return QueueItem.Id
            finally:
                self.DatabaseService.CloseConnection(connection)
        except Exception as e:
            LoggingService.LogException("Exception in SaveTranscodeQueueItem", e, "TranscodeQueueRepository", "SaveTranscodeQueueItem")
            raise

    def DeleteTranscodeQueueItem(self, ItemId: int) -> bool:
        """Delete a transcoding queue item."""
        affectedRows = self.ExecuteNonQuery("DELETE FROM TranscodeQueue WHERE Id = %s", (ItemId,))
        return affectedRows > 0

    def UpdateTranscodeQueueStatus(self, JobId: int, Status: str) -> bool:
        """Update the status of a transcoding queue item."""
        try:
            LoggingService.LogFunctionEntry("UpdateTranscodeQueueStatus", "TranscodeQueueRepository", JobId, Status)
            if Status == "Running":
                query = "UPDATE TranscodeQueue SET Status = %s, DateStarted = CURRENT_TIMESTAMP WHERE Id = %s"
            else:
                query = "UPDATE TranscodeQueue SET Status = %s WHERE Id = %s"
            affectedRows = self.ExecuteNonQuery(query, (Status, JobId))
            LoggingService.LogInfo(f"Updated transcoding queue item {JobId} status to {Status}", "TranscodeQueueRepository", "UpdateTranscodeQueueStatus")
            return affectedRows > 0
        except Exception as e:
            LoggingService.LogException("Exception updating transcoding queue status", e, "TranscodeQueueRepository", "UpdateTranscodeQueueStatus")
            return False

    def GetTranscodeQueueItemsByStatus(self, Status: str) -> List[TranscodeQueueModel]:
        """Get all transcoding queue items with a specific status."""
        query = f"SELECT {self._QUEUE_SELECT_COLS} FROM TranscodeQueue WHERE Status = %s ORDER BY Priority DESC, DateAdded ASC"
        rows = self.ExecuteQuery(query, (Status,))
        return [self._MapRowToQueueItem(row) for row in rows]

    def GetNextPendingTranscodeJob(self) -> Optional[TranscodeQueueModel]:
        """Get the next pending transcoding job (largest files first)."""
        query = f"SELECT {self._QUEUE_SELECT_COLS} FROM TranscodeQueue WHERE Status = 'Pending' ORDER BY SizeMB DESC, DateAdded ASC LIMIT 1"
        rows = self.ExecuteQuery(query)
        if rows:
            return self._MapRowToQueueItem(rows[0])
        return None

    def ClaimNextPendingTranscodeJob(self, WorkerName: str) -> Optional[TranscodeQueueModel]:
        """Atomically claim the next pending job using SELECT FOR UPDATE SKIP LOCKED.
        This prevents race conditions when multiple workers compete for jobs."""
        try:
            import psycopg2.extras
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                query = f"""
                    UPDATE TranscodeQueue
                    SET Status = 'Running', ClaimedBy = %s, ClaimedAt = NOW(), DateStarted = NOW()
                    WHERE Id = (
                        SELECT Id FROM TranscodeQueue
                        WHERE Status = 'Pending'
                        ORDER BY SizeMB DESC, DateAdded ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    RETURNING {self._QUEUE_SELECT_COLS}
                """
                cursor.execute(query, (WorkerName,))
                row = cursor.fetchone()
                connection.commit()

                if row:
                    return self._MapRowToQueueItem(row)
                return None
            finally:
                self.DatabaseService.CloseConnection(connection)
        except Exception as e:
            LoggingService.LogException("Exception in ClaimNextPendingTranscodeJob", e, "TranscodeQueueRepository", "ClaimNextPendingTranscodeJob")
            return None

    def ClearAllTranscodeQueueItems(self) -> int:
        """Clear pending items from the transcoding queue, preserving in-progress jobs."""
        try:
            LoggingService.LogFunctionEntry("ClearAllTranscodeQueueItems", "TranscodeQueueRepository")
            countQuery = "SELECT COUNT(*) as Count FROM TranscodeQueue WHERE Status != 'Running'"
            countResult = self.ExecuteQuery(countQuery)
            itemsToDelete = countResult[0]['Count'] if countResult else 0
            if itemsToDelete > 0:
                affectedRows = self.ExecuteNonQuery("DELETE FROM TranscodeQueue WHERE Status != 'Running'")
                LoggingService.LogInfo(f"Cleared {affectedRows} items from TranscodeQueue (preserved running jobs)", "TranscodeQueueRepository", "ClearAllTranscodeQueueItems")
                return affectedRows
            else:
                LoggingService.LogInfo("No items found in TranscodeQueue to clear", "TranscodeQueueRepository", "ClearAllTranscodeQueueItems")
                return 0
        except Exception as e:
            LoggingService.LogException("Exception clearing all transcoding queue items", e, "TranscodeQueueRepository", "ClearAllTranscodeQueueItems")
            return 0

    def GetQueueStatistics(self) -> Dict[str, Any]:
        """Get current queue statistics."""
        try:
            LoggingService.LogFunctionEntry("GetQueueStatistics", "TranscodeQueueRepository")
            query = "SELECT Status, COUNT(*) as Count FROM TranscodeQueue GROUP BY Status"
            rows = self.ExecuteQuery(query)
            totalJobs = 0
            pendingJobs = 0
            runningJobs = 0
            completedJobs = 0
            failedJobs = 0
            cancelledJobs = 0
            for row in rows:
                status = row['Status']
                count = row['Count']
                totalJobs += count
                if status == "Pending":
                    pendingJobs = count
                elif status == "Running":
                    runningJobs = count
                elif status == "Completed":
                    completedJobs = count
                elif status == "Failed":
                    failedJobs = count
                elif status == "Cancelled":
                    cancelledJobs = count
            activeJobsQuery = "SELECT Id FROM TranscodeQueue WHERE Status = 'Running' ORDER BY Priority DESC, DateAdded ASC"
            activeJobRows = self.ExecuteQuery(activeJobsQuery)
            activeJobs = [row['Id'] for row in activeJobRows]
            nextJobQuery = "SELECT Id FROM TranscodeQueue WHERE Status = 'Pending' ORDER BY Priority DESC, DateAdded ASC LIMIT 1"
            nextJobRows = self.ExecuteQuery(nextJobQuery)
            nextJobId = nextJobRows[0]['Id'] if nextJobRows else None
            statistics = {
                'TotalJobs': totalJobs,
                'PendingJobs': pendingJobs,
                'RunningJobs': runningJobs,
                'CompletedJobs': completedJobs,
                'FailedJobs': failedJobs,
                'CancelledJobs': cancelledJobs,
                'QueueSize': pendingJobs + runningJobs,
                'ActiveJobs': activeJobs,
                'NextJobId': nextJobId
            }
            if totalJobs > 0:
                statistics['SuccessRate'] = (completedJobs / totalJobs) * 100.0
                statistics['FailureRate'] = (failedJobs / totalJobs) * 100.0
            else:
                statistics['SuccessRate'] = 0.0
                statistics['FailureRate'] = 0.0
            return statistics
        except Exception as e:
            LoggingService.LogException("Exception in GetQueueStatistics", e, "TranscodeQueueRepository", "GetQueueStatistics")
            return {}

    def ResetQueueJobsToPending(self, QueueIds: List[int], QueueTable: str = 'TranscodeQueue') -> int:
        """Reset multiple queue jobs to Pending status."""
        try:
            LoggingService.LogFunctionEntry("ResetQueueJobsToPending", "TranscodeQueueRepository", QueueIds, QueueTable)
            if not QueueIds:
                return 0
            valid_tables = ['TranscodeQueue', 'QualityTestingQueue']
            if QueueTable not in valid_tables:
                LoggingService.LogError(f"Invalid queue table name: {QueueTable}", "TranscodeQueueRepository", "ResetQueueJobsToPending")
                return 0
            placeholders = ','.join(['%s'] * len(QueueIds))
            if QueueTable == 'TranscodeQueue':
                query = f"UPDATE {QueueTable} SET Status = 'Pending', DateStarted = NULL WHERE Id IN ({placeholders})"
            else:
                query = f"UPDATE {QueueTable} SET DateStarted = NULL, DateCompleted = NULL WHERE Id IN ({placeholders})"
            affected_rows = self.ExecuteNonQuery(query, QueueIds)
            LoggingService.LogInfo(f"Reset {affected_rows} jobs to Pending in {QueueTable}", "TranscodeQueueRepository", "ResetQueueJobsToPending")
            return affected_rows
        except Exception as e:
            LoggingService.LogException("Exception resetting queue jobs to pending", e, "TranscodeQueueRepository", "ResetQueueJobsToPending")
            return 0
