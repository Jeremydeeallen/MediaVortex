from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class TranscodeProfileModel:
    """Represents a transcoding profile with its settings."""
    
    Id: Optional[int] = None
    ProfileName: str = ""
    Description: str = ""
    CreatedDate: Optional[datetime] = None
    LastModified: Optional[datetime] = None
    
    def __post_init__(self):
        if self.CreatedDate is None:
            self.CreatedDate = datetime.now()
        if self.LastModified is None:
            self.LastModified = datetime.now()
