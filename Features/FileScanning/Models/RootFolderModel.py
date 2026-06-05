from datetime import datetime, timezone
from typing import Optional


# directive: path-perfect-implementation | # see path-storage.S1
class RootFolderModel:
    # directive: path-perfect-implementation | # see path-storage.S1
    def __init__(self, Id: Optional[int] = None, RootFolder: str = "",
                 LastScannedDate: Optional[datetime] = None,
                 TotalSizeGB: float = 0.0,
                 PreferredWorkerName: Optional[str] = None,
                 StorageRootId: Optional[int] = None,
                 RelativePath: str = ""):
        self.Id = Id
        self.LastScannedDate = LastScannedDate if LastScannedDate is not None else datetime.now(timezone.utc)
        self.TotalSizeGB = TotalSizeGB
        self.PreferredWorkerName = PreferredWorkerName
        self._LegacyRootFolder = RootFolder or ""
        self.StorageRootId = StorageRootId
        self.RelativePath = RelativePath or ""
        if (StorageRootId is None or RelativePath == "") and RootFolder:
            from Core.Path.Path import Path, PathError
            from Core.Path.PathStorageRoots import GetStorageRoots
            try:
                Parsed = Path.FromLegacyString(RootFolder, GetStorageRoots())
                if self.StorageRootId is None:
                    self.StorageRootId = Parsed.StorageRootId
                if not self.RelativePath:
                    self.RelativePath = Parsed.RelativePath
            except PathError:
                pass

    # directive: path-perfect-implementation | # see path-storage.S1
    @property
    def RootFolder(self) -> str:
        if self.StorageRootId is not None:
            from Core.Path.Path import Path, PathError
            from Core.Path.PathStorageRoots import GetPrefixMap
            try:
                return Path(self.StorageRootId, self.RelativePath or "").CanonicalDisplay(GetPrefixMap())
            except PathError:
                pass
        return self._LegacyRootFolder

    # directive: path-perfect-implementation | # see path-storage.S1
    @RootFolder.setter
    def RootFolder(self, Value: str) -> None:
        self._LegacyRootFolder = Value or ""
        if Value:
            from Core.Path.Path import Path, PathError
            from Core.Path.PathStorageRoots import GetStorageRoots
            try:
                Parsed = Path.FromLegacyString(Value, GetStorageRoots())
                self.StorageRootId = Parsed.StorageRootId
                self.RelativePath = Parsed.RelativePath
            except PathError:
                pass
