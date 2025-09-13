from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class SeasonModel:
    """Represents season/folder organization for media files."""
    
    Id: Optional[int] = None
    RootFolderId: Optional[int] = None
    SeasonName: str = ""
    SeasonNumber: Optional[int] = None
    EpisodeCount: int = 0
    TotalSizeGB: float = 0.0
    CreatedDate: Optional[datetime] = None
    LastUpdatedDate: Optional[datetime] = None
    
    def __post_init__(self):
        if self.CreatedDate is None:
            self.CreatedDate = datetime.now()
        if self.LastUpdatedDate is None:
            self.LastUpdatedDate = datetime.now()
