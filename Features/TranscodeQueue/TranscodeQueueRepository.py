#!/usr/bin/env python3

from typing import Optional, List, Dict, Any
from datetime import datetime
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService
import ntpath
from Core.Path.Path import Path, PathError
from Core.Path.PathStorageRoots import GetStorageRoots
from Features.TranscodeQueue.Models.TranscodeQueueModel import TranscodeQueueModel


# directive: path-schema-migration | # see path.S8
class TranscodeQueueRepository(BaseRepository):
    """Repository for transcode queue CRUD operations."""

    _QUEUE_SELECT_COLS = (
        "Id, StorageRootId, RelativePath, FileName, Directory, "
        "SizeBytes, SizeMB, Priority, Status, DateAdded, DateStarted, "
        "ProcessingMode, ClaimedBy, MediaFileId, TestVariantSetId"
    )

    # directive: path-schema-migration | # see path.S8
    def _MapRowToQueueItem(self, row) -> TranscodeQueueModel:
        """Map a database row to a TranscodeQueueModel; FilePath synthesized via model @property."""
        return TranscodeQueueModel(
            Id=row['Id'],
            StorageRootId=row.get('StorageRootId'),
            RelativePath=row.get('RelativePath') or '',
            FileName=row['FileName'],
            Directory=row['Directory'],
            SizeBytes=row['SizeBytes'],
            SizeMB=row['SizeMB'],
            Priority=row['Priority'],
            Status=row['Status'],
            MediaFileId=row.get('MediaFileId'),
            ClaimedBy=row.get('ClaimedBy'),
            TestVariantSetId=row.get('TestVariantSetId'),
            DateAdded=self.ConvertStringToDateTime(row['DateAdded']) if row.get('DateAdded') else None,
            DateStarted=self.ConvertStringToDateTime(row['DateStarted']) if row.get('DateStarted') else None,
            ProcessingMode=row.get('ProcessingMode') or 'Transcode'
        )

    # directive: path-schema-migration | # see path.S8
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

    # directive: path-schema-migration | # see path.S8
    def GetAllTranscodeQueueItems(self) -> List[TranscodeQueueModel]:
        """Get all transcoding queue items."""
        query = (
            f"SELECT {self._QUEUE_SELECT_COLS} "
            "FROM TranscodeQueue "
            "ORDER BY Priority DESC, DateAdded ASC"
        )
        rows = self.ExecuteQuery(query)
        return [self._MapRowToQueueItem(row) for row in rows]

    # directive: path-schema-migration | # see path.S8
    def GetTranscodeQueueItemById(self, ItemId: int) -> Optional[TranscodeQueueModel]:
        """Get a specific transcoding queue item by ID."""
        query = (
            f"SELECT {self._QUEUE_SELECT_COLS} "
            "FROM TranscodeQueue WHERE Id = %s"
        )
        rows = self.ExecuteQuery(query, (ItemId,))
        if not rows:
            return None
        return self._MapRowToQueueItem(rows[0])

    # directive: path-schema-migration | # see path.S8
    def SaveTranscodeQueueItem(self, QueueItem: TranscodeQueueModel) -> int:
        """Save a transcoding queue item (insert or update) and return the item ID."""
        try:
            if QueueItem.StorageRootId is None or not QueueItem.RelativePath:
                raise PathError(f"SaveTranscodeQueueItem: QueueItem missing typed pair (StorageRootId={QueueItem.StorageRootId}, RelativePath={QueueItem.RelativePath!r})")
            LoggingService.LogFunctionEntry("SaveTranscodeQueueItem", "TranscodeQueueRepository", QueueItem.Id, QueueItem.RelativePath, QueueItem.Status)
            if QueueItem.Id is None:
                _Stem, _Ext = ntpath.splitext((QueueItem.RelativePath or '').lower())
                if _Stem.endswith("-mv") and _Ext:
                    LoggingService.LogWarning(
                        f"Refusing to admit queue row -- source already MediaVortex-transcoded ({QueueItem.RelativePath})",
                        "TranscodeQueueRepository", "SaveTranscodeQueueItem",
                    )
                    return 0
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                if QueueItem.Id is None:
                    LoggingService.LogInfo("Inserting new transcoding queue item...", "TranscodeQueueRepository", "SaveTranscodeQueueItem")
                    MediaFileId = self.DatabaseService.ExecuteScalar(
                        "SELECT Id FROM MediaFiles WHERE StorageRootId = %s AND RelativePath = %s LIMIT 1",
                        (QueueItem.StorageRootId, QueueItem.RelativePath)
                    )
                    query = (
                        "INSERT INTO TranscodeQueue "
                        "(StorageRootId, RelativePath, FileName, Directory, SizeBytes, SizeMB, "
                        "Priority, Status, DateAdded, DateStarted, ProcessingMode, MediaFileId) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                        "RETURNING Id"
                    )
                    parameters = (
                        QueueItem.StorageRootId, QueueItem.RelativePath,
                        QueueItem.FileName, QueueItem.Directory,
                        QueueItem.SizeBytes, QueueItem.SizeMB, QueueItem.Priority,
                        QueueItem.Status, QueueItem.DateAdded, QueueItem.DateStarted,
                        QueueItem.ProcessingMode, MediaFileId
                    )
                    cursor.execute(query, parameters)
                    itemId = cursor.fetchone()[0]
                    connection.commit()
                    LoggingService.LogInfo(f"Queue item inserted with ID: {itemId}", "TranscodeQueueRepository", "SaveTranscodeQueueItem")
                    return itemId
                else:
                    LoggingService.LogInfo(f"Updating existing queue item with ID: {QueueItem.Id}", "TranscodeQueueRepository", "SaveTranscodeQueueItem")
                    query = (
                        "UPDATE TranscodeQueue "
                        "SET StorageRootId = %s, RelativePath = %s, FileName = %s, Directory = %s, "
                        "SizeBytes = %s, SizeMB = %s, Priority = %s, Status = %s, "
                        "DateAdded = %s, DateStarted = %s, ProcessingMode = %s "
                        "WHERE Id = %s"
                    )
                    parameters = (
                        QueueItem.StorageRootId, QueueItem.RelativePath,
                        QueueItem.FileName, QueueItem.Directory,
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

    # directive: path-schema-migration | # see path.S8
    def BulkInsertQueueItems(self, QueueItems: List[TranscodeQueueModel]) -> int:
        """Insert multiple queue items in a single transaction; resolves typed pair + MediaFileId in bulk."""
        if not QueueItems:
            return 0
        try:
            from psycopg2.extras import execute_values

            for Item in QueueItems:
                if Item.StorageRootId is None or not Item.RelativePath:
                    raise PathError(f"BulkInsertQueueItems: Item missing typed pair (StorageRootId={Item.StorageRootId}, RelativePath={Item.RelativePath!r})")

            Connection = self.DatabaseService.GetConnection()
            try:
                Cursor = Connection.cursor()

                # Bulk-resolve MediaFileIds via typed-pair (MediaFiles.FilePath has been dropped).
                TypedPairs = [
                    (Item.StorageRootId, Item.RelativePath)
                    for Item in QueueItems
                    if Item.StorageRootId is not None and Item.RelativePath
                ]
                PairToMediaFileId: Dict[tuple, int] = {}
                if TypedPairs:
                    Cursor.execute(
                        "SELECT Id, StorageRootId, RelativePath FROM MediaFiles "
                        "WHERE (StorageRootId, RelativePath) IN %s",
                        (tuple(TypedPairs),)
                    )
                    PairToMediaFileId = {(Row[1], Row[2]): Row[0] for Row in Cursor.fetchall()}

                Values = []
                for Item in QueueItems:
                    MediaFileId = PairToMediaFileId.get((Item.StorageRootId, Item.RelativePath))
                    Values.append((
                        Item.StorageRootId, Item.RelativePath,
                        Item.FileName, Item.Directory,
                        Item.SizeBytes, Item.SizeMB, Item.Priority,
                        Item.Status, Item.DateAdded, Item.DateStarted,
                        Item.ProcessingMode, MediaFileId
                    ))

                execute_values(
                    Cursor,
                    "INSERT INTO TranscodeQueue "
                    "(StorageRootId, RelativePath, FileName, Directory, "
                    "SizeBytes, SizeMB, Priority, Status, DateAdded, DateStarted, "
                    "ProcessingMode, MediaFileId) "
                    "VALUES %s",
                    Values,
                    page_size=500
                )
                Inserted = Cursor.rowcount
                Connection.commit()
                LoggingService.LogInfo(f"Bulk-inserted {Inserted} queue items in one transaction", "TranscodeQueueRepository", "BulkInsertQueueItems")
                return Inserted
            finally:
                self.DatabaseService.CloseConnection(Connection)
        except Exception as Ex:
            LoggingService.LogException("Exception in BulkInsertQueueItems", Ex, "TranscodeQueueRepository", "BulkInsertQueueItems")
            raise

    # directive: path-schema-migration | # see path.S8
    def GetExistingQueueFilePaths(self) -> set:
        """Return a set of FilePaths currently in the queue (synthesized from typed pair)."""
        Rows = self.ExecuteQuery("SELECT StorageRootId, RelativePath FROM TranscodeQueue")
        return {Row.get('FilePath', '') for Row in Rows}

    # directive: path-schema-migration | # see path.S8
    def DeleteTranscodeQueueItem(self, ItemId: int) -> bool:
        """Delete a transcoding queue item."""
        affectedRows = self.ExecuteNonQuery("DELETE FROM TranscodeQueue WHERE Id = %s", (ItemId,))
        return affectedRows > 0

    # directive: path-schema-migration | # see path.S8
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

    # directive: path-schema-migration | # see path.S8
    def GetTranscodeQueueItemsByStatus(self, Status: str) -> List[TranscodeQueueModel]:
        """Get all transcoding queue items with a specific status."""
        query = (
            f"SELECT {self._QUEUE_SELECT_COLS} "
            "FROM TranscodeQueue WHERE Status = %s "
            "ORDER BY Priority DESC, DateAdded ASC"
        )
        rows = self.ExecuteQuery(query, (Status,))
        return [self._MapRowToQueueItem(row) for row in rows]

    # directive: path-schema-migration | # see path.S8
    def GetNextPendingTranscodeJob(self) -> Optional[TranscodeQueueModel]:
        """Get the next pending transcoding job (highest priority first, oldest tiebreaker)."""
        query = (
            f"SELECT {self._QUEUE_SELECT_COLS} "
            "FROM TranscodeQueue WHERE Status = 'Pending' "
            "ORDER BY Priority DESC, DateAdded ASC LIMIT 1"
        )
        rows = self.ExecuteQuery(query)
        if not rows:
            return None
        return self._MapRowToQueueItem(rows[0])

    # directive: path-schema-migration | # see path.S8
    def ClaimNextPendingTranscodeJob(self, WorkerName: str, AcceptsInterlaced: bool = True) -> Optional[TranscodeQueueModel]:
        """Atomically claim the next pending Transcode-mode job (NULL or 'Transcode'); honors capability + NVENC gates."""
        try:
            import psycopg2.extras
            from Core.Database.WorkerCapabilityPredicate import BuildClaimPredicate
            CapabilityFragment, CapabilityParams = BuildClaimPredicate(WorkerName, "TranscodeEnabled")
            NvencGate = (
                "p.profilename IS NOT NULL "
                "AND (p.usenvidiahardware = 0 "
                "OR EXISTS (SELECT 1 FROM Workers w2 "
                "WHERE w2.WorkerName = %s AND w2.nvenccapable = TRUE))"
            )
            ReturningCols = (
                "Id, StorageRootId, RelativePath, FileName, Directory, "
                "SizeBytes, SizeMB, Priority, Status, DateAdded, DateStarted, "
                "ProcessingMode, ClaimedBy, MediaFileId, TestVariantSetId"
            )
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                if AcceptsInterlaced:
                    query = (
                        "UPDATE TranscodeQueue "
                        "SET Status = 'Running', ClaimedBy = %s, ClaimedAt = NOW(), DateStarted = NOW() "
                        "WHERE Id = ( "
                        "  SELECT tq.Id FROM TranscodeQueue tq "
                        "  LEFT JOIN MediaFiles mf ON tq.MediaFileId = mf.Id "
                        "  LEFT JOIN Profiles p ON p.profilename = mf.AssignedProfile "
                        "  WHERE tq.Status = 'Pending' "
                        "    AND (tq.ProcessingMode IS NULL OR tq.ProcessingMode = 'Transcode') "
                        f"    AND {CapabilityFragment} "
                        f"    AND {NvencGate} "
                        "  ORDER BY tq.Priority DESC, tq.DateAdded ASC "
                        "  LIMIT 1 "
                        "  FOR UPDATE OF tq SKIP LOCKED "
                        ") "
                        f"RETURNING {ReturningCols}"
                    )
                else:
                    query = (
                        "UPDATE TranscodeQueue "
                        "SET Status = 'Running', ClaimedBy = %s, ClaimedAt = NOW(), DateStarted = NOW() "
                        "WHERE Id = ( "
                        "  SELECT tq.Id FROM TranscodeQueue tq "
                        "  JOIN MediaFiles mf ON tq.MediaFileId = mf.Id "
                        "  LEFT JOIN Profiles p ON p.profilename = mf.AssignedProfile "
                        "  WHERE tq.Status = 'Pending' "
                        "    AND (tq.ProcessingMode IS NULL OR tq.ProcessingMode = 'Transcode') "
                        "    AND (mf.IsInterlaced IS NULL OR mf.IsInterlaced = '0') "
                        f"    AND {CapabilityFragment} "
                        f"    AND {NvencGate} "
                        "  ORDER BY tq.Priority DESC, tq.DateAdded ASC "
                        "  LIMIT 1 "
                        "  FOR UPDATE OF tq SKIP LOCKED "
                        ") "
                        f"RETURNING {ReturningCols}"
                    )
                cursor.execute(query, (WorkerName,) + CapabilityParams + (WorkerName,))
                row = cursor.fetchone()
                connection.commit()

                if row:
                    NormalizedRow = {
                        'Id': row['id'],
                        'StorageRootId': row.get('storagerootid'),
                        'RelativePath': row.get('relativepath') or '',
                        'FileName': row['filename'],
                        'Directory': row['directory'],
                        'SizeBytes': row['sizebytes'],
                        'SizeMB': row['sizemb'],
                        'Priority': row['priority'],
                        'Status': row['status'],
                        'DateAdded': row['dateadded'],
                        'DateStarted': row['datestarted'],
                        'ProcessingMode': row.get('processingmode') or 'Transcode',
                        'ClaimedBy': row.get('claimedby'),
                        'MediaFileId': row.get('mediafileid'),
                        'TestVariantSetId': row.get('testvariantsetid'),
                    }
                    return self._MapRowToQueueItem(NormalizedRow)
                return None
            finally:
                self.DatabaseService.CloseConnection(connection)
        except Exception as e:
            LoggingService.LogException("Exception in ClaimNextPendingTranscodeJob", e, "TranscodeQueueRepository", "ClaimNextPendingTranscodeJob")
            return None

    # directive: path-schema-migration | # see path.S8
    def ClaimNextPendingRemuxJob(self, WorkerName: str) -> Optional[TranscodeQueueModel]:
        """Atomically claim the next Remux-class job (Remux/Quick/AudioFix); gated on RemuxEnabled."""
        try:
            import psycopg2.extras
            from Core.Database.WorkerCapabilityPredicate import BuildClaimPredicate
            CapabilityFragment, CapabilityParams = BuildClaimPredicate(WorkerName, "RemuxEnabled")
            ReturningCols = (
                "Id, StorageRootId, RelativePath, FileName, Directory, "
                "SizeBytes, SizeMB, Priority, Status, DateAdded, DateStarted, "
                "ProcessingMode, ClaimedBy, MediaFileId, TestVariantSetId"
            )
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                query = (
                    "UPDATE TranscodeQueue "
                    "SET Status = 'Running', ClaimedBy = %s, ClaimedAt = NOW(), DateStarted = NOW() "
                    "WHERE Id = ( "
                    "  SELECT Id FROM TranscodeQueue "
                    "  WHERE Status = 'Pending' "
                    "    AND ProcessingMode IN ('Remux', 'Quick', 'AudioFix') "
                    f"   AND {CapabilityFragment} "
                    "  ORDER BY Priority DESC, DateAdded ASC "
                    "  LIMIT 1 "
                    "  FOR UPDATE SKIP LOCKED "
                    ") "
                    f"RETURNING {ReturningCols}"
                )
                cursor.execute(query, (WorkerName,) + CapabilityParams)
                row = cursor.fetchone()
                connection.commit()

                if row:
                    NormalizedRow = {
                        'Id': row['id'],
                        'StorageRootId': row.get('storagerootid'),
                        'RelativePath': row.get('relativepath') or '',
                        'FileName': row['filename'],
                        'Directory': row['directory'],
                        'SizeBytes': row['sizebytes'],
                        'SizeMB': row['sizemb'],
                        'Priority': row['priority'],
                        'Status': row['status'],
                        'DateAdded': row['dateadded'],
                        'DateStarted': row['datestarted'],
                        'ProcessingMode': row.get('processingmode') or 'Remux',
                        'ClaimedBy': row.get('claimedby'),
                        'MediaFileId': row.get('mediafileid'),
                        'TestVariantSetId': row.get('testvariantsetid'),
                    }
                    return self._MapRowToQueueItem(NormalizedRow)
                return None
            finally:
                self.DatabaseService.CloseConnection(connection)
        except Exception as e:
            LoggingService.LogException("Exception in ClaimNextPendingRemuxJob", e, "TranscodeQueueRepository", "ClaimNextPendingRemuxJob")
            return None

    # directive: path-schema-migration | # see path.S8
    def GetTranscodeQueueItemsPaginated(self, Page: int = 1, PageSize: int = 25, SortBy: str = "Priority", SortOrder: str = "DESC", Mode: str = None):
        """Get paginated transcoding queue items with SQL-level sorting + optional ProcessingMode filter."""
        sort_columns = {
            'SizeMB': 'SizeMB',
            'Priority': 'Priority',
            'DateAdded': 'DateAdded',
            'FileName': 'FileName'
        }
        sort_col = sort_columns.get(SortBy, 'Priority')
        order = 'DESC' if SortOrder == 'DESC' else 'ASC'

        ModeFilter = Mode if Mode in ('Transcode', 'Quick', 'Remux', 'AudioFix') else None
        WhereClause = "WHERE ProcessingMode = %s" if ModeFilter else ""
        FilterParams = (ModeFilter,) if ModeFilter else ()

        count_query = f"SELECT COUNT(*) as Count FROM TranscodeQueue {WhereClause}"
        count_rows = self.ExecuteQuery(count_query, FilterParams if ModeFilter else ())
        total_items = count_rows[0]['Count'] if count_rows else 0

        offset = (Page - 1) * PageSize
        query = (
            f"SELECT {self._QUEUE_SELECT_COLS} "
            "FROM TranscodeQueue "
            f"{WhereClause} "
            f"ORDER BY {sort_col} {order}, DateAdded ASC "
            "LIMIT %s OFFSET %s"
        )
        rows = self.ExecuteQuery(query, FilterParams + (PageSize, offset))
        return [self._MapRowToQueueItem(row) for row in rows], total_items

    # directive: path-schema-migration | # see path.S8
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

    # directive: path-schema-migration | # see path.S8
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

    # directive: path-schema-migration | # see path.S8
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
