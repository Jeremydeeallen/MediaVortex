import os
import subprocess
import tempfile
import threading

from Core.SubprocessUtil import NoWindowFlags


# directive: audio-language-detection
class FasterWhisperBackend:

    _MODEL_LOCK = threading.Lock()
    _MODEL_CACHE = {}

    DEFAULT_MODEL_SIZE = 'base'
    DEFAULT_TIMEOUT_SECONDS = 120
    NAME = 'faster-whisper-base'

    def __init__(self, FFmpegPath=None, ModelSize=None, TimeoutSeconds=None):
        self._FFmpegPath = FFmpegPath
        self._ModelSize = (ModelSize or self.DEFAULT_MODEL_SIZE).strip().lower()
        self._Timeout = TimeoutSeconds or self.DEFAULT_TIMEOUT_SECONDS

    def IsAvailable(self):
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False
        return bool(self._ResolveFFmpegPath())

    def Detect(self, LocalFilePath, StreamIndex, DurationSeconds=60):
        FFmpeg = self._ResolveFFmpegPath()
        if not FFmpeg:
            return {'Language': 'und', 'Confidence': 0.0, 'Error': 'ffmpeg_unavailable'}
        Fd, WavPath = tempfile.mkstemp(prefix='fw_', suffix='.wav')
        os.close(Fd)
        Cmd = [
            FFmpeg, '-hide_banner', '-nostdin',
            '-t', str(int(DurationSeconds)),
            '-i', LocalFilePath,
            '-map', f'0:a:{StreamIndex}',
            '-ac', '1', '-ar', '16000',
            '-y', WavPath,
        ]
        try:
            Res = subprocess.run(
                Cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                timeout=self._Timeout, check=False,
                creationflags=NoWindowFlags(),
            )
            if Res.returncode != 0:
                return {'Language': 'und', 'Confidence': 0.0, 'Error': f'ffmpeg_extract_rc={Res.returncode}'}
            return self._DetectFromWav(WavPath)
        except (subprocess.TimeoutExpired, FileNotFoundError) as Ex:
            return {'Language': 'und', 'Confidence': 0.0, 'Error': type(Ex).__name__}
        finally:
            try:
                os.remove(WavPath)
            except OSError:
                pass

    def _DetectFromWav(self, WavPath):
        try:
            from faster_whisper.audio import decode_audio
        except ImportError:
            return {'Language': 'und', 'Confidence': 0.0, 'Error': 'faster_whisper_missing'}
        Model = self._GetOrLoadModel()
        if Model is None:
            return {'Language': 'und', 'Confidence': 0.0, 'Error': 'faster_whisper_missing'}
        try:
            AudioArray = decode_audio(WavPath, sampling_rate=16000)
            Lang, Prob, _ = Model.detect_language(AudioArray)
            return {'Language': str(Lang).lower(), 'Confidence': float(Prob)}
        except Exception as Ex:
            return {'Language': 'und', 'Confidence': 0.0, 'Error': type(Ex).__name__}

    def _GetOrLoadModel(self):
        with self._MODEL_LOCK:
            Model = self._MODEL_CACHE.get(self._ModelSize)
            if Model is None:
                try:
                    from faster_whisper import WhisperModel
                except ImportError:
                    return None
                Model = WhisperModel(self._ModelSize, device='cpu', compute_type='int8')
                self._MODEL_CACHE[self._ModelSize] = Model
            return Model

    def _ResolveFFmpegPath(self):
        if self._FFmpegPath:
            return self._FFmpegPath
        try:
            from Core.WorkerContext import WorkerContext
            Ctx = WorkerContext.TryCurrentOrTemplate()
            if Ctx and getattr(Ctx, 'FFmpegPath', None):
                return Ctx.FFmpegPath
        except Exception:
            pass
        return None
