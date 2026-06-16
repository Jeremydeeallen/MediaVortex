import json
import os
import re
import subprocess
from typing import List, Optional

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


WRITE_CACHE_SQL = (
    "UPDATE MediaFiles SET AudioStreamLanguageDetectionsJson = %s::jsonb WHERE Id = %s"
)


LOAD_CACHE_SQL = (
    "SELECT AudioStreamLanguageDetectionsJson FROM MediaFiles WHERE Id = %s"
)


WHISPER_MODEL_SETTING = 'WhisperModelPath'
WHISPER_LANG_RE = re.compile(r"detected language:\s*([a-z]{2,3})", re.IGNORECASE)
WHISPER_PROB_RE = re.compile(r"detected language probability:\s*([0-9.]+)", re.IGNORECASE)


# directive: audio-vertical-compliance-and-activity | # see audio-normalization.C19
def _ResolveWhisperModelPath():
    """Read SystemSettings.WhisperModelPath fresh per call (db-is-authority); None when unset."""
    try:
        from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
        Value = SystemSettingsRepository().GetSystemSetting(WHISPER_MODEL_SETTING) or ''
        return Value.strip() or None
    except Exception:
        return None


# directive: audio-vertical-compliance-and-activity | # see audio-normalization.C19
class _StubLanguageIdBackend:
    """Fallback backend when no Whisper model is configured; returns 'und' confidence 0."""

    # directive: audio-vertical-compliance-and-activity | # see audio-normalization.C19
    def Detect(self, LocalFilePath, StreamIndex, DurationSeconds=60):
        """Stub: returns 'und' confidence 0.0."""
        return {'Language': 'und', 'Confidence': 0.0}


# directive: audio-vertical-compliance-and-activity | # see audio-normalization.C19
class WhisperFfmpegBackend:
    """Real backend: invokes ffmpeg's --enable-whisper filter on first DurationSeconds of audio, parses detected language."""

    DEFAULT_TIMEOUT_SECONDS = 120

    # directive: audio-vertical-compliance-and-activity | # see audio-normalization.C19
    def __init__(self, FFmpegPath=None, ModelPath=None, TimeoutSeconds=None):
        """Bind to specific ffmpeg + model paths; ModelPath defaults to SystemSettings.WhisperModelPath."""
        self._FFmpegPath = FFmpegPath
        self._ModelPath = ModelPath or _ResolveWhisperModelPath()
        self._Timeout = TimeoutSeconds or self.DEFAULT_TIMEOUT_SECONDS

    # directive: audio-vertical-compliance-and-activity | # see audio-normalization.C19
    def _ResolveFFmpegPath(self):
        """Return the bound override or the WorkerContext value; None when neither available."""
        if self._FFmpegPath:
            return self._FFmpegPath
        try:
            from Core.WorkerContext import WorkerContext
            Ctx = WorkerContext.Current()
            if Ctx and Ctx.FFmpegPath:
                return Ctx.FFmpegPath
        except Exception:
            pass
        return None

    # directive: audio-vertical-compliance-and-activity | # see audio-normalization.C19
    def IsAvailable(self):
        """True when ffmpeg + a model file are resolvable + the model exists on disk."""
        return bool(self._ResolveFFmpegPath() and self._ModelPath and os.path.exists(self._ModelPath))

    # directive: audio-vertical-compliance-and-activity | # see audio-normalization.C19
    def Detect(self, LocalFilePath, StreamIndex, DurationSeconds=60):
        """Run ffmpeg whisper filter on first DurationSeconds; return {Language, Confidence}; 'und' on failure."""
        Fp = self._ResolveFFmpegPath()
        if not Fp or not self._ModelPath:
            return {'Language': 'und', 'Confidence': 0.0, 'Error': 'whisper_backend_unavailable'}
        NullSink = 'NUL' if os.name == 'nt' else '/dev/null'
        Cmd = [
            Fp, '-hide_banner', '-nostdin',
            '-t', str(int(DurationSeconds)),
            '-i', LocalFilePath,
            '-map', f'0:a:{StreamIndex}',
            '-af', f'whisper=model={self._ModelPath}:queue=10:destination=-',
            '-f', 'null', NullSink,
        ]
        try:
            Result = subprocess.run(
                Cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                timeout=self._Timeout, check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as Ex:
            return {'Language': 'und', 'Confidence': 0.0, 'Error': type(Ex).__name__}
        Stderr = Result.stderr.decode('utf-8', errors='replace') if Result.stderr else ''
        Match = WHISPER_LANG_RE.search(Stderr)
        Prob = WHISPER_PROB_RE.search(Stderr)
        if not Match:
            return {'Language': 'und', 'Confidence': 0.0, 'Error': 'language_not_detected'}
        return {
            'Language': Match.group(1).strip().lower(),
            'Confidence': float(Prob.group(1)) if Prob else 0.0,
        }


# directive: audio-vertical-compliance-and-activity | # see audio-normalization.C19
def _DefaultBackend():
    """Pick WhisperFfmpegBackend when available, otherwise the stub."""
    Candidate = WhisperFfmpegBackend()
    return Candidate if Candidate.IsAvailable() else _StubLanguageIdBackend()


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C19
class LanguageEnrichmentService:
    """Schedule + cache speech-language detections per MediaFile; backend pluggable for Whisper integration."""

    # directive: perfect-audio-vertical | # see audio-normalization.C19
    def __init__(self, Backend=None):
        """Inject a language-ID backend; default picks WhisperFfmpegBackend when a model is configured, else stub."""
        self.Backend = Backend or _DefaultBackend()

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
