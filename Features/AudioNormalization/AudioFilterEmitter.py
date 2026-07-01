# directive: audio-dialog-boost-real | # see audio-normalization.C8
from typing import List, Optional

from Features.AudioNormalization.AudioDispositionResolver import AudioDispositionResolver
from Features.AudioNormalization.LanguageDetector import LanguageDetector


TRACK0_BITRATE_PER_CHANNEL_KBPS = 64
TRACK0_MIN_PER_CHANNEL_KBPS = 48
TRACK1_STEREO_BITRATE_KBPS = 192
TRACK1_VOCALS_RMS_FALLBACK_DBFS = -50.0
DEFAULT_TARGET_LUFS = -23.0
DEFAULT_TARGET_TRUE_PEAK_DBTP = -2.0
DIALOG_BOOST_TARGET_LUFS = -20.0
DIALOG_BOOST_TARGET_LRA = 5.0
SAMPLE_LIMIT_HEADROOM_DB = 4.0


# directive: audio-dialog-boost-real | # see audio-normalization.C3
def _DbToLinear(Db):
    return 10.0 ** (float(Db) / 20.0)


# directive: audio-dialog-boost-real | # see audio-normalization.C8
class TrackBlock:

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def __init__(self, Label, Language, Strategy):
        self.Label = Label
        self.Language = Language
        self.Strategy = Strategy
        self.InputArgs = []
        self.MapArgs = []
        self.CodecArgs = []
        self.FilterArgs = []
        self.MetadataArgs = []
        self.DispositionArgs = []


# directive: audio-dialog-boost-real | # see audio-normalization.C8
def _GetField(Obj, Name):
    if hasattr(Obj, Name):
        return getattr(Obj, Name)
    if hasattr(Obj, 'get'):
        Val = Obj.get(Name)
        if Val is not None:
            return Val
        return Obj.get(Name.lower())
    return None


# directive: audio-dialog-boost-real | # see audio-normalization.C3
def _BuildLinearLoudnormFilter(MediaFile, TargetLufs, TargetTruePeakDbtp):
    SrcI = float(_GetField(MediaFile, 'SourceIntegratedLufs'))
    SrcLra = float(_GetField(MediaFile, 'SourceLoudnessRangeLU'))
    SrcTp = float(_GetField(MediaFile, 'SourceTruePeakDbtp'))
    SrcThresh = float(_GetField(MediaFile, 'SourceIntegratedThresholdLufs'))
    Measured = (
        f"measured_I={SrcI:.2f}"
        f":measured_LRA={SrcLra:.2f}"
        f":measured_TP={SrcTp:.2f}"
        f":measured_thresh={SrcThresh:.2f}"
    )
    return (
        f"loudnorm=I={float(TargetLufs):.2f}"
        f":LRA={max(SrcLra, 1.0):.2f}"
        f":TP={float(TargetTruePeakDbtp):.2f}"
        f":{Measured}"
        f":linear=true"
    )


# directive: audio-dialog-boost-real | # see audio-normalization.C3
def _BuildDialogBoostLoudnormFilter(MediaFile):
    return (
        f"loudnorm=I={DIALOG_BOOST_TARGET_LUFS:.2f}"
        f":LRA={DIALOG_BOOST_TARGET_LRA:.2f}"
        f":TP={DEFAULT_TARGET_TRUE_PEAK_DBTP:.2f}"
    )


