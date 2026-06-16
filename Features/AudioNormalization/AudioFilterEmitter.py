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


# directive: perfect-audio-vertical | # see perfect-audio-vertical.C1
class AudioFilterEmitter:
    """The seam: every shape consumes EmitTracks(MediaFile, Policy) -> List[TrackBlock]."""

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C1
    def __init__(self, Classifier=None, LanguageDetectorInstance=None, DialNormHandlerInstance=None):
        """Constructor injection per SOLID DIP; default-constructs each collaborator when omitted."""
        self.Classifier = Classifier or AudioStrategyClassifier()
        self.LanguageDetector = LanguageDetectorInstance or LanguageDetector()
        self.DialNormHandler = DialNormHandlerInstance or DialNormHandler()

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C1
    def EmitTracks(self, MediaFile, Policy, AudioStreams=None, LibraryDefault=None):
        """Return a list of TrackBlocks across Policy.EmitTracks x kept language streams."""
        if AudioStreams is None:
            AudioStreams = [{'index': 0, 'tags': {}, 'disposition': {}}]

        KeepCommentary = bool(_GetField(Policy, 'KeepCommentaryTracks'))
        if not KeepCommentary:
            AudioStreams = [S for S in AudioStreams if not _IsCommentaryStream(S)]

        EnableSpeech = bool(_GetField(Policy, 'EnableSpeechLanguageDetection'))
        SpeechCache = _GetField(MediaFile, 'AudioStreamLanguageDetectionsJson')
        Detection = self.LanguageDetector.Detect(
            AudioStreams,
            LibraryDefault=LibraryDefault,
            SpeechCache=SpeechCache,
            EnableSpeechLayer=EnableSpeech,
        )
        StreamLanguageMap = {Sl.StreamIndex: Sl.Language for Sl in Detection.StreamLanguages}

        EmitTrackConfigs = _GetField(Policy, 'EmitTracks') or []
        Blocks = []
        OutputIndex = 0

        for TrackConfig in EmitTrackConfigs:
            Strategy = self.Classifier.ClassifyTrack(MediaFile, TrackConfig, Policy)
            if Strategy.Strategy == STRATEGY_REVIEW:
                continue

            for Stream in AudioStreams:
                StreamIdx = Stream.get('index')
                StreamLanguage = StreamLanguageMap.get(StreamIdx, 'und')
                if not _LanguageMatches(TrackConfig, StreamLanguage):
                    continue

                Block = self._BuildBlockForTrack(
                    MediaFile, TrackConfig, Strategy, Stream, StreamLanguage,
                    OutputIndex, len(EmitTrackConfigs),
                )
                if Block is not None:
                    Blocks.append(Block)
                    OutputIndex += 1

        return Blocks

    # directive: perfect-audio-vertical | # see perfect-audio-vertical.C2
    def _BuildBlockForTrack(self, MediaFile, TrackConfig, Strategy, Stream, Language, OutputIndex, NumEmitTracks):
        """Build the four-slot TrackBlock argv for a single Track x Stream pair."""
        StreamIdx = Stream.get('index', 0)
        Label = TrackConfig.get('Label') or 'Track'
        StreamCopy = _ShouldStreamCopy(MediaFile, TrackConfig, Strategy)

        Block = TrackBlock(
            Label=Label,
            Language=Language,
            Strategy='stream_copy' if StreamCopy else Strategy.Strategy,
            MapArgs=['-map', f'0:a:{StreamIdx}'],
        )

        if StreamCopy:
            Block.CodecArgs = [f'-c:a:{OutputIndex}', 'copy']
        elif Strategy.Strategy == STRATEGY_SKIP:
            Block.CodecArgs = [f'-c:a:{OutputIndex}', 'copy']
            Block.Strategy = 'stream_copy_fallback'
        else:
            Codec = (TrackConfig.get('Codec') or 'eac3').lower()
            Bitrate = TrackConfig.get('Bitrate')
            SampleRate = TrackConfig.get('SampleRateHz')
            Channels = TrackConfig.get('Channels')
            Block.CodecArgs = [f'-c:a:{OutputIndex}', Codec]
            if Bitrate:
                Block.CodecArgs += [f'-b:a:{OutputIndex}', f'{int(Bitrate)}k']
            if SampleRate:
                Block.CodecArgs += [f'-ar:{OutputIndex}', str(int(SampleRate))]
            if Channels not in (None, 'source'):
                Block.CodecArgs += [f'-ac:{OutputIndex}', str(int(Channels))]
            Filter = _BuildLoudnormFilter(MediaFile, Strategy)
            Block.FilterArgs = [f'-filter:a:{OutputIndex}', Filter]

        Block.MetadataArgs = [
            f'-metadata:s:a:{OutputIndex}', f'language={Language}',
            f'-metadata:s:a:{OutputIndex}', f'title={Label}',
        ]

        SourceDialNorm = self.DialNormHandler.GetSourceDialNorm(Stream)
        IsOriginalCopy = StreamCopy and Label.lower().startswith('original')
        DialNorm = self.DialNormHandler.ResolveForTrack(Strategy, SourceDialNorm, IsOriginalCopy)
        if DialNorm is not None:
            Block.MetadataArgs += [
                f'-metadata:s:a:{OutputIndex}', f'dialnorm={DialNorm}',
            ]

        if bool(TrackConfig.get('IsDefaultTrack')):
            Block.DispositionArgs = [f'-disposition:a:{OutputIndex}', 'default']
        else:
            Block.DispositionArgs = [f'-disposition:a:{OutputIndex}', '0']

        return Block
