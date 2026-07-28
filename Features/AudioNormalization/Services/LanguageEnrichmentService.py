import os
import subprocess

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalBasename, LocalDirname, LocalExists, LocalJoin, LocalSplitExt

from Features.AudioNormalization.Repositories.MediaFileLanguageDetectionsRepository import MediaFileLanguageDetectionsRepository
from Features.AudioNormalization.Services.AudioStreamProbe import AudioStreamProbe
from Features.AudioNormalization.Services.FasterWhisperBackend import FasterWhisperBackend
from Features.AudioNormalization.Services.LanguageEnrichmentError import LanguageEnrichmentError


ISO639_1_TO_2 = {
    'en': 'eng', 'es': 'spa', 'fr': 'fra', 'de': 'deu', 'it': 'ita',
    'pt': 'por', 'ja': 'jpn', 'zh': 'zho', 'ko': 'kor', 'ru': 'rus',
    'ar': 'ara', 'hi': 'hin', 'nl': 'nld', 'sv': 'swe', 'no': 'nor',
    'da': 'dan', 'fi': 'fin', 'pl': 'pol', 'tr': 'tur', 'th': 'tha',
    'vi': 'vie', 'id': 'ind', 'he': 'heb', 'cs': 'ces', 'el': 'ell',
    'hu': 'hun', 'ro': 'ron', 'uk': 'ukr', 'ca': 'cat', 'bg': 'bul',
}


def NormalizeIso639(Code):
    if not Code:
        return ''
    C = Code.strip().lower()
    if len(C) == 2:
        return ISO639_1_TO_2.get(C, C)
    return C


ENGLISH_CODES = ('en', 'eng')


# directive: audio-language-detection
class _StubLanguageIdBackend:

    NAME = 'stub'

    def Detect(self, LocalFilePath, StreamIndex, DurationSeconds=60):
        return {'Language': 'und', 'Confidence': 0.0}


# directive: audio-language-detection
def _DefaultBackend():
    try:
        Faster = FasterWhisperBackend()
        if Faster.IsAvailable():
            return Faster
    except Exception as Ex:
        LoggingService.LogWarning(
            f"FasterWhisperBackend.IsAvailable raised {type(Ex).__name__}: {Ex}",
            'LanguageEnrichmentService', '_DefaultBackend',
        )
    return _StubLanguageIdBackend()


