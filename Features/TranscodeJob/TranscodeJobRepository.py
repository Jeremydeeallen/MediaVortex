from typing import Optional, List, Dict, Any
from datetime import datetime
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService
from Core.Models.TranscodeAttemptModel import TranscodeAttemptModel
from Core.Models.TranscodeFileModel import TranscodeFileModel
from Features.TranscodeJob.Models.TranscodeProgressModel import TranscodeProgressModel
# directive: path-schema-migration | # see path.S8
from Core.Path.Path import Path, PathError
from Core.Path.PathStorageRoots import GetStorageRoots


class TranscodeJobRepository(BaseRepository):
    """Repository for TranscodeAttempts, TranscodeFiles, and TranscodeProgress database operations."""

    # region Helper Methods

    # directive: path-schema-migration | # see path.S8
    def _MapRowToAttempt(self, row) -> TranscodeAttemptModel:
        """Map a database row to a TranscodeAttemptModel."""
        return TranscodeAttemptModel(
            Id=row['Id'],
            StorageRootId=row.get('StorageRootId'),
            RelativePath=row.get('RelativePath') or '',
            AttemptDate=row['AttemptDate'],
            Quality=row['Quality'],
            OldSizeBytes=row['OldSizeBytes'],
            NewSizeBytes=row['NewSizeBytes'],
            Success=row['Success'],
            SizeReductionBytes=row['SizeReductionBytes'],
            SizeReductionPercent=row['SizeReductionPercent'],
            ErrorMessage=row['ErrorMessage'],
            TranscodeDurationSeconds=row['TranscodeDurationSeconds'],
            FfpmpegCommand=row['FfpmpegCommand'],
            AudioBitrateKbps=row['AudioBitrateKbps'],
            VideoBitrateKbps=row['VideoBitrateKbps'],
            ProfileName=row['ProfileName'],
            VMAF=row['VMAF'],
            FileReplaced=bool(row.get('FileReplaced', False)),
            FileReplacedDate=row.get('FileReplacedDate'),
            ReplacementType=row.get('ReplacementType'),
            StartTime=row.get('StartTime'),
            PreferredAttempt=bool(row.get('PreferredAttempt', False)),
            WorkerName=row.get('WorkerName')
        )

    def _MapRowToTranscodeFile(self, row) -> TranscodeFileModel:
        """Map a database row to a TranscodeFileModel."""
        return TranscodeFileModel(
            Id=row['Id'],
            FilePath=row['FilePath'],
            AllQualitiesFailed=row['AllQualitiesFailed'],
            SuccessfullyTranscoded=row['SuccessfullyTranscoded'],
            FirstAttemptDate=row['FirstAttemptDate'],
            LastAttemptDate=row['LastAttemptDate'],
            SuccessDate=row['SuccessDate'],
            FinalQuality=row['FinalQuality'],
            FinalSizeBytes=row['FinalSizeBytes'],
            TotalAttempts=row['TotalAttempts'],
            OriginalFilePath=row['OriginalFilePath'],
            FinalFilePath=row['FinalFilePath']
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
                LoggingService.LogWarning(f"Failed to convert date string to datetime: {DateString}", "TranscodeJobRepository", "ConvertStringToDateTime")
                return None

    # endregion

    # region TranscodeAttempts Methods

    # directive: path-schema-migration | # see path.S8
    _ATTEMPT_SELECT_COLUMNS = (
        "Id, StorageRootId, RelativePath, AttemptDate, Quality, OldSizeBytes, NewSizeBytes, Success, "
        "SizeReductionBytes, SizeReductionPercent, ErrorMessage, TranscodeDurationSeconds, "
        "FfpmpegCommand, AudioBitrateKbps, VideoBitrateKbps, ProfileName, VMAF, "
        "FileReplaced, FileReplacedDate, ReplacementType, StartTime, PreferredAttempt, "
        "WorkerName"
    )

    # directive: path-schema-migration | # see path.S8
    def GetAllTranscodeAttempts(self) -> List[TranscodeAttemptModel]:
        """Get all transcoding attempts."""
        query = (
            f"SELECT {self._ATTEMPT_SELECT_COLUMNS} "
            "FROM TranscodeAttempts "
            "ORDER BY AttemptDate DESC"
        )
        rows = self.DatabaseService.ExecuteQuery(query)
        return [self._MapRowToAttempt(row) for row in rows]

    # directive: path-schema-migration | # see path.S8
    def GetTranscodeAttemptById(self, AttemptId: int) -> Optional[TranscodeAttemptModel]:
        """Get a specific transcoding attempt by ID."""
        query = (
            f"SELECT {self._ATTEMPT_SELECT_COLUMNS} "
            "FROM TranscodeAttempts "
            "WHERE Id = %s"
        )
        rows = self.DatabaseService.ExecuteQuery(query, (AttemptId,))
        if rows:
            return self._MapRowToAttempt(rows[0])
        return None

    # directive: path-schema-migration | # see path.S8
    def GetTranscodeAttemptsByMediaFileId(self, MediaFileId: int) -> List[TranscodeAttemptModel]:
        """Get all transcoding attempts for a specific media file by ID."""
        query = (
            f"SELECT {self._ATTEMPT_SELECT_COLUMNS} "
            "FROM TranscodeAttempts "
            "WHERE MediaFileId = %s "
            "ORDER BY PreferredAttempt DESC, AttemptDate DESC"
        )
        rows = self.DatabaseService.ExecuteQuery(query, (MediaFileId,))
        return [self._MapRowToAttempt(row) for row in rows]

    # directive: path-schema-migration | # see path.S8
    def GetLatestTranscodeAttemptWithVMAF(self, MediaFileId: int) -> Optional[Dict[str, Any]]:
        """Get the most recent transcode attempt with VMAF score; prioritizes preferred attempts."""
        try:
            LoggingService.LogFunctionEntry("GetLatestTranscodeAttemptWithVMAF", "TranscodeJobRepository", MediaFileId)

            preferred_query = (
                "SELECT Quality, VMAF, ProfileName, AttemptDate, Success, PreferredAttempt "
                "FROM TranscodeAttempts "
                "WHERE MediaFileId = %s "
                "  AND VMAF IS NOT NULL "
                "  AND Success = TRUE "
                "  AND PreferredAttempt = TRUE "
                "ORDER BY AttemptDate DESC "
                "LIMIT 1"
            )

            rows = self.DatabaseService.ExecuteQuery(preferred_query, (MediaFileId,))

            if rows:
                result = rows[0]
                LoggingService.LogInfo(f"Found preferred attempt for MediaFileId {MediaFileId}: CRF={result.get('Quality')}, VMAF={result.get('VMAF')}",
                                     "TranscodeJobRepository", "GetLatestTranscodeAttemptWithVMAF")
                return result

            query = (
                "SELECT Quality, VMAF, ProfileName, AttemptDate, Success, PreferredAttempt "
                "FROM TranscodeAttempts "
                "WHERE MediaFileId = %s "
                "  AND VMAF IS NOT NULL "
                "  AND Success = TRUE "
                "ORDER BY AttemptDate DESC "
                "LIMIT 1"
            )

            rows = self.DatabaseService.ExecuteQuery(query, (MediaFileId,))

            if rows:
                result = rows[0]
                LoggingService.LogInfo(f"Found latest attempt for MediaFileId {MediaFileId}: CRF={result.get('Quality')}, VMAF={result.get('VMAF')}",
                                     "TranscodeJobRepository", "GetLatestTranscodeAttemptWithVMAF")
                return result
            else:
                LoggingService.LogDebug(f"No previous successful attempt with VMAF found for MediaFileId {MediaFileId}",
                                      "TranscodeJobRepository", "GetLatestTranscodeAttemptWithVMAF")
                return None

        except Exception as e:
            LoggingService.LogException("Exception getting latest transcode attempt with VMAF", e, "TranscodeJobRepository", "GetLatestTranscodeAttemptWithVMAF")
            return None

    # directive: path-schema-migration | # see path.S8
    def SaveTranscodeAttempt(self, Attempt: TranscodeAttemptModel) -> int:
        """Save a transcoding attempt (insert or update) and return the attempt ID."""
        try:
            if Attempt.StorageRootId is None or not Attempt.RelativePath:
                raise PathError(f"SaveTranscodeAttempt: Attempt missing typed pair (StorageRootId={Attempt.StorageRootId}, RelativePath={Attempt.RelativePath!r})")
            LoggingService.LogFunctionEntry("SaveTranscodeAttempt", "TranscodeJobRepository", Attempt.Id, Attempt.RelativePath, Attempt.Success)

            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()

                if Attempt.Id is None:
                    LoggingService.LogInfo("Inserting new transcoding attempt...", "TranscodeJobRepository", "SaveTranscodeAttempt")
                    # directive: failure-accounting | # see failure-accounting.C5
                    MediaFileId = Attempt.MediaFileId
                    if MediaFileId is None:
                        MediaFileId = self.DatabaseService.ExecuteScalar(
                            "SELECT Id FROM MediaFiles WHERE StorageRootId = %s AND RelativePath = %s LIMIT 1",
                            (Attempt.StorageRootId, Attempt.RelativePath)
                        )
                    if MediaFileId is None:
                        LoggingService.LogWarning(
                            "TranscodeAttempts INSERT could not resolve MediaFileId; using sentinel 0. Attempt(StorageRootId=" + str(Attempt.StorageRootId) + ", RelativePath=" + repr(Attempt.RelativePath) + ", ProfileName=" + repr(Attempt.ProfileName) + ", WorkerName=" + repr(Attempt.WorkerName) + "). see failure-accounting.C5",
                            "TranscodeJobRepository", "SaveTranscodeAttempt"
                        )
                        MediaFileId = 0
                    ProfileNameForInsert = Attempt.ProfileName
                    if not ProfileNameForInsert:
                        raise ValueError(
                            f"SaveTranscodeAttempt: ProfileName unresolved (MediaFileId={MediaFileId}, StorageRootId={Attempt.StorageRootId}, RelativePath={Attempt.RelativePath!r}). Caller must populate ProfileName -- JobMode is the mandatory fallback."
                        )
                    Sid = Attempt.StorageRootId
                    Rel = Attempt.RelativePath
                    query = (
                        "INSERT INTO TranscodeAttempts "
                        "(StorageRootId, RelativePath, AttemptDate, Quality, OldSizeBytes, NewSizeBytes, Success, "
                        " SizeReductionBytes, SizeReductionPercent, ErrorMessage, TranscodeDurationSeconds, "
                        " FfpmpegCommand, AudioBitrateKbps, VideoBitrateKbps, ProfileName, VMAF, "
                        " FileReplaced, FileReplacedDate, ReplacementType, StartTime, PreferredAttempt, "
                        " WorkerName, MediaFileId) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                        "RETURNING Id"
                    )
                    parameters = (
                        Sid, Rel,
                        Attempt.AttemptDate, Attempt.Quality,
                        Attempt.OldSizeBytes, Attempt.NewSizeBytes, Attempt.Success,
                        Attempt.SizeReductionBytes, Attempt.SizeReductionPercent, Attempt.ErrorMessage,
                        Attempt.TranscodeDurationSeconds,
                        Attempt.FfpmpegCommand,
                        Attempt.AudioBitrateKbps, Attempt.VideoBitrateKbps, ProfileNameForInsert, Attempt.VMAF,
                        Attempt.FileReplaced, Attempt.FileReplacedDate, Attempt.ReplacementType, Attempt.StartTime,
                        Attempt.PreferredAttempt,
                        Attempt.WorkerName, MediaFileId
                    )
                    LoggingService.LogInfo(f"Insert attempt parameters: {parameters}", "TranscodeJobRepository", "SaveTranscodeAttempt")
                    # directive: transcode-flow-canonical -- ta_one_inflight_per_mfid enforces one Success-NULL row per MediaFileId; UniqueViolation = race lost, release queue row
                    try:
                        cursor.execute(query, parameters)
                    except Exception as insertEx:
                        import psycopg2
                        if isinstance(insertEx, psycopg2.errors.UniqueViolation):
                            connection.rollback()
                            LoggingService.LogWarning(
                                f"Attempt INSERT refused by ta_one_inflight_per_mfid (MediaFileId={MediaFileId}); another in-flight attempt already exists. Releasing queue row for MediaFileId back to Pending.",
                                "TranscodeJobRepository", "SaveTranscodeAttempt",
                            )
                            self.DatabaseService.ExecuteNonQuery(
                                "UPDATE TranscodeQueue SET Status='Pending', ClaimedBy=NULL, ClaimedAt=NULL, DateStarted=NULL "
                                "WHERE MediaFileId=%s AND Status='Running' AND ClaimedBy = %s",
                                (MediaFileId, Attempt.WorkerName),
                            )
                            return None
                        raise
                    attemptId = cursor.fetchone()[0]
                    connection.commit()
                    LoggingService.LogInfo(f"Attempt inserted with ID: {attemptId}", "TranscodeJobRepository", "SaveTranscodeAttempt")
                    return attemptId
                else:
                    LoggingService.LogInfo(f"Updating existing attempt with ID: {Attempt.Id}", "TranscodeJobRepository", "SaveTranscodeAttempt")
                    query = (
                        "UPDATE TranscodeAttempts "
                        "SET AttemptDate = %s, Quality = %s, OldSizeBytes = %s, NewSizeBytes = %s, "
                        "    Success = %s, SizeReductionBytes = %s, SizeReductionPercent = %s, ErrorMessage = %s, "
                        "    TranscodeDurationSeconds = %s, FfpmpegCommand = %s, AudioBitrateKbps = %s, "
                        "    VideoBitrateKbps = %s, ProfileName = %s, VMAF = %s, "
                        "    FileReplaced = %s, FileReplacedDate = %s, ReplacementType = %s, PreferredAttempt = %s "
                        "WHERE Id = %s"
                    )
                    parameters = (
                        Attempt.AttemptDate, Attempt.Quality,
                        Attempt.OldSizeBytes, Attempt.NewSizeBytes, Attempt.Success,
                        Attempt.SizeReductionBytes, Attempt.SizeReductionPercent, Attempt.ErrorMessage,
                        Attempt.TranscodeDurationSeconds,
                        Attempt.FfpmpegCommand,
                        Attempt.AudioBitrateKbps, Attempt.VideoBitrateKbps, Attempt.ProfileName, Attempt.VMAF,
                        Attempt.FileReplaced, Attempt.FileReplacedDate, Attempt.ReplacementType, Attempt.PreferredAttempt, Attempt.Id
                    )
                    LoggingService.LogInfo(f"Update attempt parameters: {parameters}", "TranscodeJobRepository", "SaveTranscodeAttempt")
                    cursor.execute(query, parameters)
                    connection.commit()
                    affectedRows = cursor.rowcount
                    LoggingService.LogInfo(f"Attempt update affected {affectedRows} rows", "TranscodeJobRepository", "SaveTranscodeAttempt")
                    return Attempt.Id
            finally:
                self.DatabaseService.CloseConnection(connection)
        except Exception as e:
            LoggingService.LogException("Exception in SaveTranscodeAttempt", e, "TranscodeJobRepository", "SaveTranscodeAttempt")
            raise

    # directive: path-schema-migration | # see path.S8
    def UpdateTranscodeAttempt(self, AttemptId: int, Updates: Dict[str, Any]) -> bool:
        """Update specific fields of a transcoding attempt."""
        try:
            LoggingService.LogFunctionEntry("UpdateTranscodeAttempt", "TranscodeJobRepository", AttemptId, Updates)

            valid_fields = [
                'StorageRootId', 'RelativePath',
                'AttemptDate', 'Quality', 'OldSizeBytes', 'NewSizeBytes',
                'Success', 'SizeReductionBytes', 'SizeReductionPercent', 'ErrorMessage',
                'TranscodeDurationSeconds', 'FfpmpegCommand', 'AudioBitrateKbps',
                'VideoBitrateKbps', 'ProfileName', 'VMAF', 'FileReplaced', 'FileReplacedDate',
                'ReplacementType', 'StartTime', 'PreferredAttempt', 'WorkerName',
                'CompletedDate', 'QualityTestRequired', 'QualityTestCompleted',
                'TestVariantSetId', 'TestVariantName'
            ]

            set_clauses = []
            parameters = []

            for field, value in Updates.items():
                if field == 'FilePath':
                    try:
                        _P = Path.FromLegacyString(value, GetStorageRoots()) if value else None
                    except PathError:
                        _P = None
                    set_clauses.append("StorageRootId = %s")
                    parameters.append(_P.StorageRootId if _P else None)
                    set_clauses.append("RelativePath = %s")
                    parameters.append(_P.RelativePath if _P else '')
                elif field in valid_fields:
                    set_clauses.append(f"{field} = %s")
                    parameters.append(value)
                elif field == 'FFmpegOutput':
                    set_clauses.append("FfpmpegCommand = %s")
                    parameters.append(value)
                elif field == 'FFmpegError':
                    set_clauses.append("ErrorMessage = %s")
                    parameters.append(value)
                else:
                    LoggingService.LogWarning(f"Unknown field '{field}' ignored in UpdateTranscodeAttempt",
                                            "TranscodeJobRepository", "UpdateTranscodeAttempt")

            if not set_clauses:
                LoggingService.LogWarning("No valid fields to update", "TranscodeJobRepository", "UpdateTranscodeAttempt")
                return False

            # directive: transcode-flow-canonical -- owner-only writes at repo layer; VMAF finalization + owner-transfer path exempt
            VmafFinalizationKeys = {'VMAF', 'QualityTestCompleted', 'StorageRootId', 'RelativePath', 'WorkerName'}
            UpdatingFieldSet = set(Updates.keys())
            IsVmafFinalizationOnly = UpdatingFieldSet.issubset(VmafFinalizationKeys) and 'VMAF' in UpdatingFieldSet
            OwnerGate = ""
            OwnerParams = ()
            if not IsVmafFinalizationOnly:
                try:
                    from Core.WorkerContext import WorkerContext
                    LocalWorkerName = WorkerContext.Current().WorkerName
                    OwnerGate = " AND WorkerName = %s"
                    OwnerParams = (LocalWorkerName,)
                except Exception:
                    OwnerGate = ""
                    OwnerParams = ()

            query = f"UPDATE TranscodeAttempts SET {', '.join(set_clauses)} WHERE Id = %s{OwnerGate}"
            parameters.append(AttemptId)
            if OwnerParams:
                parameters.extend(OwnerParams)

            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()
                cursor.execute(query, parameters)
                connection.commit()
                affected_rows = cursor.rowcount
                if affected_rows == 0 and OwnerGate:
                    LoggingService.LogWarning(
                        f"UpdateTranscodeAttempt refused: attempt {AttemptId} not owned by this worker (OwnerParams={OwnerParams}); fields={list(Updates.keys())}",
                        "TranscodeJobRepository", "UpdateTranscodeAttempt",
                    )
                LoggingService.LogInfo(f"Updated {affected_rows} rows for attempt {AttemptId} with fields: {list(Updates.keys())}",
                                     "TranscodeJobRepository", "UpdateTranscodeAttempt")
                return affected_rows > 0
            finally:
                self.DatabaseService.CloseConnection(connection)

        except Exception as e:
            LoggingService.LogException("Exception in UpdateTranscodeAttempt", e, "TranscodeJobRepository", "UpdateTranscodeAttempt")
            return False

    # directive: path-schema-migration | # see path.S8
    def SetPreferredAttempt(self, AttemptId: int, MediaFileId: int, IsPreferred: bool = True) -> bool:
        """Set/unset a transcode attempt as preferred; when setting, unsets all others for the same file."""
        try:
            LoggingService.LogFunctionEntry("SetPreferredAttempt", "TranscodeJobRepository", AttemptId, MediaFileId, IsPreferred)

            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()

                if IsPreferred:
                    unset_query = (
                        "UPDATE TranscodeAttempts "
                        "SET PreferredAttempt = FALSE "
                        "WHERE MediaFileId = %s "
                        "  AND Id != %s"
                    )
                    cursor.execute(unset_query, (MediaFileId, AttemptId))

                    set_query = (
                        "UPDATE TranscodeAttempts "
                        "SET PreferredAttempt = TRUE "
                        "WHERE Id = %s"
                    )
                    cursor.execute(set_query, (AttemptId,))
                    connection.commit()

                    LoggingService.LogInfo(f"Set attempt {AttemptId} as preferred for MediaFileId {MediaFileId}",
                                         "TranscodeJobRepository", "SetPreferredAttempt")
                else:
                    unset_query = (
                        "UPDATE TranscodeAttempts "
                        "SET PreferredAttempt = FALSE "
                        "WHERE Id = %s"
                    )
                    cursor.execute(unset_query, (AttemptId,))
                    connection.commit()

                    LoggingService.LogInfo(f"Unset preferred status for attempt {AttemptId}",
                                         "TranscodeJobRepository", "SetPreferredAttempt")

                return True

            finally:
                self.DatabaseService.CloseConnection(connection)

        except Exception as e:
            LoggingService.LogException("Exception in SetPreferredAttempt", e, "TranscodeJobRepository", "SetPreferredAttempt")
            return False

    # endregion

    # region TranscodeFiles Methods

    _TRANSCODE_FILE_SELECT_COLUMNS = (
        "Id, FilePath, AllQualitiesFailed, SuccessfullyTranscoded, FirstAttemptDate, "
        "LastAttemptDate, SuccessDate, FinalQuality, FinalSizeBytes, TotalAttempts, "
        "OriginalFilePath, FinalFilePath"
    )

    # directive: path-schema-migration | # see path.S8
    def GetAllTranscodeFiles(self) -> List[TranscodeFileModel]:
        """Get all transcoding file records."""
        query = (
            f"SELECT {self._TRANSCODE_FILE_SELECT_COLUMNS} "
            "FROM TranscodeFiles "
            "ORDER BY FirstAttemptDate DESC"
        )
        rows = self.DatabaseService.ExecuteQuery(query)
        return [self._MapRowToTranscodeFile(row) for row in rows]

    # directive: path-schema-migration | # see path.S8
    def GetTranscodeFileByMediaFileId(self, MediaFileId: int) -> Optional[TranscodeFileModel]:
        """Get transcoding file record by media file ID."""
        query = (
            f"SELECT {self._TRANSCODE_FILE_SELECT_COLUMNS} "
            "FROM TranscodeFiles "
            "WHERE MediaFileId = %s"
        )
        rows = self.DatabaseService.ExecuteQuery(query, (MediaFileId,))
        if not rows:
            return None
        return self._MapRowToTranscodeFile(rows[0])

    def SaveTranscodeFile(self, TranscodeFile: TranscodeFileModel) -> int:
        """Save a transcoding file record (insert or update) and return the file ID."""
        try:
            LoggingService.LogFunctionEntry("SaveTranscodeFile", "TranscodeJobRepository", TranscodeFile.Id, TranscodeFile.FilePath, TranscodeFile.SuccessfullyTranscoded)

            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()

                if TranscodeFile.Id is None:
                    # Insert new transcode file
                    LoggingService.LogInfo("Inserting new transcoding file record...", "TranscodeJobRepository", "SaveTranscodeFile")
                    MediaFileId = self.LookupMediaFileId(TranscodeFile.FilePath)
                    query = """
                        INSERT INTO TranscodeFiles
                        (AllQualitiesFailed, SuccessfullyTranscoded, FirstAttemptDate,
                         LastAttemptDate, SuccessDate, FinalQuality, FinalSizeBytes, TotalAttempts,
                         OriginalFilePath, FinalFilePath, MediaFileId)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING Id
                    """
                    parameters = (
                        TranscodeFile.AllQualitiesFailed, TranscodeFile.SuccessfullyTranscoded,
                        TranscodeFile.FirstAttemptDate, TranscodeFile.LastAttemptDate, TranscodeFile.SuccessDate,
                        TranscodeFile.FinalQuality, TranscodeFile.FinalSizeBytes, TranscodeFile.TotalAttempts,
                        TranscodeFile.OriginalFilePath, TranscodeFile.FinalFilePath, MediaFileId
                    )
                    LoggingService.LogInfo(f"Insert transcode file parameters: {parameters}", "TranscodeJobRepository", "SaveTranscodeFile")
                    cursor.execute(query, parameters)
                    fileId = cursor.fetchone()[0]
                    connection.commit()
                    LoggingService.LogInfo(f"Transcode file inserted with ID: {fileId}", "TranscodeJobRepository", "SaveTranscodeFile")
                    return fileId
                else:
                    # Update existing transcode file
                    LoggingService.LogInfo(f"Updating existing transcode file with ID: {TranscodeFile.Id}", "TranscodeJobRepository", "SaveTranscodeFile")
                    query = """
                        UPDATE TranscodeFiles
                        SET AllQualitiesFailed = %s, SuccessfullyTranscoded = %s, FirstAttemptDate = %s,
                            LastAttemptDate = %s, SuccessDate = %s, FinalQuality = %s, FinalSizeBytes = %s,
                            TotalAttempts = %s, OriginalFilePath = %s, FinalFilePath = %s
                        WHERE Id = %s
                    """
                    parameters = (
                        TranscodeFile.AllQualitiesFailed, TranscodeFile.SuccessfullyTranscoded,
                        TranscodeFile.FirstAttemptDate, TranscodeFile.LastAttemptDate, TranscodeFile.SuccessDate,
                        TranscodeFile.FinalQuality, TranscodeFile.FinalSizeBytes, TranscodeFile.TotalAttempts,
                        TranscodeFile.OriginalFilePath, TranscodeFile.FinalFilePath, TranscodeFile.Id
                    )
                    LoggingService.LogInfo(f"Update transcode file parameters: {parameters}", "TranscodeJobRepository", "SaveTranscodeFile")
                    cursor.execute(query, parameters)
                    connection.commit()
                    affectedRows = cursor.rowcount
                    LoggingService.LogInfo(f"Transcode file update affected {affectedRows} rows", "TranscodeJobRepository", "SaveTranscodeFile")
                    return TranscodeFile.Id
            finally:
                self.DatabaseService.CloseConnection(connection)
        except Exception as e:
            LoggingService.LogException("Exception in SaveTranscodeFile", e, "TranscodeJobRepository", "SaveTranscodeFile")
            raise

    def UpdateTranscodeFileStatus(self, MediaFileId: int, SuccessfullyTranscoded: bool = None,
                                 AllQualitiesFailed: bool = None, FinalQuality: int = None,
                                 FinalSizeBytes: int = None, FinalFilePath: str = None) -> bool:
        """Update transcoding file status fields."""
        try:
            LoggingService.LogFunctionEntry("UpdateTranscodeFileStatus", "TranscodeJobRepository", MediaFileId, SuccessfullyTranscoded, AllQualitiesFailed)

            # Build dynamic update query
            updateFields = []
            parameters = []

            if SuccessfullyTranscoded is not None:
                updateFields.append("SuccessfullyTranscoded = %s")
                parameters.append(SuccessfullyTranscoded)

            if AllQualitiesFailed is not None:
                updateFields.append("AllQualitiesFailed = %s")
                parameters.append(AllQualitiesFailed)

            if FinalQuality is not None:
                updateFields.append("FinalQuality = %s")
                parameters.append(FinalQuality)

            if FinalSizeBytes is not None:
                updateFields.append("FinalSizeBytes = %s")
                parameters.append(FinalSizeBytes)

            if FinalFilePath is not None:
                updateFields.append("FinalFilePath = %s")
                parameters.append(FinalFilePath)

            if not updateFields:
                LoggingService.LogWarning("No fields to update", "TranscodeJobRepository", "UpdateTranscodeFileStatus")
                return False

            # Add LastAttemptDate update
            updateFields.append("LastAttemptDate = NOW()")

            # Add MediaFileId to parameters for WHERE clause
            parameters.append(MediaFileId)

            query = f"UPDATE TranscodeFiles SET {', '.join(updateFields)} WHERE MediaFileId = %s"

            affectedRows = self.DatabaseService.ExecuteNonQuery(query, parameters)
            LoggingService.LogInfo(f"Updated transcode file status for MediaFileId {MediaFileId}, affected {affectedRows} rows", "TranscodeJobRepository", "UpdateTranscodeFileStatus")
            return affectedRows > 0

        except Exception as e:
            LoggingService.LogException("Exception in UpdateTranscodeFileStatus", e, "TranscodeJobRepository", "UpdateTranscodeFileStatus")
            return False

    # endregion

    # region TranscodeProgress Methods

    def SaveTranscodeProgress(self, TranscodeAttemptId: int, CurrentPhase: str, ProgressPercent: float,
                             CurrentFrame: int, CurrentFPS: float, CurrentBitrate: str,
                             CurrentTime: str, CurrentSpeed: str, ETA: str = "Unknown",
                             TotalFrames: int = 0, AverageFPS: float = 0.0) -> int:
        """Save transcoding progress information in the TranscodeProgress table. Uses single record per transcode with UPDATE."""
        try:
            # Function entry logging removed for frequent progress updates

            # Check if progress record already exists
            existingQuery = "SELECT Id FROM TranscodeProgress WHERE TranscodeAttemptId = %s"
            existingRows = self.DatabaseService.ExecuteQuery(existingQuery, (TranscodeAttemptId,))

            if existingRows:
                # Update existing record
                updateQuery = """
                    UPDATE TranscodeProgress SET
                        CurrentPhase = %s, ProgressPercent = %s, CurrentFrame = %s, CurrentFPS = %s,
                        CurrentBitrate = %s, CurrentTime = %s, CurrentSpeed = %s, ETA = %s,
                        TotalFrames = %s, AverageFPS = %s, LastProgressUpdate = NOW(),
                        LastFrameAdvance = CASE WHEN CurrentFrame != %s THEN NOW() ELSE LastFrameAdvance END
                    WHERE TranscodeAttemptId = %s
                """
                parameters = (CurrentPhase, ProgressPercent, CurrentFrame, CurrentFPS,
                             CurrentBitrate, CurrentTime, CurrentSpeed, ETA,
                             TotalFrames, AverageFPS, CurrentFrame, TranscodeAttemptId)

                result = self.DatabaseService.ExecuteNonQuery(updateQuery, parameters)
                LoggingService.LogDebug(f"Updated progress record for attempt {TranscodeAttemptId}: {CurrentPhase} ({ProgressPercent}%) - Frame: {CurrentFrame}, FPS: {CurrentFPS}, ETA: {ETA}", "TranscodeJobRepository", "SaveTranscodeProgress")
                return result
            else:
                # directive: transcode-flow-canonical -- LastFrameAdvance NULL on CurrentFrame=0
                insertQuery = (
                    "INSERT INTO TranscodeProgress "
                    "(TranscodeAttemptId, PassNumber, PassType, CurrentPhase, ProgressPercent, CurrentFrame, CurrentFPS, "
                    " CurrentBitrate, CurrentTime, CurrentSpeed, ETA, TotalFrames, AverageFPS, LastProgressUpdate, LastFrameAdvance) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NULL) "
                    "RETURNING Id"
                )
                parameters = (TranscodeAttemptId, 1, "Encoding", CurrentPhase, ProgressPercent, CurrentFrame, CurrentFPS,
                             CurrentBitrate, CurrentTime, CurrentSpeed, ETA, TotalFrames, AverageFPS)

                RowsAffected = self.DatabaseService.ExecuteNonQuery(insertQuery, parameters)
                if RowsAffected > 0:
                    progressId = self.DatabaseService.GetLastInsertId()
                    LoggingService.LogDebug(f"Inserted new progress record for attempt {TranscodeAttemptId}: {CurrentPhase} ({ProgressPercent}%) - Frame: {CurrentFrame}, FPS: {CurrentFPS}, ETA: {ETA}", "TranscodeJobRepository", "SaveTranscodeProgress")
                    return progressId
                else:
                    LoggingService.LogError(f"Failed to insert progress record for attempt {TranscodeAttemptId}", "TranscodeJobRepository", "SaveTranscodeProgress")
                    return 0

        except Exception as e:
            LoggingService.LogException("Exception saving transcode progress", e, "TranscodeJobRepository", "SaveTranscodeProgress")
            return 0

    def GetLatestTranscodeProgress(self, TranscodeAttemptId: int) -> Optional[Dict[str, Any]]:
        """Get the latest progress information for a transcoding attempt."""
        try:
            LoggingService.LogFunctionEntry("GetLatestTranscodeProgress", "TranscodeJobRepository", TranscodeAttemptId)

            query = """
                SELECT CurrentPhase, ProgressPercent, CurrentFrame, TotalFrames, CurrentFPS,
                       AverageFPS, CurrentBitrate, CurrentTime, CurrentSpeed, ETA,
                       PassDuration, LastProgressUpdate
                FROM TranscodeProgress
                WHERE TranscodeAttemptId = %s
                ORDER BY LastProgressUpdate DESC
                LIMIT 1
            """

            rows = self.DatabaseService.ExecuteQuery(query, (TranscodeAttemptId,))

            if rows:
                row = rows[0]
                progress = {
                    'CurrentPhase': row['CurrentPhase'],
                    'ProgressPercent': row['ProgressPercent'],
                    'CurrentFrame': row['CurrentFrame'],
                    'TotalFrames': row['TotalFrames'],
                    'CurrentFPS': row['CurrentFPS'],
                    'AverageFPS': row['AverageFPS'],
                    'CurrentBitrate': row['CurrentBitrate'],
                    'CurrentTime': row['CurrentTime'],
                    'CurrentSpeed': row['CurrentSpeed'],
                    'ETA': row['ETA'],
                    'PassDuration': row['PassDuration'],
                    'LastProgressUpdate': row['LastProgressUpdate']
                }
                LoggingService.LogDebug(f"Retrieved latest progress for attempt {TranscodeAttemptId}: {progress['CurrentPhase']} ({progress['ProgressPercent']}%)", "TranscodeJobRepository", "GetLatestTranscodeProgress")
                return progress
            else:
                LoggingService.LogDebug(f"No progress found for attempt {TranscodeAttemptId}", "TranscodeJobRepository", "GetLatestTranscodeProgress")
                return None

        except Exception as e:
            LoggingService.LogException("Exception getting latest transcode progress", e, "TranscodeJobRepository", "GetLatestTranscodeProgress")
            return None

    def GetTranscodeProgressByPhase(self, TranscodeAttemptId: int, CurrentPhase: str) -> Optional[Dict[str, Any]]:
        """Get progress information for a specific phase of a transcoding attempt."""
        try:
            LoggingService.LogFunctionEntry("GetTranscodeProgressByPhase", "TranscodeJobRepository", TranscodeAttemptId, CurrentPhase)

            query = """
                SELECT CurrentPhase, ProgressPercent, CurrentFrame, CurrentFPS,
                       CurrentBitrate, CurrentTime, CurrentSpeed, LastProgressUpdate
                FROM TranscodeProgress
                WHERE TranscodeAttemptId = %s AND CurrentPhase = %s
                ORDER BY LastProgressUpdate DESC
                LIMIT 1
            """

            rows = self.DatabaseService.ExecuteQuery(query, (TranscodeAttemptId, CurrentPhase))

            if rows:
                row = rows[0]
                progress = {
                    'CurrentPhase': row['CurrentPhase'],
                    'ProgressPercent': row['ProgressPercent'],
                    'CurrentFrame': row['CurrentFrame'],
                    'CurrentFPS': row['CurrentFPS'],
                    'CurrentBitrate': row['CurrentBitrate'],
                    'CurrentTime': row['CurrentTime'],
                    'CurrentSpeed': row['CurrentSpeed'],
                    'LastProgressUpdate': row['LastProgressUpdate']
                }
                LoggingService.LogDebug(f"Retrieved progress for attempt {TranscodeAttemptId} phase {CurrentPhase}: {progress['ProgressPercent']}%", "TranscodeJobRepository", "GetTranscodeProgressByPhase")
                return progress
            else:
                LoggingService.LogDebug(f"No progress found for attempt {TranscodeAttemptId} phase {CurrentPhase}", "TranscodeJobRepository", "GetTranscodeProgressByPhase")
                return None

        except Exception as e:
            LoggingService.LogException("Exception getting transcode progress by phase", e, "TranscodeJobRepository", "GetTranscodeProgressByPhase")
            return None

    def GetCurrentTranscodeProgress(self) -> Optional[Dict[str, Any]]:
        """Get the current active transcoding progress (latest progress from any active attempt)."""
        try:
            LoggingService.LogFunctionEntry("GetCurrentTranscodeProgress", "TranscodeJobRepository")

            # directive: path-schema-migration | # see path.S8
            from Core.Path.Path import Path as _PathGCTP, PathError as _PEGCTP
            from Core.Path.PathStorageRoots import GetPrefixMap as _GPMGCTP
            import ntpath as _ntpathGCTP
            _PmGCTP = _GPMGCTP()
            query = (
                "SELECT tp.TranscodeAttemptId, tp.CurrentPhase, tp.ProgressPercent, tp.CurrentFrame, "
                "tp.TotalFrames, tp.CurrentFPS, tp.AverageFPS, tp.CurrentBitrate, "
                "tp.CurrentTime, tp.CurrentSpeed, tp.ETA, tp.PassDuration, "
                "tp.LastProgressUpdate, "
                "ta.StorageRootId AS TaStorageRootId, ta.RelativePath AS TaRelativePath, "
                "ta.Quality, ta.ProfileName, ta.AttemptDate, "
                "mf.TotalFrames as MediaFileTotalFrames, ta.FfpmpegCommand "
                "FROM TranscodeProgress tp "
                "INNER JOIN TranscodeAttempts ta ON tp.TranscodeAttemptId = ta.Id "
                "INNER JOIN TranscodeQueue tq ON ta.MediaFileId = tq.MediaFileId AND tq.Status = 'Running' "
                "LEFT JOIN MediaFiles mf ON ta.MediaFileId = mf.Id "
                "WHERE ta.Success IS NULL "
                "ORDER BY tp.LastProgressUpdate DESC "
                "LIMIT 1"
            )

            result = self.DatabaseService.ExecuteQuery(query)

            if result and len(result) > 0:
                row = result[0]
                _Sid = row.get('tastoragerootid')
                _Rel = row.get('tarelativepath')
                FilePath = ''
                if _Sid is not None:
                    try:
                        FilePath = _PathGCTP(_Sid, _Rel or '').CanonicalDisplay(_PmGCTP)
                    except _PEGCTP:
                        FilePath = ''
                FileName = _ntpathGCTP.basename(FilePath) if FilePath else "Unknown"

                # Use MediaFiles TotalFrames if available, fallback to TranscodeProgress TotalFrames
                MediaFileTotalFrames = row.get('mediafiletotalframes')
                ProgressTotalFrames = row['totalframes']
                ActualTotalFrames = MediaFileTotalFrames if MediaFileTotalFrames else ProgressTotalFrames

                # Recalculate progress percentage if we have better TotalFrames data
                CurrentFrame = row['currentframe']
                RecalculatedProgress = 0.0
                if ActualTotalFrames and ActualTotalFrames > 0 and CurrentFrame > 0:
                    RecalculatedProgress = min((CurrentFrame / ActualTotalFrames) * 100, 95.0)

                progressData = {
                    'Success': True,
                    'AttemptId': row['transcodeattemptid'],
                    'TranscodeAttemptId': row['transcodeattemptid'],
                    'CurrentPhase': row['currentphase'],
                    'ProgressPercent': RecalculatedProgress if RecalculatedProgress > 0 else row['progresspercent'],
                    'CurrentFrame': CurrentFrame,
                    'TotalFrames': ActualTotalFrames,
                    'CurrentFPS': row['currentfps'],
                    'AverageFPS': row['averagefps'],
                    'CurrentBitrate': row['currentbitrate'],
                    'CurrentTime': row['currenttime'],
                    'CurrentSpeed': row['currentspeed'],
                    'ETA': row['eta'],
                    'PassDuration': row['passduration'],
                    'LastUpdate': row['lastprogressupdate'],
                    'LastProgressUpdate': row['lastprogressupdate'],
                    'FilePath': FilePath,
                    'FileName': FileName,
                    'StartTime': row['attemptdate'],
                    'Quality': row['quality'],
                    'ProfileName': row['profilename'],
                    'MediaFileTotalFrames': MediaFileTotalFrames,
                    'RecalculatedProgress': RecalculatedProgress > 0,
                    'Command': row.get('ffpmpegcommand')
                }

                LoggingService.LogDebug(f"Found current progress: {progressData['CurrentPhase']} ({progressData['ProgressPercent']}%) for {progressData['FileName']}", "TranscodeJobRepository", "GetCurrentTranscodeProgress")
                return progressData
            else:
                LoggingService.LogDebug("No current transcoding progress found", "TranscodeJobRepository", "GetCurrentTranscodeProgress")
                return None

        except Exception as e:
            LoggingService.LogException("Exception getting current transcode progress", e, "TranscodeJobRepository", "GetCurrentTranscodeProgress")
            return None

    # directive: path-schema-migration | # see path.S8
    def GetAllCurrentTranscodeProgress(self) -> list:
        """Progress for ALL active transcoding jobs; typed-pair SELECT, Python-synthesized FilePath."""
        try:
            from Core.Path.Path import Path as _PathACTP, PathError as _PEACTP
            from Core.Path.PathStorageRoots import GetPrefixMap as _GPMACTP
            import ntpath as _ntpathACTP
            _PmACTP = _GPMACTP()
            query = (
                "SELECT tp.TranscodeAttemptId, tp.CurrentPhase, tp.ProgressPercent, tp.CurrentFrame, "
                "tp.TotalFrames, tp.CurrentFPS, tp.AverageFPS, tp.CurrentBitrate, "
                "tp.CurrentTime, tp.CurrentSpeed, tp.ETA, tp.PassDuration, "
                "tp.LastProgressUpdate, "
                "ta.StorageRootId AS TaStorageRootId, ta.RelativePath AS TaRelativePath, "
                "ta.Quality, ta.ProfileName, ta.AttemptDate, "
                "mf.TotalFrames as MediaFileTotalFrames, ta.FfpmpegCommand "
                "FROM TranscodeProgress tp "
                "INNER JOIN TranscodeAttempts ta ON tp.TranscodeAttemptId = ta.Id "
                "LEFT JOIN MediaFiles mf ON ta.MediaFileId = mf.Id "
                "WHERE ta.Success IS NULL "
                "ORDER BY tp.LastProgressUpdate DESC"
            )
            results = self.DatabaseService.ExecuteQuery(query)
            if not results:
                return []
            ProgressList = []
            SeenAttempts = set()
            for row in results:
                AttemptId = row['transcodeattemptid']
                if AttemptId in SeenAttempts:
                    continue
                SeenAttempts.add(AttemptId)
                _Sid = row.get('tastoragerootid')
                _Rel = row.get('tarelativepath')
                FilePath = ''
                if _Sid is not None:
                    try:
                        FilePath = _PathACTP(_Sid, _Rel or '').CanonicalDisplay(_PmACTP)
                    except _PEACTP:
                        FilePath = ''
                FileName = _ntpathACTP.basename(FilePath) if FilePath else "Unknown"
                MediaFileTotalFrames = row.get('mediafiletotalframes')
                ProgressTotalFrames = row['totalframes']
                ActualTotalFrames = MediaFileTotalFrames if MediaFileTotalFrames else ProgressTotalFrames
                CurrentFrame = row['currentframe']
                RecalculatedProgress = 0.0
                if ActualTotalFrames and ActualTotalFrames > 0 and CurrentFrame > 0:
                    RecalculatedProgress = min((CurrentFrame / ActualTotalFrames) * 100, 95.0)
                ProgressList.append({
                    'Success': True,
                    'AttemptId': AttemptId,
                    'TranscodeAttemptId': AttemptId,
                    'CurrentPhase': row['currentphase'],
                    'ProgressPercent': RecalculatedProgress if RecalculatedProgress > 0 else row['progresspercent'],
                    'CurrentFrame': CurrentFrame,
                    'TotalFrames': ActualTotalFrames,
                    'CurrentFPS': row['currentfps'],
                    'AverageFPS': row['averagefps'],
                    'CurrentBitrate': row['currentbitrate'],
                    'CurrentTime': row['currenttime'],
                    'CurrentSpeed': row['currentspeed'],
                    'ETA': row['eta'],
                    'PassDuration': row['passduration'],
                    'LastUpdate': row['lastprogressupdate'],
                    'LastProgressUpdate': row['lastprogressupdate'],
                    'FilePath': FilePath,
                    'FileName': FileName,
                    'StartTime': row['attemptdate'],
                    'Quality': row['quality'],
                    'ProfileName': row['profilename'],
                    'MediaFileTotalFrames': MediaFileTotalFrames,
                    'RecalculatedProgress': RecalculatedProgress > 0,
                    'Command': row.get('ffpmpegcommand')
                })
            return ProgressList
        except Exception as e:
            LoggingService.LogException("Exception getting all current transcode progress", e, "TranscodeJobRepository", "GetAllCurrentTranscodeProgress")
            return []

    def DeleteTranscodeProgress(self, TranscodeAttemptId: int) -> bool:
        """Delete all progress records for a specific transcoding attempt."""
        try:
            LoggingService.LogFunctionEntry("DeleteTranscodeProgress", "TranscodeJobRepository", TranscodeAttemptId)

            query = "DELETE FROM TranscodeProgress WHERE TranscodeAttemptId = %s"
            rowsAffected = self.DatabaseService.ExecuteNonQuery(query, (TranscodeAttemptId,))

            LoggingService.LogInfo(f"Deleted {rowsAffected} progress records for attempt {TranscodeAttemptId}", "TranscodeJobRepository", "DeleteTranscodeProgress")
            return True

        except Exception as e:
            LoggingService.LogException("Exception deleting transcode progress", e, "TranscodeJobRepository", "DeleteTranscodeProgress")
            return False

    def CleanupOldProgressData(self, DaysToKeep: int = 7) -> int:
        """Clean up old progress data to keep the table manageable."""
        try:
            LoggingService.LogFunctionEntry("CleanupOldProgressData", "TranscodeJobRepository", DaysToKeep)

            query = """
                DELETE FROM TranscodeProgress
                WHERE LastProgressUpdate < NOW() - INTERVAL '{} days'
            """.format(DaysToKeep)

            rowsAffected = self.DatabaseService.ExecuteNonQuery(query)

            LoggingService.LogInfo(f"Cleaned up {rowsAffected} old progress records (older than {DaysToKeep} days)", "TranscodeJobRepository", "CleanupOldProgressData")
            return rowsAffected

        except Exception as e:
            LoggingService.LogException("Exception cleaning up old progress data", e, "TranscodeJobRepository", "CleanupOldProgressData")
            return 0

    # endregion

    # region Transcoding Support Methods

    def GetKeepSourceSetting(self, TranscodeAttemptId: int) -> Optional[bool]:
        """Get the KeepSource setting for a transcode attempt."""
        try:
            # Get the KeepSource setting directly from MediaFiles table
            query = '''
            SELECT mf.KeepSource
            FROM MediaFiles mf
            JOIN TranscodeAttempts ta ON ta.MediaFileId = mf.Id
            WHERE ta.Id = %s
            '''
            result = self.DatabaseService.ExecuteQuery(query, (TranscodeAttemptId,))

            if result:
                return bool(result[0]['keepsource'])
            return None

        except Exception as e:
            LoggingService.LogException(f"Exception getting KeepSource setting for transcode attempt {TranscodeAttemptId}", e,
                                      "TranscodeJobRepository", "GetKeepSourceSetting")
            return None

    def GetTranscodeDestinationSummary(self) -> Dict[str, Any]:
        """Aggregate destination formats from transcode logs to show what Jellyfin transcodes TO."""
        try:
            query = """
                SELECT DestResolution, DestProfile, DestLevel, DestPixelFormat, DestFormat,
                       COUNT(*) as Count
                FROM JellyfinOperations
                WHERE OperationType = 'Transcode'
                  AND (DestResolution != '' OR DestProfile != '' OR DestLevel != '')
                GROUP BY DestResolution, DestProfile, DestLevel, DestPixelFormat, DestFormat
                ORDER BY Count DESC
            """
            rows = self.DatabaseService.ExecuteQuery(query)
            formats = []
            for row in rows:
                formats.append({
                    "DestResolution": row['destresolution'] or "",
                    "DestProfile": row['destprofile'] or "",
                    "DestLevel": row['destlevel'] or "",
                    "DestPixelFormat": row['destpixelformat'] or "",
                    "DestFormat": row['destformat'] or "",
                    "Count": row['count']
                })
            totalWithDest = sum(f["Count"] for f in formats)
            return {"Success": True, "Formats": formats, "TotalWithDestInfo": totalWithDest}
        except Exception as e:
            LoggingService.LogException("Error getting transcode destination summary", e, "DatabaseManager", "GetTranscodeDestinationSummary")
            return {"Success": False, "ErrorMessage": str(e)}

            return None
