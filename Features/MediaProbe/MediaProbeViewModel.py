from typing import Dict, Any, Optional
from Features.MediaProbe.MediaProbeBusinessService import MediaProbeBusinessService
from Core.Logging.LoggingService import LoggingService


class MediaProbeViewModel:
    """Manages MediaProbe UI state and delegates to BusinessService."""

    def __init__(self, BusinessService: MediaProbeBusinessService = None):
        self.BusinessService = BusinessService or MediaProbeBusinessService()

    def ProbeFile(self, MediaFileId: int, Force: bool = False) -> Dict[str, Any]:
        """Probe a single file."""
        return self.BusinessService.ProbeFile(MediaFileId, Force)

    def ProbeFilesNeedingMetadata(self, RootFolderId: Optional[int] = None) -> Dict[str, Any]:
        """Probe all files needing metadata."""
        return self.BusinessService.ProbeFilesNeedingMetadata(RootFolderId)

    def ResetFailures(self, MediaFileId: int) -> Dict[str, Any]:
        """Reset probe failures for a single file."""
        return self.BusinessService.ResetFailures(MediaFileId)

    def ResetAllFailures(self) -> Dict[str, Any]:
        """Reset probe failures for all files."""
        return self.BusinessService.ResetAllFailures()

    def GetFailedFiles(self) -> Dict[str, Any]:
        """Get permanently failed files."""
        return self.BusinessService.GetFailedFiles()

    def GetProbeStatistics(self) -> Dict[str, Any]:
        """Get probe statistics."""
        return self.BusinessService.GetProbeStatistics()
