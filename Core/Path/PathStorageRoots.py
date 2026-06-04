from threading import Lock
from typing import Dict, List, Optional


# directive: path-schema-migration | # see path.S8
class PathStorageRoots:
    """Process-singleton cache of StorageRoots; loads (Id, CanonicalPrefix) lazily on first read."""

    _Instance: Optional["PathStorageRoots"] = None
    _Lock = Lock()

    # directive: path-schema-migration | # see path.S8
    def __init__(self):
        self._Roots: Optional[List[dict]] = None
        self._PrefixMap: Optional[Dict[int, str]] = None

    @classmethod
    # directive: path-schema-migration | # see path.S8
    def Instance(cls) -> "PathStorageRoots":
        """Return the process singleton."""
        with cls._Lock:
            if cls._Instance is None:
                cls._Instance = cls()
            return cls._Instance

    # directive: path-schema-migration | # see path.S8
    def _Load(self):
        """Populate cache from PostgreSQL; ordered longest-prefix-first for FromLegacyString."""
        from Core.Database.DatabaseService import DatabaseService
        Db = DatabaseService()
        Rows = Db.ExecuteQuery(
            "SELECT Id, CanonicalPrefix FROM StorageRoots ORDER BY length(CanonicalPrefix) DESC"
        )
        self._Roots = [
            {"Id": R.get("id", R.get("Id")),
             "CanonicalPrefix": R.get("canonicalprefix", R.get("CanonicalPrefix"))}
            for R in Rows
        ]
        self._PrefixMap = {R["Id"]: R["CanonicalPrefix"] for R in self._Roots}

    # directive: path-schema-migration | # see path.S8
    def StorageRoots(self) -> List[dict]:
        """Ordered prefix list; safe for Path.FromLegacyString."""
        if self._Roots is None:
            self._Load()
        return self._Roots

    # directive: path-schema-migration | # see path.S8
    def PrefixMap(self) -> Dict[int, str]:
        """StorageRootId -> CanonicalPrefix mapping."""
        if self._PrefixMap is None:
            self._Load()
        return self._PrefixMap

    # directive: path-schema-migration | # see path.S8
    def Invalidate(self):
        """Drop the cache; next read reloads from PostgreSQL."""
        self._Roots = None
        self._PrefixMap = None


# directive: path-schema-migration | # see path.S8
def GetStorageRoots() -> List[dict]:
    """Module-level shortcut for PathStorageRoots.Instance().StorageRoots()."""
    return PathStorageRoots.Instance().StorageRoots()


# directive: path-schema-migration | # see path.S8
def GetPrefixMap() -> Dict[int, str]:
    """Module-level shortcut for PathStorageRoots.Instance().PrefixMap()."""
    return PathStorageRoots.Instance().PrefixMap()