# directive: audio-dialog-boost-real | # see audio-normalization.C8
class AudioFilterEmitter:

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def __init__(self, LanguageDetectorInstance=None, DispositionResolver=None):
        self.LanguageDetector = LanguageDetectorInstance or LanguageDetector()
        self.DispositionResolver = DispositionResolver or AudioDispositionResolver()

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def EmitTracks(self, MediaFile, Policy, AudioStreams=None, LibraryDefault=None, DemucsPremixPath=None, VocalsRmsDbfs=None):
        if AudioStreams is None:
            AudioStreams = [{'index': 0, 'tags': {}, 'disposition': {}}]
        EffectiveDefault = LibraryDefault or _GetField(Policy, 'LanguageDefault')
        SpeechCache = _GetField(MediaFile, 'AudioStreamLanguageDetectionsJson')
        EnableSpeech = bool(_GetField(Policy, 'EnableSpeechLanguageDetection'))
        Detection = self.LanguageDetector.Detect(
            AudioStreams,
            LibraryDefault=EffectiveDefault,
            SpeechCache=SpeechCache,
            EnableSpeechLayer=EnableSpeech,
        )
        StreamLanguageMap = {Sl.StreamIndex: Sl.Language for Sl in Detection.StreamLanguages}
        DefaultLanguage = self._PickDefaultLanguage(AudioStreams, StreamLanguageMap, EffectiveDefault)
        TargetLufs = float(_GetField(Policy, 'TargetIntegratedLufs') or DEFAULT_TARGET_LUFS)
        TargetTp = float(_GetField(Policy, 'TargetTruePeakDbtp') or DEFAULT_TARGET_TRUE_PEAK_DBTP)
        EmitDialogBoost = self._ShouldEmitDialogBoost(DemucsPremixPath, VocalsRmsDbfs)
        Blocks = []
        OutputIndex = 0
        for Stream in AudioStreams:
            StreamIdx = Stream.get('index', 0)
            Language = StreamLanguageMap.get(StreamIdx, 'und')
            IsDefaultLanguage = (Language == DefaultLanguage)
            OriginalIsDefault = (IsDefaultLanguage and not (EmitDialogBoost and IsDefaultLanguage))
            Blocks.append(self._BuildOriginalBlock(MediaFile, Stream, Language, StreamIdx, OutputIndex, OriginalIsDefault, TargetLufs, TargetTp))
            OutputIndex += 1
            if EmitDialogBoost and IsDefaultLanguage:
                Blocks.append(self._BuildDialogBoostBlock(MediaFile, Language, OutputIndex, DemucsPremixPath))
                OutputIndex += 1
        return Blocks

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def _ShouldEmitDialogBoost(self, DemucsPremixPath, VocalsRmsDbfs):
        if not DemucsPremixPath:
            return False
        if VocalsRmsDbfs is not None and float(VocalsRmsDbfs) <= TRACK1_VOCALS_RMS_FALLBACK_DBFS:
            return False
        return True

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def _BuildOriginalBlock(self, MediaFile, Stream, Language, StreamIdx, OutputIndex, IsDefault, TargetLufs, TargetTp):
        Channels = self._ResolveSourceChannels(MediaFile)
        Bitrate = max(TRACK0_BITRATE_PER_CHANNEL_KBPS, TRACK0_MIN_PER_CHANNEL_KBPS) * Channels
        Block = TrackBlock(Label='Original', Language=Language, Strategy='linear_loudnorm')
        Block.MapArgs = ['-map', f'0:a:{StreamIdx}']
        Block.CodecArgs = [
            f'-c:a:{OutputIndex}', 'aac',
            f'-b:a:{OutputIndex}', f'{Bitrate}k',
            f'-ar:{OutputIndex}', '48000',
        ]
        Filter = _BuildLinearLoudnormFilter(MediaFile, TargetLufs, TargetTp) + f",alimiter=level_in=1:level_out=1:limit={_DbToLinear(TargetTp - SAMPLE_LIMIT_HEADROOM_DB):.4f}:attack=1:release=50:level=false"
        Block.FilterArgs = [f'-filter:a:{OutputIndex}', Filter]
        Block.MetadataArgs = self._BuildMetadataArgs(Language, 'Original', OutputIndex)
        Block.DispositionArgs = [f'-disposition:a:{OutputIndex}', '1' if IsDefault else '0']
        return Block

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def _BuildDialogBoostBlock(self, MediaFile, Language, OutputIndex, DemucsPremixPath):
        Block = TrackBlock(Label='Dialog Boost', Language=Language, Strategy='demucs_boost')
        Block.InputArgs = ['-i', DemucsPremixPath]
        Block.MapArgs = ['-map', '1:a:0']
        Block.CodecArgs = [
            f'-c:a:{OutputIndex}', 'aac',
            f'-b:a:{OutputIndex}', f'{TRACK1_STEREO_BITRATE_KBPS}k',
            f'-ar:{OutputIndex}', '48000',
        ]
        Filter = _BuildDialogBoostLoudnormFilter(MediaFile) + f",alimiter=level_in=1:level_out=1:limit={_DbToLinear(DEFAULT_TARGET_TRUE_PEAK_DBTP - SAMPLE_LIMIT_HEADROOM_DB):.4f}:attack=1:release=50:level=false"
        Block.FilterArgs = [f'-filter:a:{OutputIndex}', Filter]
        Block.MetadataArgs = self._BuildMetadataArgs(Language, 'Dialog Boost', OutputIndex)
        Block.DispositionArgs = [f'-disposition:a:{OutputIndex}', '1']
        return Block

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def _BuildMetadataArgs(self, Language, Label, OutputIndex):
        return [
            f'-metadata:s:a:{OutputIndex}', f'language={Language}',
            f'-metadata:s:a:{OutputIndex}', f'title={Label}',
            f'-metadata:s:a:{OutputIndex}', f'handler_name={Label} ({Language})',
        ]

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def _ResolveSourceChannels(self, MediaFile):
        Channels = _GetField(MediaFile, 'AudioChannels')
        try:
            ChannelsInt = int(Channels) if Channels else 2
        except (TypeError, ValueError):
            ChannelsInt = 2
        return max(1, min(8, ChannelsInt))

    # directive: audio-dialog-boost-real | # see audio-normalization.C24
    def _PickDefaultLanguage(self, AudioStreams, StreamLanguageMap, LibraryDefault):
        Present = [StreamLanguageMap.get(S.get('index'), 'und') for S in AudioStreams]
        Result = self.DispositionResolver.PickDefaultLanguage(Present, LibraryDefault)
        if hasattr(Result, 'Plan'):
            Plan = Result.Plan
            return Plan.get('Language')
        return None
