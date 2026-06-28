from dataclasses import dataclass


@dataclass(frozen=True)
# directive: work-transcode-unified
class SeriesIdentity:
    """Identifies one series uniquely within the library: (drive, first-path-segment) pair."""

    StorageRootId: int
    RelativePath: str

    # directive: work-transcode-unified
    def ToCompositeKey(self) -> str:
        """Render as the URL path token used by /api/Work/<bucket>/Series/<sid>."""
        # see work-bucket.C2
        return f"{self.StorageRootId}:{self.RelativePath}"

    @classmethod
    # directive: work-transcode-unified
    def FromCompositeKey(cls, Key: str) -> "SeriesIdentity":
        """Parse the URL path token. The first colon separates StorageRootId from RelativePath; RelativePath may contain further colons."""
        # see work-bucket.C2
        Sep = Key.find(':')
        if Sep < 0:
            raise ValueError(f"SeriesIdentity composite key missing ':' separator: {Key!r}")
        return cls(StorageRootId=int(Key[:Sep]), RelativePath=Key[Sep + 1:])
