# directive: target-policy-1a-tables | # see policy.W2, policy.S6 -- an override is a tier at series or file scope; UNIQUE (StorageRootId, Scope, Key)
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from Core.Database.DatabaseService import DatabaseService

SCOPE_SERIES = 'series'
SCOPE_FILE = 'file'
_SCOPES = (SCOPE_SERIES, SCOPE_FILE)
_COLUMNS = "Id, StorageRootId, Scope, Key, QualityTier, SetBy, SetAt"


@dataclass(frozen=True)
# directive: target-policy-1a-tables | # see policy.W2
class TargetOverride:
    Id: int
    StorageRootId: int
    Scope: str
    Key: str
    QualityTier: int
    SetBy: str
    SetAt: datetime


# directive: target-policy-1a-tables | # see policy.W2
def _Row(R) -> TargetOverride:
    return TargetOverride(
        Id=int(R['Id']), StorageRootId=int(R['StorageRootId']), Scope=str(R['Scope']), Key=str(R['Key']),
        QualityTier=int(R['QualityTier']), SetBy=str(R['SetBy']), SetAt=R['SetAt'],
    )


# directive: target-policy-1a-tables | # see policy.W2
def _Validate(Scope: str, Key: str, QualityTier: Optional[int] = 1) -> None:
    if Scope not in _SCOPES:
        raise ValueError(f"Scope must be one of {_SCOPES}, got {Scope!r}")
    if not Key:
        raise ValueError("Key is required (series folder or MediaFileId text)")
    if QualityTier is not None and not (1 <= int(QualityTier) <= 5):
        raise ValueError(f"QualityTier must be 1-5, got {QualityTier!r}")


# directive: target-policy-1a-tables | # see policy.W2
class TargetOverrideRepository:

    # directive: target-policy-1a-tables | # see policy.W2
    def __init__(self, Db: Optional[DatabaseService] = None):
        self.Db = Db or DatabaseService()

    # directive: target-policy-1a-tables | # see policy.W2, policy.S6
    def Upsert(self, StorageRootId: int, Scope: str, Key: str, QualityTier: int, SetBy: str) -> TargetOverride:
        _Validate(Scope, Key, QualityTier)
        if not SetBy:
            raise ValueError("SetBy is required")
        self.Db.ExecuteNonQuery(
            "INSERT INTO TargetOverrides (StorageRootId, Scope, Key, QualityTier, SetBy, SetAt) VALUES (%s, %s, %s, %s, %s, NOW()) "
            "ON CONFLICT (StorageRootId, Scope, Key) DO UPDATE SET QualityTier = EXCLUDED.QualityTier, SetBy = EXCLUDED.SetBy, SetAt = NOW()",
            (int(StorageRootId), Scope, str(Key), int(QualityTier), SetBy),
        )
        Row = self.Get(StorageRootId, Scope, Key)
        if Row is None:
            raise RuntimeError(f"TargetOverrides upsert did not persist ({StorageRootId}, {Scope}, {Key})")
        return Row

    # directive: target-policy-1a-tables | # see policy.W2
    def Delete(self, StorageRootId: int, Scope: str, Key: str) -> int:
        _Validate(Scope, Key, None)
        return int(self.Db.ExecuteNonQuery(
            "DELETE FROM TargetOverrides WHERE StorageRootId = %s AND Scope = %s AND Key = %s",
            (int(StorageRootId), Scope, str(Key)),
        ) or 0)

    # directive: target-policy-1a-tables | # see policy.W2
    def Get(self, StorageRootId: int, Scope: str, Key: str) -> Optional[TargetOverride]:
        _Validate(Scope, Key, None)
        Rows = self.Db.ExecuteQuery(
            f"SELECT {_COLUMNS} FROM TargetOverrides WHERE StorageRootId = %s AND Scope = %s AND Key = %s",
            (int(StorageRootId), Scope, str(Key)),
        )
        return _Row(Rows[0]) if Rows else None

    # directive: target-policy-1a-tables | # see policy.W2
    def ListForRoot(self, StorageRootId: int) -> List[TargetOverride]:
        Rows = self.Db.ExecuteQuery(
            f"SELECT {_COLUMNS} FROM TargetOverrides WHERE StorageRootId = %s ORDER BY Scope, Key",
            (int(StorageRootId),),
        )
        return [_Row(R) for R in Rows]
