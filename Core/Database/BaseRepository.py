from Core.Database.DatabaseService import DatabaseService


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

    def LookupMediaFileId(self, FilePath: str):
        """Look up MediaFiles.Id by FilePath (case-insensitive). Returns None if not found."""
        if not FilePath:
            return None
        Result = self.DatabaseService.ExecuteScalar(
            "SELECT Id FROM MediaFiles WHERE LOWER(FilePath) = LOWER(%s) LIMIT 1",
            (FilePath,)
        )
        return Result
