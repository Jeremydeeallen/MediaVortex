import json
from typing import List, Optional

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


WRITE_CACHE_SQL = (
    "UPDATE MediaFiles SET AudioStreamLanguageDetectionsJson = %s::jsonb WHERE Id = %s"
)


LOAD_CACHE_SQL = (
    "SELECT AudioStreamLanguageDetectionsJson FROM MediaFiles WHERE Id = %s"
)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
class _StubLanguageIdBackend:
    """Default backend: returns 'und' for every stream. Real Whisper integration is a follow-up."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
    def Detect(self, LocalFilePath, StreamIndex, DurationSeconds=60):
        """Stub: returns 'und' confidence 0.0; real Whisper backend implements this."""
        return {'Language': 'und', 'Confidence': 0.0}


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
class LanguageEnrichmentService:
    """Schedule + cache speech-language detections per MediaFile; backend pluggable for Whisper integration."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
    def __init__(self, Backend=None):
        """Inject a language-ID backend; default stub returns 'und'."""
        self.Backend = Backend or _StubLanguageIdBackend()

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
    def GetCached(self, MediaFileId):
        """Return cached AudioStreamLanguageDetectionsJson for a MediaFile or None."""
        Rows = DatabaseService().ExecuteQuery(LOAD_CACHE_SQL, (MediaFileId,))
        if not Rows:
            return None
        Cache = Rows[0].get('audiostreamlanguagedetectionsjson')
        if Cache is None:
            return None
        if isinstance(Cache, str):
            try:
                return json.loads(Cache)
            except (ValueError, TypeError):
                return None
        return Cache

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
    def Enrich(self, MediaFileId, LocalFilePath, StreamIndices=(0,)):
        """Run the backend for every requested stream; persist cache; return the cache dict."""
        Cached = self.GetCached(MediaFileId) or {}
        for Idx in StreamIndices:
            if str(Idx) in Cached or Idx in Cached:
                continue
            try:
                Result = self.Backend.Detect(LocalFilePath, Idx)
                Cached[str(Idx)] = Result
            except Exception as Ex:
                LoggingService.LogException(
                    f"LanguageEnrichment.Detect failed for MediaFileId={MediaFileId} stream={Idx}",
                    Ex, "LanguageEnrichmentService", "Enrich",
                )
                Cached[str(Idx)] = {'Language': 'und', 'Confidence': 0.0, 'Error': str(Ex)}

        try:
            DatabaseService().ExecuteNonQuery(WRITE_CACHE_SQL, (json.dumps(Cached), MediaFileId))
        except Exception as Ex:
            LoggingService.LogException(
                f"LanguageEnrichment.Enrich persist failed for MediaFileId={MediaFileId}",
                Ex, "LanguageEnrichmentService", "Enrich",
            )
        return Cached

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
    def HasCacheForAllStreams(self, MediaFileId, StreamIndices):
        """True when every requested stream has a cached detection; admission skips enrichment."""
        Cached = self.GetCached(MediaFileId) or {}
        for Idx in StreamIndices:
            if str(Idx) not in Cached and Idx not in Cached:
                return False
        return True
