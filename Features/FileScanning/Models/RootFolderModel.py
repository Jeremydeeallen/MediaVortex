from datetime import datetime, timezone
from typing import Optional


# directive: path-class-perfection | # see path.C23
class RootFolderModel:
    # directive: path-class-perfection | # see path.C27
    def __init__(self, Id: Optional[int] = None,
                 LastScannedDate: Optional[datetime] = None,
                 TotalSizeGB: float = 0.0,
                 PreferredWorkerName: Optional[str] = None,
                 StorageRootId: Optional[int] = None,
                 RelativePath: str = ""):
        self.Id = Id
        self.LastScannedDate = LastScannedDate if LastScannedDate is not None else datetime.now(timezone.utc)
        self.TotalSizeGB = TotalSizeGB
        self.PreferredWorkerName = PreferredWorkerName
        self.StorageRootId = StorageRootId
        self.RelativePath = RelativePath or ""

    # directive: path-class-perfection | # see path.C23
    @property
    def Path(self):
        from Core.Path.Path import Path as _Path
        if self.StorageRootId is None:
            return None
        return _Path(self.StorageRootId, self.RelativePath or "")
