# directive: transcode-worker-unification | # see filereplacement.C11
import os
from typing import Optional
from Core.Logging.LoggingService import LoggingService


# directive: transcode-worker-unification | # see filereplacement.C11
class FilesystemRenameWithBackup:

    # directive: transcode-worker-unification | # see filereplacement.C11
    def __init__(self, SourcePath: str, TargetPath: str, BackupPath: Optional[str] = None):
        # see filereplacement.C11
        self.SourcePath = SourcePath
        self.TargetPath = TargetPath
        self.BackupPath = BackupPath or (SourcePath + '.replacing.bak')
        self._RenameDone = False
        self._BackupCreated = False

    # directive: transcode-worker-unification | # see filereplacement.C11
    def Apply(self) -> None:
        # see filereplacement.C11
        if os.path.exists(self.TargetPath):
            os.rename(self.TargetPath, self.BackupPath)
            self._BackupCreated = True
        os.rename(self.SourcePath, self.TargetPath)
        self._RenameDone = True

    # directive: transcode-worker-unification | # see filereplacement.C11
    def Commit(self) -> None:
        # see filereplacement.C11
        if self._BackupCreated and os.path.exists(self.BackupPath):
            os.remove(self.BackupPath)
            self._BackupCreated = False

    # directive: transcode-worker-unification | # see filereplacement.C11
    def Rollback(self) -> None:
        # see filereplacement.C11
        if self._RenameDone:
            try:
                os.rename(self.TargetPath, self.SourcePath)
            except Exception as Ex:
                LoggingService.LogException("Rollback rename failed", Ex, "FilesystemRenameWithBackup", "Rollback")
            self._RenameDone = False
        if self._BackupCreated and os.path.exists(self.BackupPath):
            try:
                os.rename(self.BackupPath, self.TargetPath)
            except Exception as Ex:
                LoggingService.LogException("Rollback backup-restore failed", Ex, "FilesystemRenameWithBackup", "Rollback")
            self._BackupCreated = False
