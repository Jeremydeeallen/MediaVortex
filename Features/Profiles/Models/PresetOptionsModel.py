from dataclasses import dataclass
from Core.DateTimeHelpers import ToUtcIsoZ
from datetime import datetime, timezone
from typing import Optional


@dataclass
class PresetOptionsModel:
    """Represents preset options for codecs with string-based presets."""
    
    Id: Optional[int] = None
    CodecFlagsId: int = 0
    PresetValue: str = ""  # The actual preset value (e.g., "medium", "fast")
    PresetName: str = ""  # Friendly display name (e.g., "Medium", "Fast")
    Description: str = ""  # User-friendly description
    SortOrder: int = 0  # Order for display in UI
    CreatedDate: Optional[datetime] = None
    
    def __post_init__(self):
        if self.CreatedDate is None:
            self.CreatedDate = datetime.now(timezone.utc)
    
    def ToDict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'Id': self.Id,
            'CodecFlagsId': self.CodecFlagsId,
            'PresetValue': self.PresetValue,
            'PresetName': self.PresetName,
            'Description': self.Description,
            'SortOrder': self.SortOrder,
            'CreatedDate': ToUtcIsoZ(self.CreatedDate)
        }
