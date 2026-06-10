import os
import shutil
from typing import Optional, Tuple
from Core.Logging.LoggingService import LoggingService
from Core.Path import Path, Worker
from Core.Path.LocalPath import LocalBasename, LocalDirname, LocalExists, LocalGetSize


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C11
class LocalStagingAdapter:
    """Mediates JobProcessor access to Mode A / Mode B staging; wraps existing LocalStagingService."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C11
    def __init__(self, DatabaseManager, WorkerName: str):
        """Inject DB + worker identity (LocalStagingConfig is per-worker)."""
        self.DatabaseManager = DatabaseManager
        self.WorkerName = WorkerName

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C11
    def ResolveTfpPathParts(self, Job, OutputPath: str):
        """Return (SrcStorageRootId, SrcRel, OutStorageRootId, OutRel) typed pairs for the TFP row."""
        SrcId = getattr(Job, 'StorageRootId', None)
        SrcRel = getattr(Job, 'RelativePath', None) or None
        OutBase = LocalBasename(OutputPath) if OutputPath else ''
        OutId = SrcId
        SrcDirRel = SrcRel.rsplit('/', 1)[0] if (SrcRel and '/' in SrcRel) else ''
        OutRel = f"{SrcDirRel}/{OutBase}" if SrcDirRel else OutBase
        OutRel = OutRel or None
        return SrcId, SrcRel, OutId, OutRel

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C11
    def GetLocalStagingPathsIfActive(self, EffectiveInputPath: str, OutputPath: str) -> Tuple[Optional[str], Optional[str]]:
        """Return (LocalSourcePath, LocalOutputPath) iff EffectiveInputPath lies under this worker's LocalScratchDir; else (None, None)."""
        try:
            Rows = self.DatabaseManager.DatabaseService.ExecuteQuery("SELECT LocalScratchDir FROM Workers WHERE WorkerName = %s", (self.WorkerName,))
            if not Rows:
                return (None, None)
            ScratchDir = (Rows[0].get('localscratchdir') or '').strip()
            if not ScratchDir:
                return (None, None)
            EffStr = str(EffectiveInputPath or '')
            if EffStr.startswith(ScratchDir):
                return (EffStr, str(OutputPath) if OutputPath else None)
            return (None, None)
        except Exception as Ex:
            LoggingService.LogException("GetLocalStagingPathsIfActive failed", Ex, "LocalStagingAdapter", "GetLocalStagingPathsIfActive")
            return (None, None)

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C11
    def ResolveCanonicalOutputPath(self, OutputStorageRootId, OutputRelativePath) -> Optional[str]:
        """Resolve the canonical typed-pair output path to the worker-native mount path."""
        try:
            if OutputStorageRootId is None or OutputRelativePath is None:
                return None
            return Path(OutputStorageRootId, OutputRelativePath).Resolve(Worker.Current(Db=self.DatabaseManager.DatabaseService))
        except Exception as Ex:
            LoggingService.LogException("ResolveCanonicalOutputPath failed", Ex, "LocalStagingAdapter", "ResolveCanonicalOutputPath")
            return None

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C11
    def CopyBackStagedOutput(self, LocalOutputPath: str, CanonicalOutputPath: str, MediaFileId: int) -> bool:
        """Mode B copy-back: ship local .inprogress to canonical NFS path before downstream consumers read it."""
        try:
            if not LocalOutputPath or not CanonicalOutputPath:
                LoggingService.LogError(f"Copy-back missing path: local={LocalOutputPath} canonical={CanonicalOutputPath} mid={MediaFileId}", "LocalStagingAdapter", "CopyBackStagedOutput")
                return False
            DestDir = LocalDirname(CanonicalOutputPath)
            if DestDir and not LocalExists(DestDir):
                os.makedirs(DestDir, exist_ok=True)
            LoggingService.LogInfo(f"Copy-back staged output for MediaFileId={MediaFileId}: {LocalOutputPath} -> {CanonicalOutputPath}", "LocalStagingAdapter", "CopyBackStagedOutput")
            shutil.copy2(LocalOutputPath, CanonicalOutputPath)
            SrcSize = LocalGetSize(LocalOutputPath)
            DstSize = LocalGetSize(CanonicalOutputPath)
            if SrcSize != DstSize:
                LoggingService.LogError(f"Copy-back size mismatch for MediaFileId={MediaFileId}: src={SrcSize} dst={DstSize}; deleting partial canonical write", "LocalStagingAdapter", "CopyBackStagedOutput")
                try:
                    os.remove(CanonicalOutputPath)
                except Exception:
                    pass
                return False
            LoggingService.LogInfo(f"Copy-back complete for MediaFileId={MediaFileId}: {DstSize} bytes at {CanonicalOutputPath}", "LocalStagingAdapter", "CopyBackStagedOutput")
            return True
        except Exception as Ex:
            LoggingService.LogException(f"CopyBackStagedOutput failed for MediaFileId={MediaFileId}", Ex, "LocalStagingAdapter", "CopyBackStagedOutput")
            return False
