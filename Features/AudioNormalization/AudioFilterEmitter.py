from dataclasses import dataclass, field
from typing import List, Optional

from Features.AudioNormalization.AudioStrategyClassifier import (
    AudioStrategyClassifier,
    STRATEGY_LINEAR,
    STRATEGY_ADAPTIVE,
    STRATEGY_LIMITER,
    STRATEGY_SKIP,
    STRATEGY_REVIEW,
)
from Features.AudioNormalization.AudioDispositionResolver import AudioDispositionResolver
from Features.AudioNormalization.DialNormHandler import DialNormHandler
from Features.AudioNormalization.LanguageDetector import LanguageDetector, KEEP_ALL


MP4_COMPAT_AUDIO_CODECS = ('aac', 'ac3', 'eac3', 'mp3')


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C1
@dataclass
class TrackBlock:
    """One output audio track expressed as four argv slices the shape consumer concatenates."""
    Label: str
    Language: str
    Strategy: str
    MapArgs: List[str] = field(default_factory=list)
    CodecArgs: List[str] = field(default_factory=list)
    FilterArgs: List[str] = field(default_factory=list)
    MetadataArgs: List[str] = field(default_factory=list)
    DispositionArgs: List[str] = field(default_factory=list)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C8
def _GetField(Obj, Name):
    """Read Name off a dict/object/CaseInsensitiveDict and return the value or None."""
    if hasattr(Obj, Name):
        return getattr(Obj, Name)
    if hasattr(Obj, 'get'):
        Val = Obj.get(Name)
        if Val is not None:
            return Val
        return Obj.get(Name.lower())
    return None


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C22
def _IsMp4CompatCodec(Codec):
    """True when the source audio codec can be MP4-mux-stream-copied."""
    return (Codec or '').lower() in MP4_COMPAT_AUDIO_CODECS


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C22
def _ShouldStreamCopy(MediaFile, TrackConfig, Strategy):
    """True when policy says no audio modification AND source codec is MP4-compat AND AudioCorruptSuspect is not true."""
    if Strategy.Strategy not in (STRATEGY_SKIP,):
        return False
    if bool(_GetField(MediaFile, 'AudioCorruptSuspect')):
        return False
    SourceCodec = _GetField(MediaFile, 'AudioCodec')
    return _IsMp4CompatCodec(SourceCodec)


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C23
def _IsCommentaryStream(Stream):
    """True when ffprobe disposition.comment == 1 marks the stream as commentary."""
    Disposition = Stream.get('disposition') or {}
    return Disposition.get('comment') in (1, True, '1')


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C4
def _LanguageMatches(TrackConfig, StreamLanguage):
    """True when the TrackConfig.LanguageFilter accepts the detected stream language."""
    Filter = (TrackConfig.get('LanguageFilter') or 'keep-all').lower()
    if Filter in ('keep-all', '*', ''):
        return True
    if Filter == 'detected-only':
        return StreamLanguage not in (None, 'und', '')
    Codes = [C.strip().lower() for C in Filter.split(',') if C.strip()]
    return StreamLanguage and StreamLanguage.lower() in Codes


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C3
def _BuildLoudnormFilter(MediaFile, Strategy):
    """Compose the loudnorm filter argv value for a per-track strategy that needs re-encode."""
    SrcI = float(_GetField(MediaFile, 'SourceIntegratedLufs'))
    SrcLra = float(_GetField(MediaFile, 'SourceLoudnessRangeLU'))
    SrcTp = float(_GetField(MediaFile, 'SourceTruePeakDbtp'))
    SrcThresh = float(_GetField(MediaFile, 'SourceIntegratedThresholdLufs'))

    TargetI = float(Strategy.EffectiveTargetLufs)
    TargetTp = float(Strategy.EffectiveTruePeakDbtp)
    TargetLra = Strategy.EffectiveLra if Strategy.EffectiveLra is not None else max(SrcLra, 1.0)

    Measured = (
        f"measured_I={SrcI:.2f}"
        f":measured_LRA={SrcLra:.2f}"
        f":measured_TP={SrcTp:.2f}"
        f":measured_thresh={SrcThresh:.2f}"
    )
    Filter = (
        f"loudnorm=I={TargetI:.2f}"
        f":LRA={float(TargetLra):.2f}"
        f":TP={TargetTp:.2f}"
        f":{Measured}"
    )

    if Strategy.Strategy in (STRATEGY_LINEAR, STRATEGY_ADAPTIVE) and Strategy.EffectiveLra is None:
        Filter += ":linear=true"
    return Filter


