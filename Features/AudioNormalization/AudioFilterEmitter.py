# directive: audio-dialog-boost-real | # see audio-normalization.C8
from typing import List, Optional

from Features.AudioNormalization.AudioDispositionResolver import AudioDispositionResolver
from Features.AudioNormalization.AudioStrategyResult import AudioPolicyUnresolvedError
from Features.AudioNormalization.LanguageDetector import LanguageDetector
from Features.AudioNormalization.Repositories.AudioComplianceRulesRepository import AudioComplianceRulesRepository


# directive: audio-dialog-boost-real | # see audio-normalization.C8
def _DbToLinear(Db):
    return 10.0 ** (float(Db) / 20.0)


# directive: audio-dialog-boost-real | # see audio-normalization.C8
def _ResolveFfmpegCodec(CodecName):
    Normalized = str(CodecName or 'aac').strip().lower()
    return {'opus': 'libopus', 'aac': 'aac', 'libopus': 'libopus'}.get(Normalized, 'aac')


# directive: audio-dialog-boost-real | # see audio-normalization.C8
MIN_TRANSPARENT_KBPS_PER_CH = 48


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


# directive: audio-dialog-boost-real | # see audio-normalization.C8
def _BuildTrack0Chain(MediaFile, TargetLufs, TargetTruePeakDbtp, SampleLimitHeadroomDb):
    SrcI = float(_GetField(MediaFile, 'SourceIntegratedLufs'))
    SrcLra = float(_GetField(MediaFile, 'SourceLoudnessRangeLU'))
    SrcTp = float(_GetField(MediaFile, 'SourceTruePeakDbtp'))
    SrcThresh = float(_GetField(MediaFile, 'SourceIntegratedThresholdLufs'))
    EffectiveTargetTp = float(TargetTruePeakDbtp) - float(SampleLimitHeadroomDb)
    GainShift = float(TargetLufs) - SrcI
    ClipNeeded = max(0.0, SrcTp + GainShift - EffectiveTargetTp)
    if ClipNeeded > 0.0:
        PreLimitDb = SrcTp - ClipNeeded
        PreLimitLinear = _DbToLinear(PreLimitDb)
        EffectiveMeasuredTp = PreLimitDb
        PreChain = f"alimiter=level_in=1:level_out=1:limit={PreLimitLinear:.4f}:attack=1:release=50:level=false,"
    else:
        EffectiveMeasuredTp = SrcTp
        PreChain = ""
    Measured = (
        f"measured_I={SrcI:.2f}"
        f":measured_LRA={SrcLra:.2f}"
        f":measured_TP={EffectiveMeasuredTp:.2f}"
        f":measured_thresh={SrcThresh:.2f}"
    )
    return (
        f"{PreChain}"
        f"loudnorm=I={float(TargetLufs):.2f}"
        f":LRA={max(SrcLra, 1.0):.2f}"
        f":TP={EffectiveTargetTp:.2f}"
        f":{Measured}"
        f":linear=true"
    )


# directive: audio-dialog-boost-real | # see audio-normalization.C8
def _BuildDialogBoostLoudnormFilter(TargetLufs, TargetLra, TargetTruePeakDbtp, MeasuredI=None, MeasuredLra=None, MeasuredTp=None, MeasuredThresh=None):
    Base = (
        f"loudnorm=I={float(TargetLufs):.2f}"
        f":LRA={float(TargetLra):.2f}"
        f":TP={float(TargetTruePeakDbtp):.2f}"
    )
    if MeasuredI is not None and MeasuredLra is not None and MeasuredTp is not None and MeasuredThresh is not None:
        Base += (
            f":measured_I={float(MeasuredI):.2f}"
            f":measured_LRA={float(MeasuredLra):.2f}"
            f":measured_TP={float(MeasuredTp):.2f}"
            f":measured_thresh={float(MeasuredThresh):.2f}"
            f":linear=true"
        )
    return Base


