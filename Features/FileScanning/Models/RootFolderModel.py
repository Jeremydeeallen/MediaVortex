from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RootFolderModel:
    """Represents a base directory with size information."""
    
    Id: Optional[int] = None
    RootFolder: str = ""
    LastScannedDate: Optional[datetime] = None
    TotalSizeGB: float = 0.0
    
    def __post_init__(self):
        if self.LastScannedDate is None:
            self.LastScannedDate = datetime.now()
