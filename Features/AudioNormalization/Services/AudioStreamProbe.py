import json
import subprocess
from typing import List, Optional

from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalExists


# directive: audio-vertical-live-evidence | # see audio-normalization.L1
class AudioStreamProbe:
    """Single source of truth for `ffprobe -select_streams a` against a local source file."""

    DEFAULT_TIMEOUT_SECONDS = 30

    # directive: audio-vertical-live-evidence | # see audio-normalization.L1
    def __init__(self, FFprobePath: Optional[str] = None, TimeoutSeconds: Optional[int] = None):
        """Bind a specific ffprobe path; tests inject a stub."""
        self._FFprobePath = FFprobePath
        self._Timeout = int(TimeoutSeconds or self.DEFAULT_TIMEOUT_SECONDS)

    # directive: audio-vertical-live-evidence | # see audio-normalization.L1
    def Probe(self, LocalSourcePath) -> List[dict]:
        """Return the audio-only stream list with sequential audio-only indices, language tags, and disposition.default."""
        Ffprobe = self._ResolveFFprobePath()
        if not Ffprobe or not LocalSourcePath or not LocalExists(LocalSourcePath):
            return []
        Cmd = [
            Ffprobe, '-v', 'error', '-select_streams', 'a',
            '-show_entries', 'stream=index:stream_tags=language:stream_disposition=default',
            '-of', 'json', LocalSourcePath,
        ]
        try:
            Result = subprocess.run(
                Cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=self._Timeout, check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as Ex:
            LoggingService.LogException(
                f"AudioStreamProbe.Probe subprocess failed for {LocalSourcePath}",
                Ex, "AudioStreamProbe", "Probe",
            )
            return []
        try:
            Data = json.loads(Result.stdout.decode('utf-8', errors='replace') or '{}')
        except ValueError:
            return []
        Streams = Data.get('streams') or []
        return [
            {
                'index': AudioOnlyIdx,
                'tags': S.get('tags') or {},
                'disposition': S.get('disposition') or {},
            }
            for AudioOnlyIdx, S in enumerate(Streams)
        ]

    # directive: audio-vertical-live-evidence | # see audio-normalization.L1
    def _ResolveFFprobePath(self):
        """Use the bound path; fall back to WorkerContext.FFprobePath; None when neither set."""
        if self._FFprobePath:
            return self._FFprobePath
        try:
            from Core.WorkerContext import WorkerContext
            Ctx = WorkerContext.Current()
            if Ctx and getattr(Ctx, 'FFprobePath', None):
                return Ctx.FFprobePath
        except Exception:
            pass
        return None