# directive: audio-dialog-boost-real | # see audio-normalization.C8
class AudioFilterEmitter:

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def __init__(self, LanguageDetectorInstance=None, DispositionResolver=None, RulesRepo=None):
        self.LanguageDetector = LanguageDetectorInstance or LanguageDetector()
        self.DispositionResolver = DispositionResolver or AudioDispositionResolver()
        self._RulesRepo = RulesRepo or AudioComplianceRulesRepository()

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def EmitTracks(self, MediaFile, Policy, AudioStreams=None, LibraryDefault=None, DemucsPremixPath=None, VocalsRmsDbfs=None, Rules=None, PremixMeasuredI=None, PremixMeasuredLra=None, PremixMeasuredTp=None, PremixMeasuredThresh=None):
        R = Rules or self._RulesRepo.GetRules()
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
        EmitDialogBoost = self._ShouldEmitDialogBoost(DemucsPremixPath, VocalsRmsDbfs, R['Track1VocalsRmsFallbackDbfs'])
        Blocks = []
        OutputIndex = 0
        for Stream in AudioStreams:
            StreamIdx = Stream.get('index', 0)
            Language = StreamLanguageMap.get(StreamIdx, 'und')
            IsDefaultLanguage = (Language == DefaultLanguage)
            # directive: e2e-bug-fixes | # see e2e-bug-fixes.C26 -- Boost at Track 0 so index-blind TVs get it; default flag on Track 0 stays consistent.
            if EmitDialogBoost and IsDefaultLanguage:
                Blocks.append(self._BuildDialogBoostBlock(Language, OutputIndex, DemucsPremixPath, R, PremixMeasuredI, PremixMeasuredLra, PremixMeasuredTp, PremixMeasuredThresh))
                OutputIndex += 1
                Blocks.append(self._BuildOriginalBlock(MediaFile, Stream, Language, StreamIdx, OutputIndex, False, R))
            else:
                Blocks.append(self._BuildOriginalBlock(MediaFile, Stream, Language, StreamIdx, OutputIndex, IsDefaultLanguage, R))
            OutputIndex += 1
        return Blocks

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def _ShouldEmitDialogBoost(self, DemucsPremixPath, VocalsRmsDbfs, VocalsFallbackDbfs):
        if not DemucsPremixPath:
            return False
        if VocalsRmsDbfs is not None and float(VocalsRmsDbfs) <= float(VocalsFallbackDbfs):
            return False
        return True

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def _BuildOriginalBlock(self, MediaFile, Stream, Language, StreamIdx, OutputIndex, IsDefault, R):
        Channels = self._ResolveSourceChannels(MediaFile)
        Bitrate = max(MIN_TRANSPARENT_KBPS_PER_CH, int(R['Track0BitratePerChannelKbps']), int(R['Track0MinPerChannelKbps'])) * Channels
        TargetLufs = float(R['TargetIntegratedLufs'])
        TargetTp = float(R['TargetTruePeakDbtp'])
        CodecName = _ResolveFfmpegCodec(R.get('Track0Codec', 'aac'))
        Block = TrackBlock(Label='Original', Language=Language, Strategy='linear_loudnorm')
        Block.MapArgs = ['-map', f'0:a:{StreamIdx}']
        Block.CodecArgs = [
            f'-c:a:{OutputIndex}', CodecName,
            f'-b:a:{OutputIndex}', f'{Bitrate}k',
            f'-ar:{OutputIndex}', '48000',
        ]
        if CodecName == 'libopus' and Channels > 2:
            Block.CodecArgs.extend([f'-mapping_family:a:{OutputIndex}', '1'])
        Filter = _BuildTrack0Chain(MediaFile, TargetLufs, TargetTp, float(R['SampleLimitHeadroomDb']))
        if CodecName == 'libopus' and Channels > 2:
            Filter = f"aformat=channel_layouts=5.1|7.1,{Filter}"
        Block.FilterArgs = [f'-filter:a:{OutputIndex}', Filter]
        Block.MetadataArgs = self._BuildMetadataArgs(Language, 'Original', OutputIndex)
        Block.DispositionArgs = [f'-disposition:a:{OutputIndex}', '1' if IsDefault else '0']
        return Block

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def _BuildDialogBoostBlock(self, Language, OutputIndex, DemucsPremixPath, R, MeasuredI=None, MeasuredLra=None, MeasuredTp=None, MeasuredThresh=None):
        TargetTp = float(R['TargetTruePeakDbtp'])
        EffectiveTp = TargetTp - float(R['SampleLimitHeadroomDb'])
        SampleLimit = _DbToLinear(EffectiveTp)
        CodecName = _ResolveFfmpegCodec(R.get('Track1Codec', 'aac'))
        Block = TrackBlock(Label='Dialog Boost', Language=Language, Strategy='demucs_boost')
        Block.InputArgs = ['-i', DemucsPremixPath]
        Block.MapArgs = ['-map', '1:a:0']
        Block.CodecArgs = [
            f'-c:a:{OutputIndex}', CodecName,
            f'-b:a:{OutputIndex}', f"{int(R['Track1StereoBitrateKbps'])}k",
            f'-ar:{OutputIndex}', '48000',
        ]
        Filter = _BuildDialogBoostLoudnormFilter(R['DialogBoostTargetLufs'], R['DialogBoostTargetLra'], EffectiveTp, MeasuredI, MeasuredLra, MeasuredTp, MeasuredThresh) + f",alimiter=level_in=1:level_out=1:limit={SampleLimit:.4f}:attack=1:release=50:level=false"
        Block.FilterArgs = [f'-filter:a:{OutputIndex}', Filter]
        Block.MetadataArgs = self._BuildMetadataArgs(Language, 'Dialog Boost', OutputIndex)
        Block.DispositionArgs = [f'-disposition:a:{OutputIndex}', '1']
        return Block

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def _BuildMetadataArgs(self, Language, Label, OutputIndex):
        return [
            f'-metadata:s:a:{OutputIndex}', f'"language={Language}"',
            f'-metadata:s:a:{OutputIndex}', f'"title={Label}"',
            f'-metadata:s:a:{OutputIndex}', f'"handler_name={Label} ({Language})"',
        ]

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def _ResolveSourceChannels(self, MediaFile):
        Channels = _GetField(MediaFile, 'AudioChannels')
        MediaFileId = _GetField(MediaFile, 'Id')
        if Channels is None or (isinstance(Channels, str) and not Channels.strip()):
            raise AudioPolicyUnresolvedError(
                'AudioChannelsMissing',
                f'MediaFile.Id={MediaFileId} has AudioChannels=NULL; cannot emit audio without known source channel layout. Route to operator review; trigger re-probe. See BUG-0074.',
                None,
            )
        try:
            ChannelsInt = int(Channels)
        except (TypeError, ValueError):
            raise AudioPolicyUnresolvedError(
                'AudioChannelsInvalid',
                f'MediaFile.Id={MediaFileId} has AudioChannels={Channels!r} (unparseable). See BUG-0074.',
                None,
            )
        if ChannelsInt <= 0:
            raise AudioPolicyUnresolvedError(
                'AudioChannelsInvalid',
                f'MediaFile.Id={MediaFileId} has AudioChannels={ChannelsInt} (non-positive). See BUG-0074.',
                None,
            )
        return max(1, min(8, ChannelsInt))

    # directive: audio-dialog-boost-real | # see audio-normalization.C8
    def _PickDefaultLanguage(self, AudioStreams, StreamLanguageMap, LibraryDefault):
        Present = [StreamLanguageMap.get(S.get('index'), 'und') for S in AudioStreams]
        Result = self.DispositionResolver.PickDefaultLanguage(Present, LibraryDefault)
        if hasattr(Result, 'Plan'):
            Plan = Result.Plan
            return Plan.get('Language')
        return None