# directive: audio-language-detection
class LanguageEnrichmentService:

    def __init__(self, Backend=None, Detections=None):
        self.Backend = Backend or _DefaultBackend()
        self.Detections = Detections or MediaFileLanguageDetectionsRepository()

    def GetDetectionsMap(self, MediaFileId):
        return self.Detections.GetDetectionsMap(MediaFileId)

    def HasDetections(self, MediaFileId):
        return self.Detections.ExistsForMediaFile(MediaFileId)

    def Enrich(self, MediaFileId, LocalFilePath, StreamIndices=(0,)):
        BackendName = getattr(self.Backend, 'NAME', type(self.Backend).__name__)
        Existing = self.GetDetectionsMap(MediaFileId)
        for Idx in StreamIndices:
            if str(Idx) in Existing:
                continue
            try:
                Result = self.Backend.Detect(LocalFilePath, Idx)
                self._PersistDetection(MediaFileId, Idx, Result, BackendName)
                Existing[str(Idx)] = {
                    'Language': str(Result.get('Language') or 'und').lower(),
                    'Confidence': float(Result.get('Confidence') or 0.0),
                }
            except Exception as Ex:
                LoggingService.LogException(
                    f"LanguageEnrichment.Detect failed for MediaFileId={MediaFileId} stream={Idx}",
                    Ex, "LanguageEnrichmentService", "Enrich",
                )
        return Existing

    def _PersistDetection(self, MediaFileId, StreamIndex, Result, BackendName):
        Lang = str(Result.get('Language') or 'und').strip().lower()
        Conf = float(Result.get('Confidence') or 0.0)
        self.Detections.Insert(MediaFileId, StreamIndex, Lang, Conf, BackendName)

    def EnrichAndStamp(self, MediaFileId, LocalFilePath):
        Streams = AudioStreamProbe().Probe(LocalFilePath)
        if not Streams:
            raise LanguageEnrichmentError(MediaFileId, 'no_audio_streams')
        StreamIndices = tuple(range(len(Streams)))
        Detections = self.Enrich(MediaFileId, LocalFilePath, StreamIndices)
        MinConfidence = self._ResolveMinConfidence()
        Stamps = self._DecideStamps(Streams, Detections, MinConfidence)
        if not Stamps:
            return {'Stamped': False, 'Reason': 'no_english_or_low_confidence', 'Detections': Detections}
        return self._StampContainer(MediaFileId, LocalFilePath, Stamps, Detections)

    def _DecideStamps(self, Streams, Detections, MinConfidence):
        Stamps = []
        for Idx in range(len(Streams)):
            D = Detections.get(str(Idx)) or {}
            Lang = str(D.get('Language') or '').lower()
            Conf = float(D.get('Confidence') or 0.0)
            if Lang not in ENGLISH_CODES:
                continue
            if Conf < MinConfidence:
                continue
            SourceLang = NormalizeIso639((Streams[Idx].get('tags') or {}).get('language'))
            if SourceLang == 'eng':
                continue
            Stamps.append((Idx, 'eng'))
        return Stamps

    def _StampContainer(self, MediaFileId, LocalFilePath, Stamps, Detections):
        FfmpegPath = self._ResolveFFmpegPath()
        if not FfmpegPath:
            raise LanguageEnrichmentError(MediaFileId, 'ffmpeg_path_unresolved')
        OrigDir = LocalDirname(LocalFilePath)
        BaseName, Ext = LocalSplitExt(LocalBasename(LocalFilePath))
        InProgressPath = LocalJoin(OrigDir, f'{BaseName}.langfix.inprogress{Ext}')
        Cmd = [FfmpegPath, '-hide_banner', '-nostdin', '-i', LocalFilePath, '-map', '0', '-c', 'copy']
        for Idx, Lang in Stamps:
            Cmd += [f'-metadata:s:a:{Idx}', f'language={Lang}']
        Cmd += ['-y', InProgressPath]
        try:
            Result = subprocess.run(Cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300, check=False)
        except (subprocess.TimeoutExpired, FileNotFoundError) as Ex:
            self._SafeUnlink(InProgressPath)
            raise LanguageEnrichmentError(MediaFileId, 'ffmpeg_subprocess_error', Detail=type(Ex).__name__)
        if Result.returncode != 0:
            Stderr = (Result.stderr or b'').decode('utf-8', errors='replace')[:400]
            self._SafeUnlink(InProgressPath)
            raise LanguageEnrichmentError(MediaFileId, 'ffmpeg_returncode_nonzero', Detail=f"rc={Result.returncode} stderr={Stderr}")
        try:
            os.replace(InProgressPath, LocalFilePath)
        except OSError as Ex:
            self._SafeUnlink(InProgressPath)
            raise LanguageEnrichmentError(MediaFileId, 'file_replace_failed', Detail=str(Ex))
        try:
            from Features.MediaProbe.MediaProbeBusinessService import MediaProbeBusinessService
            Reprobe = MediaProbeBusinessService().ProbeFile(MediaFileId, Force=True)
        except Exception as Ex:
            raise LanguageEnrichmentError(MediaFileId, 'reprobe_failed', Detail=str(Ex))
        return {'Stamped': True, 'StampedStreams': Stamps, 'Detections': Detections, 'ReprobeResult': Reprobe}

    def _ResolveMinConfidence(self):
        Override = getattr(self, '_MinConfidenceOverride', None)
        if Override is not None:
            return float(Override)
        try:
            from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
            Val = SystemSettingsRepository().GetSystemSetting('MinDetectionConfidence')
            return float(Val) if Val else 0.85
        except Exception:
            return 0.85

    def _ResolveFFmpegPath(self):
        try:
            from Core.WorkerContext import WorkerContext
            Ctx = WorkerContext.TryCurrent()
            if Ctx and getattr(Ctx, 'FFmpegPath', None):
                return Ctx.FFmpegPath
        except Exception:
            pass
        return None

    def _SafeUnlink(self, Path):
        try:
            os.remove(Path)
        except OSError:
            pass
