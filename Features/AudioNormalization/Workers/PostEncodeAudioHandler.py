from typing import Optional

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


CANONICAL_PATH_SQL = (
    "SELECT sr.CanonicalPrefix, mf.RelativePath "
    "FROM MediaFiles mf JOIN StorageRoots sr ON sr.Id = mf.StorageRootId "
    "WHERE mf.Id = %s"
)


# directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S3
class PostEncodeAudioHandler:
    """Owns the post-encode audio probe + canonical path resolution; SRP-extracted from ProcessTranscodeQueueService."""

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S3
    def __init__(self, FFmpegPath: Optional[str] = None, FFprobePath: Optional[str] = None,
                 MeasurementService=None):
        """Inject ffmpeg paths + measurement service; default-construct from WorkerContext when omitted."""
        self._FFmpegPath = FFmpegPath
        self._FFprobePath = FFprobePath
        self._MeasurementService = MeasurementService

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S3
    def HandlePostEncode(self, TranscodeAttemptId, MediaFileId):
        """Resolve post-replacement canonical path + invoke probe; never raises into the encode flow."""
        try:
            Path = self.ResolvePostReplacementCanonicalPath(MediaFileId)
            if not Path:
                LoggingService.LogWarning(
                    f"Post-encode probe skipped: canonical path unresolved for MediaFileId={MediaFileId}",
                    "PostEncodeAudioHandler", "HandlePostEncode",
                )
                return False
            Svc = self._ResolveMeasurementService()
            if Svc is None:
                LoggingService.LogWarning(
                    f"Post-encode probe skipped: measurement service unavailable for AttemptId={TranscodeAttemptId}",
                    "PostEncodeAudioHandler", "HandlePostEncode",
                )
                return False
            return Svc.Probe(TranscodeAttemptId, Path)
        except Exception as Ex:
            LoggingService.LogException(
                f"Post-encode audio handler failed for AttemptId={TranscodeAttemptId}",
                Ex, "PostEncodeAudioHandler", "HandlePostEncode",
            )
            return False

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S3
    def ResolvePostReplacementCanonicalPath(self, MediaFileId):
        """Join MediaFiles + StorageRoots to build the Windows-flavored canonical path; None when unresolved."""
        try:
            Rows = DatabaseService().ExecuteQuery(CANONICAL_PATH_SQL, (MediaFileId,))
            if not Rows:
                return None
            Prefix = (Rows[0].get('canonicalprefix') or '').rstrip('/\\')
            Rel = Rows[0].get('relativepath') or ''
            if not Rel:
                return None
            Sep = '\\' if '\\' in Prefix or ':' in Prefix else '/'
            return Prefix + Sep + Rel
        except Exception as Ex:
            LoggingService.LogException(
                f"Canonical path resolution failed for MediaFileId={MediaFileId}",
                Ex, "PostEncodeAudioHandler", "ResolvePostReplacementCanonicalPath",
            )
            return None

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S3
    def _ResolveMeasurementService(self):
        """Return the injected measurement service or default-construct one bound to current ffmpeg paths."""
        if self._MeasurementService is not None:
            return self._MeasurementService
        try:
            from Features.AudioNormalization.Services.PostEncodeMeasurementService import (
                PostEncodeMeasurementService,
            )
            return PostEncodeMeasurementService(
                FFmpegPath=self._FFmpegPath,
                FFprobePath=self._FFprobePath,
            )
        except Exception as Ex:
            LoggingService.LogException(
                "PostEncodeAudioHandler default measurement service construction failed",
                Ex, "PostEncodeAudioHandler", "_ResolveMeasurementService",
            )
            return None
