from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
# directive: path-schema-migration | # see path.S5
class ShowSettingModel:
    """Represents per-show settings for target resolution override."""

    Id: Optional[int] = None
    StorageRootId: Optional[int] = None
    RelativePath: str = ""
    ShowFolder: str = ""  # Legacy column; populated by repository row map only. Dropped in Phase F.
    TargetResolution: str = ""  # "480p", "720p", "1080p", "2160p", or "" (use profile default)
    CreatedDate: Optional[datetime] = None
    LastModifiedDate: Optional[datetime] = None

    # directive: path-schema-migration | # see path.S5
    def __post_init__(self):
        if self.CreatedDate is None:
            self.CreatedDate = datetime.now(timezone.utc)
        if self.LastModifiedDate is None:
            self.LastModifiedDate = datetime.now(timezone.utc)
