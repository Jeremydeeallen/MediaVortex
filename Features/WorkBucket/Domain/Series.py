from dataclasses import dataclass
from typing import Optional
from Features.WorkBucket.Domain.SeriesIdentity import SeriesIdentity
from Features.WorkBucket.Domain.BucketKey import BucketKey


@dataclass(frozen=True)
# directive: work-transcode-unified
class Series:
    """Aggregated row for one series within one bucket -- the unit the grouped page renders."""

    Identity: SeriesIdentity
    Bucket: BucketKey
    ShowName: str
    FileCount: int
    TotalGB: float
    CommonResolution: Optional[str]
    CommonCodec: Optional[str]
    AssignedProfile: Optional[str]
    AnyInQueue: bool

    # directive: work-transcode-unified
    def ToJson(self) -> dict:
        """JSON projection for /api/Work/<bucket>."""
        # see work-bucket.C2
        return {
            'StorageRootId': self.Identity.StorageRootId,
            'RelativePath': self.Identity.RelativePath,
            'ShowName': self.ShowName,
            'CompositeKey': self.Identity.ToCompositeKey(),
            'Bucket': self.Bucket.BucketName,
            'FileCount': self.FileCount,
            'TotalGB': self.TotalGB,
            'CommonResolution': self.CommonResolution,
            'CommonCodec': self.CommonCodec,
            'AssignedProfile': self.AssignedProfile,
            'AnyInQueue': self.AnyInQueue,
        }
