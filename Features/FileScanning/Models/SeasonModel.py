from dataclasses import dataclass
from typing import Optional


@dataclass
class SeasonModel:
    """Represents season/folder organization for media files."""

    Id: Optional[int] = None
    RootFolderId: Optional[int] = None
    SeasonName: str = ""