# directive: worker-runtime-state | # see audio-normalization.C8
class AudioFilterEmitter:
    """The seam: every shape consumes EmitTracks(MediaFile, Policy) -> List[TrackBlock]."""

    # directive: audio-pipeline-fail-loud | # see audio-normalization.C8
    def __init__(self, Classifier=None, LanguageDetectorInstance=None, DialNormHandlerInstance=None, ProfileResolver=None, DispositionResolver=None):
        self.Classifier = Classifier or AudioStrategyClassifier()
        self.LanguageDetector = LanguageDetectorInstance or LanguageDetector()
        self.DialNormHandler = DialNormHandlerInstance or DialNormHandler()
        self.ProfileResolver = ProfileResolver
        self.DispositionResolver = DispositionResolver or AudioDispositionResolver()

    # directive: worker-runtime-state | # see audio-normalization.C8
    def EmitTracks(self, MediaFile, Policy, AudioStreams=None, LibraryDefault=None):
        """Return a list of TrackBlocks across Policy.EmitTracks x kept language streams."""
        if AudioStreams is None:
            AudioStreams = [{'index': 0, 'tags': {}, 'disposition': {}}]

        self._ProfileBitrateCeiling = self._ResolveProfileBitrateCeiling(MediaFile)

        KeepCommentary = bool(_GetField(Policy, 'KeepCommentaryTracks'))
        if not KeepCommentary:
            AudioStreams = [S for S in AudioStreams if not _IsCommentaryStream(S)]

        EnableSpeech = bool(_GetField(Policy, 'EnableSpeechLanguageDetection'))
        SpeechCache = _GetField(MediaFile, 'AudioStreamLanguageDetectionsJson')
        EffectiveDefault = LibraryDefault or _GetField(Policy, 'LanguageDefault')
        Detection = self.LanguageDetector.Detect(
            AudioStreams,
            LibraryDefault=EffectiveDefault,
            SpeechCache=SpeechCache,
            EnableSpeechLayer=EnableSpeech,
        )
        StreamLanguageMap = {Sl.StreamIndex: Sl.Language for Sl in Detection.StreamLanguages}

        DefaultLanguage = self._PickDefaultLanguage(AudioStreams, StreamLanguageMap, EffectiveDefault)

        EmitTrackConfigs = _GetField(Policy, 'EmitTracks') or []
        Blocks = []
        OutputIndex = 0

        for TrackConfig in EmitTrackConfigs:
            Strategy = self.Classifier.ClassifyTrack(MediaFile, TrackConfig, Policy)
            IsReview = Strategy.Strategy == STRATEGY_REVIEW

            for Stream in AudioStreams:
                StreamIdx = Stream.get('index')
                StreamLanguage = StreamLanguageMap.get(StreamIdx, 'und')
                if not _LanguageMatches(TrackConfig, StreamLanguage):
                    continue

                IsDefaultLanguage = (StreamLanguage == DefaultLanguage)
                if IsReview:
                    Block = self._BuildReviewFallbackBlock(
                        MediaFile, TrackConfig, Stream, StreamLanguage, OutputIndex, IsDefaultLanguage,
                    )
                else:
                    Block = self._BuildBlockForTrack(
                        MediaFile, TrackConfig, Strategy, Stream, StreamLanguage,
                        OutputIndex, len(EmitTrackConfigs),
                        IsDefaultLanguage=IsDefaultLanguage,
                    )
                if Block is not None:
                    Blocks.append(Block)
                    OutputIndex += 1

        return Blocks

    # directive: audio-pipeline-fail-loud | # see audio-normalization.C24
    def _BuildReviewFallbackBlock(self, MediaFile, TrackConfig, Stream, Language, OutputIndex, IsDefaultLanguage):
        StreamIdx = Stream.get('index', 0)
        Label = TrackConfig.get('Label') or 'Track'
        Disp = self.DispositionResolver.ResolveForTrack(
            TrackIndex=OutputIndex,
            ProfileCeilingKbps=getattr(self, '_ProfileBitrateCeiling', None),
            SourceBitrateKbps=_GetField(MediaFile, 'AudioBitrateKbps'),
            ConfigBitrateKbps=TrackConfig.get('Bitrate'),
            SourceCodec=_GetField(MediaFile, 'AudioCodec'),
            ForceReencode=False,
            AudioCorruptSuspect=bool(_GetField(MediaFile, 'AudioCorruptSuspect')),
            IsDefault=IsDefaultLanguage,
        )
        Block = TrackBlock(
            Label=Label,
            Language=Language,
            Strategy='review_resolved',
            MapArgs=['-map', f'0:a:{StreamIdx}'],
        )
        if Disp.Mode == 'reencode':
            Block.CodecArgs = [f'-c:a:{OutputIndex}', Disp.Codec]
            if Disp.BitrateKbps:
                Block.CodecArgs += [f'-b:a:{OutputIndex}', f'{int(Disp.BitrateKbps)}k']
        else:
            Block.CodecArgs = [f'-c:a:{OutputIndex}', 'copy']
        Block.MetadataArgs = self._BuildMetadataArgs(Language, Label, OutputIndex)
        Block.DispositionArgs = self._BuildDispositionArgs(TrackConfig, OutputIndex, IsDefaultLanguage=IsDefaultLanguage)
        return Block

    # directive: audio-vertical-live-evidence | # see audio-normalization.L1
    def _PickDefaultLanguage(self, AudioStreams, StreamLanguageMap, LibraryDefault):
        """Pick exactly one default language across the source: prefer per-stream default disposition, fall back to library default, fall back to first language present."""
        for S in AudioStreams:
            Disp = S.get('disposition') or {}
            if Disp.get('default') in (1, True, '1'):
                Lang = StreamLanguageMap.get(S.get('index'), 'und')
                if Lang and Lang != 'und':
                    return Lang
        if LibraryDefault:
            Present = {StreamLanguageMap.get(S.get('index'), 'und') for S in AudioStreams}
            if LibraryDefault in Present:
                return LibraryDefault
        for S in AudioStreams:
            Lang = StreamLanguageMap.get(S.get('index'), 'und')
            if Lang and Lang != 'und':
                return Lang
        return None

    # directive: audio-vertical-live-evidence | # see audio-normalization.L1
    def _BuildBlockForTrack(self, MediaFile, TrackConfig, Strategy, Stream, Language, OutputIndex, NumEmitTracks, IsDefaultLanguage=True):
        """Thin orchestrator: delegates each per-concern slot of the TrackBlock argv to its own helper (SRP)."""
        StreamIdx = Stream.get('index', 0)
        Label = TrackConfig.get('Label') or 'Track'
        Mode = self._DecideStreamCopyOrReencode(MediaFile, TrackConfig, Strategy)
        Codec = (TrackConfig.get('Codec') or 'eac3').lower()
        IsAc3Family = Codec in ('eac3', 'ac3')

        Block = TrackBlock(
            Label=Label,
            Language=Language,
            Strategy=Mode if Mode != 'reencode' else Strategy.Strategy,
            MapArgs=['-map', f'0:a:{StreamIdx}'],
        )

        Block.CodecArgs = self._BuildCodecArgs(TrackConfig, Mode, Codec, OutputIndex)
        if Mode == 'reencode':
            Block.FilterArgs = self._BuildFilterArgs(MediaFile, Strategy, OutputIndex)
        Block.MetadataArgs = self._BuildMetadataArgs(Language, Label, OutputIndex)
        Block.CodecArgs += self._BuildDialNormArgs(Strategy, Stream, Mode, IsAc3Family, Label, OutputIndex)
        Block.DispositionArgs = self._BuildDispositionArgs(TrackConfig, OutputIndex, IsDefaultLanguage=IsDefaultLanguage)
        return Block

    # directive: worker-runtime-state | # see audio-normalization.C8
    def _DecideStreamCopyOrReencode(self, MediaFile, TrackConfig, Strategy):
        """Return 'stream_copy' / 'stream_copy_fallback' / 'reencode' for the per-track output."""
        Ceiling = getattr(self, '_ProfileBitrateCeiling', None)
        SrcKbps = _GetField(MediaFile, 'AudioBitrateKbps')
        if Ceiling and SrcKbps and int(SrcKbps) > int(Ceiling):
            return 'reencode'
        if _ShouldStreamCopy(MediaFile, TrackConfig, Strategy):
            return 'stream_copy'
        if Strategy.Strategy == STRATEGY_SKIP:
            return 'stream_copy_fallback'
        return 'reencode'

    # directive: worker-runtime-state | # see audio-normalization.C8
    def _ResolveProfileBitrateCeiling(self, MediaFile):
        """Return EffectiveProfile.TargetAudioKbps or None when no resolver / no profile / no ceiling."""
        if self.ProfileResolver is None:
            return None
        try:
            Profile = self.ProfileResolver.Resolve(MediaFile)
            if Profile is None:
                return None
            Ceiling = getattr(Profile, 'TargetAudioKbps', None)
            return int(Ceiling) if Ceiling else None
        except Exception:
            return None

    # directive: worker-runtime-state | # see audio-normalization.C8
    def _BuildCodecArgs(self, TrackConfig, Mode, Codec, OutputIndex):
        """Codec + bitrate + sample rate + channel-count argv for the output index."""
        if Mode in ('stream_copy', 'stream_copy_fallback'):
            return [f'-c:a:{OutputIndex}', 'copy']
        Args = [f'-c:a:{OutputIndex}', Codec]
        Bitrate = TrackConfig.get('Bitrate')
        SampleRate = TrackConfig.get('SampleRateHz')
        Channels = TrackConfig.get('Channels')
        Ceiling = getattr(self, '_ProfileBitrateCeiling', None)
        if Bitrate and Ceiling and int(Bitrate) > Ceiling:
            Bitrate = Ceiling
        if Bitrate:
            Args += [f'-b:a:{OutputIndex}', f'{int(Bitrate)}k']
        if SampleRate:
            Args += [f'-ar:{OutputIndex}', str(int(SampleRate))]
        if Channels not in (None, 'source'):
            Args += [f'-ac:{OutputIndex}', str(int(Channels))]
        return Args

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
    def _BuildFilterArgs(self, MediaFile, Strategy, OutputIndex):
        """loudnorm filter argv for the per-output-track re-encode."""
        Filter = _BuildLoudnormFilter(MediaFile, Strategy)
        return [f'-filter:a:{OutputIndex}', Filter]

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.L2
    def _BuildMetadataArgs(self, Language, Label, OutputIndex):
        """Language + title + MP4-persistent handler_name (L2: title is dropped by MP4 muxer; handler_name survives)."""
        return [
            f'-metadata:s:a:{OutputIndex}', f'"language={Language}"',
            f'-metadata:s:a:{OutputIndex}', f'"title={Label}"',
            f'-metadata:s:a:{OutputIndex}', f'"handler_name={Label} ({Language})"',
        ]

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.S1
    def _BuildDialNormArgs(self, Strategy, Stream, Mode, IsAc3Family, Label, OutputIndex):
        """Signed-dB dialnorm codec option for ac3/eac3 re-encodes; empty list otherwise."""
        SourceDialNorm = self.DialNormHandler.GetSourceDialNorm(Stream)
        IsOriginalCopy = Mode == 'stream_copy' and (Label or '').lower().startswith('original')
        DialNorm = self.DialNormHandler.ResolveForTrack(Strategy, SourceDialNorm, IsOriginalCopy)
        if DialNorm is None or not IsAc3Family or Mode != 'reencode':
            return []
        return [f'-dialnorm:{OutputIndex}', str(-int(DialNorm))]

    # directive: audio-vertical-live-evidence | # see audio-normalization.L1
    def _BuildDispositionArgs(self, TrackConfig, OutputIndex, IsDefaultLanguage=True):
        """Default-flag iff TrackConfig.IsDefaultTrack AND this output corresponds to the source's default-language stream."""
        if bool(TrackConfig.get('IsDefaultTrack')) and IsDefaultLanguage:
            return [f'-disposition:a:{OutputIndex}', 'default']
        return [f'-disposition:a:{OutputIndex}', '0']
