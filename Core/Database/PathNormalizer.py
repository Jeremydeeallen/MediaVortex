from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from Services.DatabaseService import DatabaseService
from Services.LoggingService import LoggingService
from Core.Database.DatabaseService import EscapeLikePattern


class PathNormalizer:
    def __init__(self, DatabaseServiceInstance: Optional[DatabaseService] = None):
        self.DatabaseService = DatabaseServiceInstance or DatabaseService()


    def PrivateNormalizeFilePath(self, FilePath: str) -> str:
        """Private method to normalize file paths to use single backslashes."""
        try:
            if not FilePath:
                return FilePath

            # Replace double backslashes with single backslashes
            # This handles cases where paths might be escaped
            NormalizedPath = FilePath.replace('\\\\', '\\')

            # Log the normalization for debugging
            if NormalizedPath != FilePath:
                LoggingService.LogInfo(f"Normalized file path: '{FilePath}' -> '{NormalizedPath}'",
                                     "DatabaseManager", "PrivateNormalizeFilePath")

            return NormalizedPath

        except Exception as e:
            LoggingService.LogException("Exception normalizing file path", e, "DatabaseManager", "PrivateNormalizeFilePath")
            return FilePath
