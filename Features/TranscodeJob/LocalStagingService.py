import os
import shutil
from typing import Any, Dict, Optional

from Core.Database.DatabaseService import DatabaseService
from Core.Path.LocalPath import LocalBasename, LocalDirname, LocalExists, LocalGetSize, LocalIsDir, LocalJoin
from Features.TranscodeJob.LocalStagingConfigRepository import LocalStagingConfigRepository
from Services.LoggingService import LoggingService


# directive: local-staging | # see local-staging.C3
class LocalStagingService:
    """Decides + executes worker-local source staging; SRP-compliant; fresh DB reads per call."""

    def __init__(self, DatabaseServiceInstance: Optional[DatabaseService] = None):
        self.DatabaseService = DatabaseServiceInstance or DatabaseService()
        self.ConfigRepo = LocalStagingConfigRepository(self.DatabaseService)

    # directive: local-staging | # see local-staging.C5
    def ShouldStage(self, WorkerName: str, SourceSizeMB: float) -> bool:
        """Three-way gate: worker opted in + scratch dir set + source >= MinSizeMB; fresh read per call."""
        try:
            WorkerConfig = self._GetWorkerStagingConfig(WorkerName)
            if not WorkerConfig:
                return False
            if not WorkerConfig.get('LocalStagingEnabled'):
                return False
            ScratchDir = (WorkerConfig.get('LocalScratchDir') or '').strip()
            if not ScratchDir:
                return False
            MinSizeMB = int(self.ConfigRepo.Get().get('MinSizeMB', 500))
            if float(SourceSizeMB or 0) < MinSizeMB:
                return False
            return True
        except Exception as Ex:
            LoggingService.LogException("ShouldStage failed -- defaulting to direct encode", Ex, "LocalStagingService", "ShouldStage")
            return False

    # directive: local-staging | # see local-staging.C5
    def IsLocalVmafFirst(self, WorkerName: str) -> bool:
        """Returns True iff Worker.LocalVmafFirst AND Worker.QualityTestEnabled (both required for Mode A)."""
        try:
            Rows = self.DatabaseService.ExecuteQuery("SELECT LocalVmafFirst, QualityTestEnabled FROM Workers WHERE WorkerName = %s", (WorkerName,))
            if not Rows:
                return False
            R = Rows[0]
            return bool(R.get('localvmaffirst')) and bool(R.get('qualitytestenabled'))
        except Exception as Ex:
            LoggingService.LogException(f"IsLocalVmafFirst failed for {WorkerName}", Ex, "LocalStagingService", "IsLocalVmafFirst")
            return False

    # directive: local-staging | # see local-staging.C7
    def StageSource(self, WorkerName: str, MediaFileId: int, CanonicalLocalSourcePath: str) -> Optional[str]:
        """Copy source to per-job scratch subdir; returns local staged path or None on failure."""
        try:
            WorkerConfig = self._GetWorkerStagingConfig(WorkerName)
            if not WorkerConfig:
                return None
            ScratchDir = (WorkerConfig.get('LocalScratchDir') or '').strip()
            if not ScratchDir:
                return None
            JobScratchDir = LocalJoin(ScratchDir, str(MediaFileId))
            os.makedirs(JobScratchDir, exist_ok=True)
            BaseName = LocalBasename(CanonicalLocalSourcePath)
            StagedPath = LocalJoin(JobScratchDir, BaseName)
            LoggingService.LogInfo(f"Staging source for MediaFileId={MediaFileId}: {CanonicalLocalSourcePath} -> {StagedPath}", "LocalStagingService", "StageSource")
            shutil.copy2(CanonicalLocalSourcePath, StagedPath)
            SrcSize = LocalGetSize(CanonicalLocalSourcePath)
            DstSize = LocalGetSize(StagedPath)
            if SrcSize != DstSize:
                LoggingService.LogError(f"Staged copy size mismatch: source={SrcSize} bytes, staged={DstSize} bytes; cleanup + return None", "LocalStagingService", "StageSource")
                self.Cleanup(StagedPath)
                return None
            LoggingService.LogInfo(f"Stage complete: {DstSize} bytes copied to {StagedPath}", "LocalStagingService", "StageSource")
            return StagedPath
        except Exception as Ex:
            LoggingService.LogException(f"StageSource failed for MediaFileId={MediaFileId}", Ex, "LocalStagingService", "StageSource")
            return None

    # directive: local-staging | # see local-staging.C7
    def ResolveLocalOutputPath(self, WorkerName: str, MediaFileId: int, OutputBasename: str) -> Optional[str]:
        """Compose the local .inprogress output path inside the per-job scratch subdir."""
        try:
            WorkerConfig = self._GetWorkerStagingConfig(WorkerName)
            if not WorkerConfig:
                return None
            ScratchDir = (WorkerConfig.get('LocalScratchDir') or '').strip()
            if not ScratchDir:
                return None
            return LocalJoin(LocalJoin(ScratchDir, str(MediaFileId)), OutputBasename)
        except Exception as Ex:
            LoggingService.LogException(f"ResolveLocalOutputPath failed for MediaFileId={MediaFileId}", Ex, "LocalStagingService", "ResolveLocalOutputPath")
            return None

    # directive: local-staging | # see local-staging.C11
    def Cleanup(self, LocalPath: Optional[str]) -> bool:
        """Idempotent delete of a local scratch file; returns True on success/no-op. Empty subdirs are swept by crash recovery."""
        try:
            if not LocalPath:
                return True
            if LocalExists(LocalPath) and not LocalIsDir(LocalPath):
                os.remove(LocalPath)
                LoggingService.LogInfo(f"Cleaned local scratch file: {LocalPath}", "LocalStagingService", "Cleanup")
            return True
        except Exception as Ex:
            LoggingService.LogException(f"Cleanup failed for {LocalPath}", Ex, "LocalStagingService", "Cleanup")
            return False

    # directive: local-staging | # see local-staging.C11
    def CleanupJobScratchDir(self, WorkerName: str, MediaFileId: int) -> bool:
        """Remove the per-job scratch subdir + all its contents; idempotent."""
        try:
            WorkerConfig = self._GetWorkerStagingConfig(WorkerName)
            if not WorkerConfig:
                return True
            ScratchDir = (WorkerConfig.get('LocalScratchDir') or '').strip()
            if not ScratchDir:
                return True
            JobScratchDir = LocalJoin(ScratchDir, str(MediaFileId))
            if LocalExists(JobScratchDir) and LocalIsDir(JobScratchDir):
                shutil.rmtree(JobScratchDir, ignore_errors=True)
                LoggingService.LogInfo(f"Removed per-job scratch dir: {JobScratchDir}", "LocalStagingService", "CleanupJobScratchDir")
            return True
        except Exception as Ex:
            LoggingService.LogException(f"CleanupJobScratchDir failed for MediaFileId={MediaFileId}", Ex, "LocalStagingService", "CleanupJobScratchDir")
            return False

    def _GetWorkerStagingConfig(self, WorkerName: str) -> Optional[Dict[str, Any]]:
        """Fresh DB read of the three Workers staging columns (R3 + db-is-authority compliant)."""
        try:
            Rows = self.DatabaseService.ExecuteQuery("SELECT LocalScratchDir, LocalStagingEnabled, LocalVmafFirst FROM Workers WHERE WorkerName = %s", (WorkerName,))
            if not Rows:
                return None
            R = Rows[0]
            return {"LocalScratchDir": R.get('localscratchdir'), "LocalStagingEnabled": bool(R.get('localstagingenabled')), "LocalVmafFirst": bool(R.get('localvmaffirst'))}
        except Exception as Ex:
            LoggingService.LogException(f"_GetWorkerStagingConfig failed for {WorkerName}", Ex, "LocalStagingService", "_GetWorkerStagingConfig")
            return None
