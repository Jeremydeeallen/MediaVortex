# directive: path-worker-class | # see path.S3
from typing import Optional


# directive: path-worker-class | # see path.S3
class Worker:
    """Concrete Worker satisfying the Path Protocol; resolves StorageRootId to a worker-local prefix."""

    # directive: path-worker-class | # see path.S3
    def __init__(self, Name: str, Platform: str, Db=None):
        """Construct a Worker. Db is a DatabaseService instance (defaults to a fresh one); cache is per-instance."""
        self.Name = Name
        self.Platform = Platform
        self._Db = Db
        self._Cache: dict = {}

    @classmethod
    # directive: path-class-perfection | # see path.C21
    def Current(cls, Db=None) -> "Worker":
        """Build a Worker from the process-singleton WorkerContext; falls back to socket.gethostname() if uninitialized."""
        import socket
        from Core.WorkerContext import WorkerContext
        Ctx = WorkerContext.Current()
        Name = (Ctx.WorkerName if Ctx else None) or socket.gethostname()
        Platform = (Ctx.Platform if Ctx else None) or "linux"
        return cls(Name=Name, Platform=Platform, Db=Db)

    # directive: path-worker-class | # see path.S3
    def ResolveStorageRoot(self, StorageRootId: int) -> Optional[str]:
        """Return the worker-local AbsolutePath for the given StorageRootId, or None if no active resolution exists. Cached per-instance for the lifetime of this Worker; reconstruct the Worker to pick up operator changes to StorageRootResolutions."""
        if StorageRootId in self._Cache:
            return self._Cache[StorageRootId]
        Db = self._GetDb()
        Rows = Db.ExecuteQuery(
            "SELECT AbsolutePath FROM StorageRootResolutions WHERE StorageRootId = %s AND WorkerName = %s AND IsActive = TRUE LIMIT 1",
            (StorageRootId, self.Name),
        )
        Result = Rows[0]["AbsolutePath" if "AbsolutePath" in Rows[0] else "absolutepath"] if Rows else None
        self._Cache[StorageRootId] = Result
        return Result

    # directive: path-perfect-implementation | # see path.S11
    def LocalToPath(self, LocalPath: str):
        """Inverse of Path.Resolve(Worker): find the StorageRoot whose AbsolutePath is a prefix of LocalPath, return Path(Sid, Rel). None if no match."""
        if not LocalPath:
            return None
        Db = self._GetDb()
        Rows = Db.ExecuteQuery(
            "SELECT StorageRootId, AbsolutePath FROM StorageRootResolutions WHERE WorkerName = %s AND IsActive = TRUE",
            (self.Name,),
        )
        Best = None
        BestLen = -1
        for R in Rows:
            Abs = R.get("AbsolutePath") or R.get("absolutepath") or ""
            Sid = R.get("StorageRootId") if "StorageRootId" in R else R.get("storagerootid")
            if not Abs:
                continue
            if LocalPath.startswith(Abs) and len(Abs) > BestLen:
                Best = (Sid, Abs)
                BestLen = len(Abs)
        if Best is None:
            return None
        from Core.Path.Path import Path as _Path, PathError as _PE
        Sid, Abs = Best
        Tail = LocalPath[len(Abs):]
        Norm = Tail.replace("\\", "/")
        while Norm.startswith("/"):
            Norm = Norm[1:]
        try:
            return _Path(int(Sid), Norm)
        except _PE:
            return None

    # directive: path-worker-class | # see path.S3
    def _GetDb(self):
        """Lazy DatabaseService construction so unit tests can inject a mock without touching real DB."""
        if self._Db is None:
            from Core.Database.DatabaseService import DatabaseService
            self._Db = DatabaseService()
        return self._Db
