from contextvars import ContextVar
from typing import Dict, List, Optional


# directive: path-class-perfection | # see path.C25
_ScopeStorageRoots: ContextVar[Optional[List[dict]]] = ContextVar("_ScopeStorageRoots", default=None)
_ScopePrefixMap: ContextVar[Optional[Dict[int, str]]] = ContextVar("_ScopePrefixMap", default=None)


# directive: path-class-perfection | # see path.C18
def GetStorageRoots() -> List[dict]:
    """Reuse the active PrefixMapScope cache if set; else read DB fresh per call."""
    Cached = _ScopeStorageRoots.get()
    if Cached is not None:
        return Cached
    return _LoadFresh()


# directive: path-class-perfection | # see path.C18
def GetPrefixMap() -> Dict[int, str]:
    """Reuse the active PrefixMapScope cache if set; else read DB fresh."""
    Cached = _ScopePrefixMap.get()
    if Cached is not None:
        return Cached
    return {R["Id"]: R["CanonicalPrefix"] for R in _LoadFresh()}


def _LoadFresh() -> List[dict]:
    """Read StorageRoots from PostgreSQL; ordered longest-prefix-first for FromLegacyString."""
    from Core.Database.DatabaseService import DatabaseService
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT Id, CanonicalPrefix FROM StorageRoots ORDER BY length(CanonicalPrefix) DESC"
    )
    return [
        {"Id": R.get("id", R.get("Id")),
         "CanonicalPrefix": R.get("canonicalprefix", R.get("CanonicalPrefix"))}
        for R in Rows
    ]


# directive: path-class-perfection | # see path.C25
class PrefixMapScope:
    """Context manager pinning a StorageRoots snapshot for its lifetime; used by Flask request middleware + worker tick loops."""

    def __init__(self):
        self._RootsToken = None
        self._MapToken = None

    def __enter__(self):
        Roots = _LoadFresh()
        Pm = {R["Id"]: R["CanonicalPrefix"] for R in Roots}
        self._RootsToken = _ScopeStorageRoots.set(Roots)
        self._MapToken = _ScopePrefixMap.set(Pm)
        return self

    def __exit__(self, ExcType, ExcVal, Tb):
        if self._RootsToken is not None:
            _ScopeStorageRoots.reset(self._RootsToken)
        if self._MapToken is not None:
            _ScopePrefixMap.reset(self._MapToken)
        return False
