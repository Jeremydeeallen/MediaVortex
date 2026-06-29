from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
# directive: work-transcode-unified
class BucketKey:

    UrlKey: str
    BucketName: str
    ProcessingMode: str
    Title: str
    Subtitle: str
    Icon: str

    @classmethod
    # directive: work-transcode-unified
    def FromUrlKey(cls, UrlKey: str) -> Optional["BucketKey"]:
        # see work-bucket.C1
        return _BY_URL_KEY.get(UrlKey)


_REGISTRY = (
    BucketKey(
        UrlKey='Transcode',
        BucketName='Transcode',
        ProcessingMode='Transcode',
        Title='Transcode',
        Subtitle='Files needing full transcode -- video + audio + container.',
        Icon='fas fa-film',
    ),
    BucketKey(
        UrlKey='Remux',
        BucketName='Remux',
        ProcessingMode='Remux',
        Title='Remux',
        Subtitle='Files needing container fix (audio is also normalized through the same emitter).',
        Icon='fas fa-box',
    ),
    BucketKey(
        UrlKey='Audio',
        BucketName='AudioFix',
        ProcessingMode='AudioFix',
        Title='Audio',
        Subtitle='Files where audio is the only blocker; container + video stream-copy through.',
        Icon='fas fa-volume-up',
    ),
)


_BY_URL_KEY = {B.UrlKey: B for B in _REGISTRY}
