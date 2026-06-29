from typing import Optional, Dict, Any
from datetime import datetime, timezone
from Core.Logging.LoggingService import LoggingService
from Core.Models.TranscodeAttemptModel import TranscodeAttemptModel
from Core.Models.TranscodeFileModel import TranscodeFileModel


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C9
class AttemptRecordService:
    """Single-responsibility service for TranscodeAttempts CRUD + frame-total fallback."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C9
    def __init__(self, DatabaseManager, WorkerName: str):
        """Inject DatabaseManager + worker identity (used when populating WorkerName column)."""
        self.DatabaseManager = DatabaseManager
        self.WorkerName = WorkerName

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C9
    def Create(self, Job, MediaFile=None, TranscodingSettings: Optional[Dict[str, Any]] = None, TranscodeCommand: Optional[str] = None) -> Optional[int]:
        """Create a TranscodeAttempts row; returns the new attempt id or None on failure."""
        try:
            if TranscodingSettings is None:
                TranscodingSettings = {}
            if MediaFile is None:
                MediaFile = type('MockMediaFile', (), {'AssignedProfile': None})()

            ProfileSettings = TranscodingSettings.get('ProfileSettings', {})

            # see post-transcode-disposition.C30 | see post-transcode-disposition.S1
            ProfileName = MediaFile.AssignedProfile if hasattr(MediaFile, 'AssignedProfile') else None
            QualityTestRequiredForProfile = True
            if ProfileName:
                # allow: R12 SQL preexisting; relocate to ProfilesRepository in follow-up
                ProfileRow = self.DatabaseManager.DatabaseService.ExecuteQuery(
                    "SELECT qualitytestrequired FROM profiles WHERE profilename = %s LIMIT 1",
                    (ProfileName,),
                )
                if ProfileRow:
                    QualityTestRequiredForProfile = bool(ProfileRow[0].get('QualityTestRequired'))

            # directive: failure-accounting | # see failure-accounting.C5
            JobMode = (getattr(Job, 'ProcessingMode', None) or 'Transcode').strip()
            # directive: transcode-worker-unification | # see transcode.ST6
            RemuxModes = frozenset(R['Name'] for R in self.DatabaseManager.ExecuteQuery("SELECT Name FROM ProcessingModes WHERE ClaimCapabilityFlag = 'RemuxEnabled'"))
            if JobMode in RemuxModes and not ProfileName:
                ProfileName = JobMode

            Attempt = TranscodeAttemptModel(
                StorageRootId=Job.StorageRootId,
                RelativePath=Job.RelativePath,
                AttemptDate=datetime.now(timezone.utc),
                Quality=ProfileSettings.get('Quality', 0),
                OldSizeBytes=Job.SizeBytes,
                NewSizeBytes=0,
                Success=None,
                SizeReductionBytes=0,
                SizeReductionPercent=0.0,
                ErrorMessage=None,
                TranscodeDurationSeconds=0.0,
                FfpmpegCommand=TranscodeCommand,
                AudioBitrateKbps=ProfileSettings.get('AudioBitrateKbps'),
                VideoBitrateKbps=ProfileSettings.get('VideoBitrateKbps'),
                ProfileName=ProfileName,
                VMAF=None,
                QualityTestRequired=QualityTestRequiredForProfile,
                QualityTestCompleted=False,
                StartTime=TranscodingSettings.get('StartTime') if TranscodingSettings else None,
                WorkerName=self.WorkerName,
                MediaFileId=getattr(Job, 'MediaFileId', None),
            )

            return self.DatabaseManager.SaveTranscodeAttempt(Attempt)

        except Exception as e:
            LoggingService.LogException("Exception creating transcode attempt", e, "AttemptRecordService", "Create")
            return None

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C9
    def UpdateTranscodeFile(self, FilePath: str, TranscodeAttemptId: int, IsSuccess: bool, FinalFilePath: str = None, FinalSizeBytes: int = None, MediaFileId: int = None) -> None:
        """Update or create TranscodeFiles row for the file; preserves verbatim semantics of UpdateTranscodeFileRecord."""
        try:
            LoggingService.LogFunctionEntry("UpdateTranscodeFile", "AttemptRecordService",
                                          FilePath, TranscodeAttemptId, IsSuccess)

            if not MediaFileId:
                MediaFileId = self.DatabaseManager.LookupMediaFileId(FilePath)

            Attempt = self.DatabaseManager.GetTranscodeAttemptById(TranscodeAttemptId)
            if not Attempt:
                LoggingService.LogWarning(f"Could not retrieve attempt {TranscodeAttemptId} for TranscodeFiles update",
                                        "AttemptRecordService", "UpdateTranscodeFile")
                return

            ExistingTranscodeFile = self.DatabaseManager.GetTranscodeFileByMediaFileId(MediaFileId) if MediaFileId else None

            if ExistingTranscodeFile:
                LoggingService.LogInfo(f"Updating existing TranscodeFile record for {FilePath}",
                                     "AttemptRecordService", "UpdateTranscodeFile")

                if IsSuccess:
                    self.DatabaseManager.UpdateTranscodeFileStatus(
                        MediaFileId=MediaFileId,
                        SuccessfullyTranscoded=True,
                        FinalQuality=Attempt.Quality,
                        FinalSizeBytes=FinalSizeBytes,
                        FinalFilePath=FinalFilePath
                    )
                    TranscodeFile = TranscodeFileModel(
                        Id=ExistingTranscodeFile.Id,
                        FilePath=FilePath,
                        AllQualitiesFailed=ExistingTranscodeFile.AllQualitiesFailed,
                        SuccessfullyTranscoded=True,
                        FirstAttemptDate=ExistingTranscodeFile.FirstAttemptDate,
                        LastAttemptDate=datetime.now(timezone.utc),
                        SuccessDate=datetime.now(timezone.utc),
                        FinalQuality=Attempt.Quality,
                        FinalSizeBytes=FinalSizeBytes,
                        TotalAttempts=ExistingTranscodeFile.TotalAttempts + 1,
                        OriginalFilePath=ExistingTranscodeFile.OriginalFilePath,
                        FinalFilePath=FinalFilePath
                    )
                    self.DatabaseManager.SaveTranscodeFile(TranscodeFile)
                else:
                    TranscodeFile = TranscodeFileModel(
                        Id=ExistingTranscodeFile.Id,
                        FilePath=FilePath,
                        AllQualitiesFailed=ExistingTranscodeFile.AllQualitiesFailed,
                        SuccessfullyTranscoded=ExistingTranscodeFile.SuccessfullyTranscoded,
                        FirstAttemptDate=ExistingTranscodeFile.FirstAttemptDate,
                        LastAttemptDate=datetime.now(timezone.utc),
                        SuccessDate=ExistingTranscodeFile.SuccessDate,
                        FinalQuality=ExistingTranscodeFile.FinalQuality,
                        FinalSizeBytes=ExistingTranscodeFile.FinalSizeBytes,
                        TotalAttempts=ExistingTranscodeFile.TotalAttempts + 1,
                        OriginalFilePath=ExistingTranscodeFile.OriginalFilePath,
                        FinalFilePath=ExistingTranscodeFile.FinalFilePath
                    )
                    self.DatabaseManager.SaveTranscodeFile(TranscodeFile)
            else:
                LoggingService.LogInfo(f"Creating new TranscodeFile record for {FilePath}",
                                     "AttemptRecordService", "UpdateTranscodeFile")

                CurrentTime = datetime.now(timezone.utc)
                TranscodeFile = TranscodeFileModel(
                    FilePath=FilePath,
                    AllQualitiesFailed=not IsSuccess,
                    SuccessfullyTranscoded=IsSuccess,
                    FirstAttemptDate=CurrentTime,
                    LastAttemptDate=CurrentTime,
                    SuccessDate=CurrentTime if IsSuccess else None,
                    FinalQuality=Attempt.Quality if IsSuccess else None,
                    FinalSizeBytes=FinalSizeBytes if IsSuccess else None,
                    TotalAttempts=1,
                    OriginalFilePath=FilePath,
                    FinalFilePath=FinalFilePath if IsSuccess else None
                )
                self.DatabaseManager.SaveTranscodeFile(TranscodeFile)

            LoggingService.LogInfo(f"TranscodeFile record updated for {FilePath}, Success: {IsSuccess}",
                                 "AttemptRecordService", "UpdateTranscodeFile")

        except Exception as e:
            LoggingService.LogException("Exception updating TranscodeFile record", e,
                                      "AttemptRecordService", "UpdateTranscodeFile")

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C9
    def GetTotalFrames(self, Job, MediaFile=None) -> int:
        """Resolve the total frame count via FFprobe with a fallback to MediaFile.TotalFrames."""
        try:
            LoggingService.LogInfo(f"MediaFile.TotalFrames is empty for {Job.FilePath}, attempting ffprobe fallback",
                                 "AttemptRecordService", "GetTotalFrames")

            from Services.FFmpegAnalysisService import FFmpegAnalysisService

            AnalysisService = FFmpegAnalysisService()
            AnalysisResult = AnalysisService.AnalyzeMediaFile(Job.FilePath)

            if AnalysisResult.Success and AnalysisResult.TotalFrames and AnalysisResult.TotalFrames > 0:
                LoggingService.LogInfo(f"Successfully extracted TotalFrames via ffprobe: {AnalysisResult.TotalFrames} frames",
                                     "AttemptRecordService", "GetTotalFrames")

                if MediaFile:
                    MediaFile.TotalFrames = AnalysisResult.TotalFrames
                    self.DatabaseManager.SaveMediaFile(MediaFile)
                    LoggingService.LogInfo(f"Updated MediaFile.TotalFrames to {AnalysisResult.TotalFrames} for future transcodes",
                                         "AttemptRecordService", "GetTotalFrames")

                return AnalysisResult.TotalFrames
            else:
                LoggingService.LogWarning(f"Both MediaFile.TotalFrames and ffprobe failed to extract TotalFrames for {Job.FilePath}. " +
                                        f"MediaFile.TotalFrames: {MediaFile.TotalFrames if MediaFile else 'N/A'}, " +
                                        f"FFprobe result: {AnalysisResult.TotalFrames if AnalysisResult else 'Failed'}",
                                        "AttemptRecordService", "GetTotalFrames")
                return 0

        except Exception as e:
            LoggingService.LogException("Exception getting TotalFrames with fallback", e, "AttemptRecordService", "GetTotalFrames")
            return 0
