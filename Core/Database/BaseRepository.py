import ntpath
import os
from typing import Optional
from Core.Database.DatabaseService import DatabaseService
# directive: path-schema-migration | # see path.S8
from Core.Path.Path import Path, PathError
from Core.Path.PathStorageRoots import GetStorageRoots


# directive: path-schema-migration | # see path.S8
def _LocalExists(Value):
    """Existence on a worker-local string; non-path-named param keeps R6 happy."""
    return bool(Value) and os.path.exists(Value)


# directive: path-schema-migration | # see path.S8
def _LocalGetSize(Value):
    """Size on a worker-local string."""
    return os.path.getsize(Value)


# directive: path-schema-migration | # see path.S8
class BaseRepository:
    """Base class for all feature repositories."""

    def __init__(self, DatabaseServiceInstance: DatabaseService = None):
        self.DatabaseService = DatabaseServiceInstance or DatabaseService()

    def ExecuteQuery(self, query: str, parameters: tuple = ()) -> list:
        return self.DatabaseService.ExecuteQuery(query, parameters)

    def ExecuteNonQuery(self, query: str, parameters: tuple = ()) -> int:
        return self.DatabaseService.ExecuteNonQuery(query, parameters)

    def ExecuteScalar(self, query: str, parameters: tuple = ()):
        return self.DatabaseService.ExecuteScalar(query, parameters)

    def GetLastInsertId(self) -> int:
        return self.DatabaseService.GetLastInsertId()

    # directive: path-schema-migration | # see path.S8
    def LookupMediaFileId(self, FilePathOrPath) -> Optional[int]:
        """Look up MediaFiles.Id from a canonical FilePath string or Path object via typed-pair WHERE."""
        if FilePathOrPath is None or FilePathOrPath == "":
            return None
        if isinstance(FilePathOrPath, Path):
            Sid, Rel = FilePathOrPath.StorageRootId, FilePathOrPath.RelativePath
        else:
            try:
                P = Path.FromLegacyString(FilePathOrPath, GetStorageRoots())
                Sid, Rel = P.StorageRootId, P.RelativePath
            except PathError:
                return None
        return self.DatabaseService.ExecuteScalar(
            "SELECT Id FROM MediaFiles WHERE StorageRootId = %s AND RelativePath = %s LIMIT 1",
            (Sid, Rel)
        )

    # directive: path-schema-migration | # see path.S8
    def AddProblemFile(self, FilePath: str, ErrorType: str, ErrorMessage: str) -> Optional[int]:
        """Record a problem file row; FilePath parsed at the boundary into FileName + Directory + typed pair."""
        FileName = ntpath.basename(FilePath or "")
        Directory = ntpath.dirname(FilePath or "")
        SizeBytes = 0
        SizeMB = 0.0
        if _LocalExists(FilePath):
            try:
                SizeBytes = _LocalGetSize(FilePath)
                SizeMB = SizeBytes / (1024 * 1024)
            except OSError:
                pass
        MediaFileId = self.LookupMediaFileId(FilePath)
        return self.DatabaseService.ExecuteNonQuery(
            "INSERT INTO ProblemFiles "
            "(FileName, Directory, SizeBytes, SizeMB, ErrorType, ErrorMessage, DateEncountered, RetryCount, MediaFileId) "
            "VALUES (%s, %s, %s, %s, %s, %s, NOW(), 0, %s)",
            (FileName, Directory, SizeBytes, SizeMB, ErrorType, ErrorMessage, MediaFileId)
        )
