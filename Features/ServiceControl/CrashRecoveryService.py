#!/usr/bin/env python3
import os
from typing import Dict, Optional
from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalExists
from Services.ProcessManagementService import ProcessManagementService
from Features.ServiceControl.ActiveJobRepository import ActiveJobRepository
from Features.TranscodeJob.TranscodeJobRepository import TranscodeJobRepository


# directive: crash-recovery-audiofix-type | # see workerservice.ST5
class CrashRecoveryService:
    """Boot-time recovery: releases everything the database says this worker still owns from a prior run."""

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def __init__(self, DatabaseManagerInstance, WorkerName: str, ActiveJobRepositoryInstance: Optional[ActiveJobRepository] = None):
        if not WorkerName:
            raise ValueError("CrashRecoveryService requires a WorkerName")
        self.DatabaseManager = DatabaseManagerInstance
        self.ProcessManager = ProcessManagementService()
        self.WorkerName = WorkerName
        self.ActiveJobRepository = ActiveJobRepositoryInstance or ActiveJobRepository()

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def RecoverOwnedJobs(self) -> Dict:
        """Release this worker's leftover jobs by ownership; a failed database write raises and stops the boot."""
        Db = self.DatabaseManager.DatabaseService
        ProcessesKilled = self._KillLeftoverProcesses()
        AttemptsFailed = TranscodeJobRepository(Db).MarkInflightAttemptsCrashedForWorker(self.WorkerName)
        ProgressDeleted = Db.ExecuteNonQuery(
            "DELETE FROM TranscodeProgress WHERE TranscodeAttemptId IN ("
            "SELECT Id FROM TranscodeAttempts WHERE WorkerName = %s AND Success = FALSE)",
            (self.WorkerName,),
        )
        JobsReleased = Db.ExecuteNonQuery(
            "UPDATE TranscodeQueue tq "
            "SET Status = 'Pending', DateStarted = NULL, ClaimedBy = NULL, ClaimedAt = NULL "
            "WHERE tq.ClaimedBy = %s AND tq.Status = 'Running' "
            "AND NOT EXISTS (SELECT 1 FROM TranscodeAttempts ta WHERE ta.MediaFileId = tq.MediaFileId AND ta.Success IS NULL)",
            (self.WorkerName,),
        )
        # see worker-lifecycle.feature.md C11/C12
        InProgressFilesCleaned, PartialReplacementsCompleted = self._RecoverInProgressArtifacts()
        LocalStagingOrphansCleaned = self._SweepLocalStagingOrphans()
        Result = {
            "JobsReleased": JobsReleased,
            "AttemptsFailed": AttemptsFailed,
            "ProgressDeleted": ProgressDeleted,
            "ProcessesKilled": ProcessesKilled,
            "InProgressFilesCleaned": InProgressFilesCleaned,
            "PartialReplacementsCompleted": PartialReplacementsCompleted,
            "LocalStagingOrphansCleaned": LocalStagingOrphansCleaned,
        }
        LoggingService.LogInfo(f"Crash recovery completed for {self.WorkerName}: {Result}", "CrashRecoveryService", "RecoverOwnedJobs")
        return Result

    # directive: crash-recovery-audiofix-type | # see workerservice.ST5
    def _KillLeftoverProcesses(self) -> int:
        """Kill a still-running process recorded on this worker's leftover ActiveJobs rows; never this process."""
        Query = ActiveJobRepository.BuildActiveJobsQuery("TranscodeService", WorkerName=self.WorkerName, RunningOnly=False)
        Killed = 0
        for Job in self.ActiveJobRepository.GetActiveJobsByService(Query):
            ProcessId = Job.get('ProcessId')
            # see workerservice.C10 -- a recorded PID equal to our own is a reused PID from the prior run
            if not ProcessId or ProcessId == os.getpid():
                continue
            if not self.ProcessManager.IsProcessRunning(ProcessId):
                continue
            if self.ProcessManager.KillProcess(ProcessId, Graceful=True):
                Killed += 1
                LoggingService.LogWarning(f"Killed leftover process {ProcessId} for ActiveJobs row {Job.get('Id')}", "CrashRecoveryService", "_KillLeftoverProcesses")
            else:
                LoggingService.LogError(f"Failed to kill leftover process {ProcessId} for ActiveJobs row {Job.get('Id')}", "CrashRecoveryService", "_KillLeftoverProcesses")
        return Killed

    # directive: crash-recovery-audiofix-type | # see worker-lifecycle.C11
    def _RecoverInProgressArtifacts(self) -> tuple:
        """Sweep disk artifacts of this worker's terminal attempts: finalize a partial replacement (C12), else delete the leftover .ip (C11). Returns (InProgressFilesDeleted, PartialReplacementsCompleted)."""
        try:
            # directive: path-schema-migration | # see path.S8
            from Core.Path.Path import Path as _PathCR, PathError as _PECR
            from Core.Path.PathStorageRoots import GetPrefixMap as _GPMCR
            from Core.Path.Worker import Worker as _WorkerCR
            _PmCR = _GPMCR()
            _CtxCR = _WorkerCR.Current(Db=self.DatabaseManager.DatabaseService)
            # Only surface actual orphans: encode terminal AND no VMAF pending. Two conditions live in the WHERE clause where the data lives; the loop iterates real orphans only.
            Query = (
                "SELECT tfp.Id AS tfp_id, tfp.TranscodeAttemptId AS ta_id, "
                "tfp.SourceStorageRootId AS src_sid, tfp.SourceRelativePath AS src_rel, "
                "tfp.OutputStorageRootId AS out_sid, tfp.OutputRelativePath AS out_rel "
                "FROM TemporaryFilePaths tfp "
                "JOIN TranscodeAttempts ta ON ta.Id = tfp.TranscodeAttemptId "
                "LEFT JOIN QualityTestingQueue qtq "
                "  ON qtq.TranscodeAttemptId = ta.Id AND qtq.DateCompleted IS NULL "
                "WHERE ta.WorkerName = %s "
                "  AND ta.Success IS NOT NULL "
                "  AND qtq.Id IS NULL"
            )
            Rows = self.DatabaseManager.DatabaseService.ExecuteQuery(Query, (self.WorkerName,))
            if not Rows:
                return 0, 0

            InProgressDeleted = 0
            PartialCompleted = 0

            for Row in Rows:
                SrcSid = Row.get('src_sid')
                SrcRel = Row.get('src_rel')
                OutSid = Row.get('out_sid')
                OutRel = Row.get('out_rel')
                LocalSource = ''
                LocalOutput = ''
                CanonicalOriginal = ''
                try:
                    if SrcSid is not None and SrcRel is not None and _CtxCR is not None:
                        _SrcP = _PathCR(SrcSid, SrcRel)
                        LocalSource = _SrcP.Resolve(_CtxCR)
                        CanonicalOriginal = _SrcP.CanonicalDisplay(_PmCR)
                    if OutSid is not None and OutRel is not None and _CtxCR is not None:
                        _OutP = _PathCR(OutSid, OutRel)
                        LocalOutput = _OutP.Resolve(_CtxCR)
                except _PECR:
                    continue
                if not LocalOutput:
                    continue

                # OutputRelativePath stores the final path; the .ip variant lives next to it on disk during encode.
                FinalPath = LocalOutput[:-len('.ip')] if LocalOutput.endswith('.ip') else LocalOutput
                InProgressPath = FinalPath + '.ip'

                FinalExists = LocalExists(FinalPath)
                OriginalExists = bool(LocalSource) and LocalExists(LocalSource)
                InProgressExists = LocalExists(InProgressPath)

                if FinalExists and OriginalExists and CanonicalOriginal:
                    try:
                        from Features.FileReplacement.TranscodedOutputPlacement import TranscodedOutputPlacement
                        Top = TranscodedOutputPlacement(self.DatabaseManager, WorkerName=self.WorkerName)
                        FinalizeResult = Top.FinalizePartialReplacement(
                            OriginalLocalPath=LocalSource,
                            FinalLocalPath=FinalPath,
                            CanonicalOriginalPath=CanonicalOriginal,
                        )
                        if FinalizeResult.get('Success'):
                            PartialCompleted += 1
                            LoggingService.LogWarning(
                                f"Crash recovery: completed partial replacement for {LocalSource} -> {FinalPath}",
                                "CrashRecoveryService", "_RecoverInProgressArtifacts"
                            )
                    except Exception as FinalizeEx:
                        LoggingService.LogException(
                            f"Crash recovery: FinalizePartialReplacement failed for {FinalPath}",
                            FinalizeEx, "CrashRecoveryService", "_RecoverInProgressArtifacts"
                        )

                # Row selection already guarantees terminal-attempt + no-pending-QT. Delete unconditionally when file exists.
                if InProgressExists:
                    try:
                        os.remove(InProgressPath)
                        InProgressDeleted += 1
                        LoggingService.LogWarning(
                            f"Crash recovery: deleted orphaned .ip file {InProgressPath}",
                            "CrashRecoveryService", "_RecoverInProgressArtifacts"
                        )
                    except Exception as RmEx:
                        LoggingService.LogException(
                            f"Crash recovery: could not delete .ip {InProgressPath}",
                            RmEx, "CrashRecoveryService", "_RecoverInProgressArtifacts"
                        )

            return InProgressDeleted, PartialCompleted
        except Exception as e:
            LoggingService.LogException(
                "Error during _RecoverInProgressArtifacts",
                e, "CrashRecoveryService", "_RecoverInProgressArtifacts"
            )
            return 0, 0

    # directive: crash-recovery-audiofix-type | # see local-staging.C12
    def _SweepLocalStagingOrphans(self) -> int:
        """Delete orphaned per-job scratch subdirs under this worker's LocalScratchDir; orphan = no in-flight TFP row for that MediaFileId."""
        try:
            from Core.Path.LocalPath import LocalIsDir, LocalJoin
            Rows = self.DatabaseManager.DatabaseService.ExecuteQuery("SELECT LocalScratchDir FROM Workers WHERE WorkerName = %s", (self.WorkerName,))
            if not Rows:
                return 0
            ScratchDir = (Rows[0].get('localscratchdir') or '').strip()
            if not ScratchDir or not LocalExists(ScratchDir):
                return 0
            import shutil as _shutil
            Swept = 0
            try:
                Entries = os.listdir(ScratchDir)
            except Exception as ListEx:
                LoggingService.LogException(f"Crash recovery: cannot list LocalScratchDir {ScratchDir}", ListEx, "CrashRecoveryService", "_SweepLocalStagingOrphans")
                return 0
            for Name in Entries:
                if not Name.isdigit():
                    continue
                SubPath = LocalJoin(ScratchDir, Name)
                if not LocalIsDir(SubPath):
                    continue
                MediaFileId = int(Name)
                InFlight = self.DatabaseManager.DatabaseService.ExecuteQuery(
                    "SELECT 1 FROM TemporaryFilePaths tfp JOIN TranscodeAttempts ta ON ta.Id = tfp.TranscodeAttemptId "
                    "WHERE ta.MediaFileId = %s AND ta.WorkerName = %s AND ta.Success IS NULL LIMIT 1",
                    (MediaFileId, self.WorkerName),
                )
                if InFlight:
                    continue
                try:
                    _shutil.rmtree(SubPath, ignore_errors=True)
                    Swept += 1
                    LoggingService.LogWarning(f"Crash recovery: swept local-staging orphan {SubPath} for MediaFileId={MediaFileId}", "CrashRecoveryService", "_SweepLocalStagingOrphans")
                except Exception as RmEx:
                    LoggingService.LogException(f"Crash recovery: could not remove orphan scratch dir {SubPath}", RmEx, "CrashRecoveryService", "_SweepLocalStagingOrphans")
            return Swept
        except Exception as Ex:
            LoggingService.LogException("Error during _SweepLocalStagingOrphans", Ex, "CrashRecoveryService", "_SweepLocalStagingOrphans")
            return 0
