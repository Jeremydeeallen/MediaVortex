# directive: target-policy-1a-tables | # see policy.W4, policy.C6 -- EncoderSettings(Encoder, QualityTier) is the one home of encoder knobs; read fresh per call
from dataclasses import dataclass, fields
from typing import Any, Dict, List, Optional

from Core.Database.DatabaseService import DatabaseService


@dataclass(frozen=True)
# directive: target-policy-1a-tables | # see policy.W4
class EncoderSettings:
    Id: int
    Encoder: str
    QualityTier: int
    Preset: Optional[str]
    Tune: Optional[str]
    Multipass: Optional[str]
    RateControl: str
    MaxRateMultiplier: Optional[float]
    BufSizeMultiplier: Optional[float]
    SpatialAq: Optional[int]
    TemporalAq: Optional[int]
    PixelFormat: Optional[str]
    Gop: Optional[int]
    RcLookahead: Optional[int]
    BFrames: Optional[int]
    BRefMode: Optional[str]
    QsvExtBrc: Optional[int]
    QsvAdaptiveI: Optional[int]
    QsvAdaptiveB: Optional[int]
    QsvLookAheadDepth: Optional[int]
    QsvBStrategy: Optional[int]
    QsvTileCols: Optional[int]
    QsvTileRows: Optional[int]
    Crf: Optional[int]
    FilmGrain: Optional[int]


_FIELDS = [F.name for F in fields(EncoderSettings)]
_EDITABLE = frozenset(_FIELDS) - {'Id', 'Encoder', 'QualityTier'}
_INT_FIELDS = frozenset({'SpatialAq', 'TemporalAq', 'Gop', 'RcLookahead', 'BFrames', 'QsvExtBrc', 'QsvAdaptiveI', 'QsvAdaptiveB',
                         'QsvLookAheadDepth', 'QsvBStrategy', 'QsvTileCols', 'QsvTileRows', 'Crf', 'FilmGrain'})
_FLOAT_FIELDS = frozenset({'MaxRateMultiplier', 'BufSizeMultiplier'})


# directive: target-policy-1a-tables | # see policy.W4
def _Row(R) -> EncoderSettings:
    Values: Dict[str, Any] = {}
    for Name in _FIELDS:
        V = R[Name]
        if V is None:
            Values[Name] = None
        elif Name in _INT_FIELDS or Name in ('Id', 'QualityTier'):
            Values[Name] = int(V)
        elif Name in _FLOAT_FIELDS:
            Values[Name] = float(V)
        else:
            Values[Name] = str(V)
    return EncoderSettings(**Values)


# directive: target-policy-1a-tables | # see policy.W4
class EncoderSettingsRepository:

    # directive: target-policy-1a-tables | # see policy.W4
    def __init__(self, Db: Optional[DatabaseService] = None):
        self.Db = Db or DatabaseService()

    # directive: target-policy-1a-tables | # see policy.S3
    def Get(self, Encoder: str, QualityTier: int) -> Optional[EncoderSettings]:
        Rows = self.Db.ExecuteQuery(
            f"SELECT {', '.join(_FIELDS)} FROM EncoderSettings WHERE Encoder = %s AND QualityTier = %s",
            (Encoder, int(QualityTier)),
        )
        return _Row(Rows[0]) if Rows else None

    # directive: target-policy-1a-tables | # see policy.W4
    def ListAll(self) -> List[EncoderSettings]:
        Rows = self.Db.ExecuteQuery(f"SELECT {', '.join(_FIELDS)} FROM EncoderSettings ORDER BY Encoder, QualityTier")
        return [_Row(R) for R in Rows]

    # directive: target-policy-1a-tables | # see policy.W4
    def Update(self, Encoder: str, QualityTier: int, Changes: Dict[str, Any]) -> int:
        Unknown = sorted(set(Changes) - _EDITABLE)
        if Unknown:
            raise ValueError(f"EncoderSettings has no editable column(s) {Unknown}")
        if not Changes:
            return 0
        if 'RateControl' in Changes and not Changes['RateControl']:
            raise ValueError("RateControl is required")
        Names = sorted(Changes)
        SetClause = ', '.join(f"{N} = %s" for N in Names)
        return int(self.Db.ExecuteNonQuery(
            f"UPDATE EncoderSettings SET {SetClause} WHERE Encoder = %s AND QualityTier = %s",
            tuple(Changes[N] for N in Names) + (Encoder, int(QualityTier)),
        ) or 0)
