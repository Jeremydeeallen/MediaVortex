import json
from dataclasses import dataclass
from typing import List, Optional

from Core.Database.DatabaseService import DatabaseService


ROLLING_WINDOW_N = 100


@dataclass(frozen=True)
class BucketKey:
    ProfileId: int
    SourceCodec: str
    SourceResolutionTier: str
    BitratePerPixelBucket: int
    ContentClass: str


@dataclass(frozen=True)
class BucketStats:
    SampleCount: int
    VmafMean: Optional[float]
    VmafStdDev: Optional[float]
    PassRate: Optional[float]


# directive: transcode-flow-canonical | # see transcode.ST7
class VmafConfidenceStatsRepository:

    # directive: transcode-flow-canonical | # see transcode.ST7
    def __init__(self, Db: Optional[DatabaseService] = None):
        self.Db = Db or DatabaseService()

    # directive: transcode-flow-canonical | # see transcode.ST7
    def LookupBucket(self, Key: BucketKey) -> BucketStats:
        Rows = self.Db.ExecuteQuery(
            "SELECT SampleCount, VmafMean, VmafStdDev, PassRate "
            "FROM VmafConfidenceStats "
            "WHERE ProfileId = %s AND SourceCodec = %s AND SourceResolutionTier = %s "
            "  AND BitratePerPixelBucket = %s AND ContentClass = %s",
            (Key.ProfileId, Key.SourceCodec, Key.SourceResolutionTier,
             Key.BitratePerPixelBucket, Key.ContentClass),
        )
        if not Rows:
            return BucketStats(SampleCount=0, VmafMean=None, VmafStdDev=None, PassRate=None)
        R = Rows[0]
        return BucketStats(
            SampleCount=int(R.get('samplecount') or 0),
            VmafMean=self._Float(R.get('vmafmean')),
            VmafStdDev=self._Float(R.get('vmafstddev')),
            PassRate=self._Float(R.get('passrate')),
        )

    # directive: transcode-flow-canonical | # see transcode.ST7
    def RecordResult(self, Key: BucketKey, VmafScore: float, Passed: bool) -> None:
        Samples = self._LoadSamples(Key)
        Samples.append({'vmaf': float(VmafScore), 'passed': bool(Passed)})
        if len(Samples) > ROLLING_WINDOW_N:
            Samples = Samples[-ROLLING_WINDOW_N:]
        Count, Mean, StdDev, PassRate = self._Aggregate(Samples)
        self.Db.ExecuteNonQuery(
            "INSERT INTO VmafConfidenceStats "
            "(ProfileId, SourceCodec, SourceResolutionTier, BitratePerPixelBucket, ContentClass, "
            " SampleCount, VmafMean, VmafStdDev, PassRate, SamplesJson, LastUpdated) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW()) "
            "ON CONFLICT (ProfileId, SourceCodec, SourceResolutionTier, BitratePerPixelBucket, ContentClass) "
            "DO UPDATE SET SampleCount = EXCLUDED.SampleCount, VmafMean = EXCLUDED.VmafMean, "
            "  VmafStdDev = EXCLUDED.VmafStdDev, PassRate = EXCLUDED.PassRate, "
            "  SamplesJson = EXCLUDED.SamplesJson, LastUpdated = NOW()",
            (Key.ProfileId, Key.SourceCodec, Key.SourceResolutionTier,
             Key.BitratePerPixelBucket, Key.ContentClass,
             Count, Mean, StdDev, PassRate, json.dumps(Samples)),
        )

    # directive: transcode-flow-canonical | # see transcode.ST7
    def _LoadSamples(self, Key: BucketKey) -> List[dict]:
        Rows = self.Db.ExecuteQuery(
            "SELECT SamplesJson FROM VmafConfidenceStats "
            "WHERE ProfileId = %s AND SourceCodec = %s AND SourceResolutionTier = %s "
            "  AND BitratePerPixelBucket = %s AND ContentClass = %s",
            (Key.ProfileId, Key.SourceCodec, Key.SourceResolutionTier,
             Key.BitratePerPixelBucket, Key.ContentClass),
        )
        if not Rows:
            return []
        Raw = Rows[0].get('samplesjson')
        if not Raw:
            return []
        if isinstance(Raw, (list, tuple)):
            return list(Raw)
        if isinstance(Raw, str):
            return json.loads(Raw)
        return list(Raw)

    # directive: transcode-flow-canonical | # see transcode.ST7
    def _Aggregate(self, Samples: List[dict]):
        Count = len(Samples)
        if Count == 0:
            return 0, None, None, None
        Mean = sum(S['vmaf'] for S in Samples) / Count
        Variance = sum((S['vmaf'] - Mean) ** 2 for S in Samples) / Count
        StdDev = Variance ** 0.5
        PassCount = sum(1 for S in Samples if S['passed'])
        PassRate = PassCount / Count
        return Count, round(Mean, 2), round(StdDev, 2), round(PassRate, 4)

    # directive: transcode-flow-canonical | # see transcode.ST7
    def _Float(self, Value) -> Optional[float]:
        if Value is None:
            return None
        return float(Value)

    # directive: transcode-flow-canonical | # see transcode.ST7
    def GetAllForReview(self, ProfileNameFilter: Optional[str] = None, Limit: int = 200) -> List[dict]:
        Query = (
            "SELECT vcs.Id, vcs.ProfileId, p.ProfileName, p.Family, p.QualityTier, "
            "  vcs.SourceCodec, vcs.SourceResolutionTier, vcs.BitratePerPixelBucket, "
            "  vcs.ContentClass, vcs.SampleCount, vcs.VmafMean, vcs.VmafStdDev, "
            "  vcs.PassRate, vcs.LastUpdated "
            "FROM VmafConfidenceStats vcs "
            "LEFT JOIN Profiles p ON p.Id = vcs.ProfileId "
        )
        Params: List = []
        if ProfileNameFilter:
            Query += "WHERE p.ProfileName ILIKE %s "
            Params.append(f"%{ProfileNameFilter}%")
        Query += "ORDER BY vcs.LastUpdated DESC LIMIT %s"
        Params.append(int(Limit))
        Rows = self.Db.ExecuteQuery(Query, tuple(Params))
        Out = []
        for R in Rows:
            Out.append({
                'Id': int(R.get('id') or 0),
                'ProfileId': int(R.get('profileid') or 0),
                'ProfileName': R.get('profilename') or '',
                'Family': R.get('family') or '',
                'QualityTier': int(R.get('qualitytier') or 0) if R.get('qualitytier') is not None else None,
                'SourceCodec': R.get('sourcecodec') or '',
                'SourceResolutionTier': R.get('sourceresolutiontier') or '',
                'BitratePerPixelBucket': int(R.get('bitrateperpixelbucket') or 0),
                'ContentClass': R.get('contentclass') or '',
                'SampleCount': int(R.get('samplecount') or 0),
                'VmafMean': self._Float(R.get('vmafmean')),
                'VmafStdDev': self._Float(R.get('vmafstddev')),
                'PassRate': self._Float(R.get('passrate')),
                'LastUpdated': R.get('lastupdated').isoformat() if R.get('lastupdated') else None,
            })
        return Out
