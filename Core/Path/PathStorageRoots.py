from typing import Dict, List


# directive: path-class-perfection | # see path.C18
def GetStorageRoots() -> List[dict]:
    """Read StorageRoots from PostgreSQL fresh per call (no cache); ordered longest-prefix-first for FromLegacyString."""
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


# directive: path-class-perfection | # see path.C18
def GetPrefixMap() -> Dict[int, str]:
    """Read StorageRoots from PostgreSQL fresh per call; return {Id: CanonicalPrefix}."""
    return {R["Id"]: R["CanonicalPrefix"] for R in GetStorageRoots()}
