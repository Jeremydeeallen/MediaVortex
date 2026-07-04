from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from Features.AudioNormalization.AudioFilterEmitter import AudioFilterEmitter
from Features.AudioNormalization.AudioPolicyResolver import AudioPolicyResolver
from Features.AudioNormalization.AudioStrategyResult import AudioPolicyUnresolvedError
from Features.AudioNormalization.Services.AudioStreamProbe import AudioStreamProbe


# directive: transcode-flow-canonical | # see transcode.ST5
@dataclass
class AudioEmission:
    InputArgs: List[str] = field(default_factory=list)
    StreamArgs: List[str] = field(default_factory=list)


# directive: transcode-flow-canonical | # see transcode.ST5
class AudioSlot:

    # directive: transcode-flow-canonical | # see transcode.ST5
    def __init__(self, Resolver=None, Emitter=None, StreamProbe=None):
        self.Resolver = Resolver or AudioPolicyResolver()
        self.Emitter = Emitter or AudioFilterEmitter()
        self.StreamProbe = StreamProbe or AudioStreamProbe()

    # directive: transcode-flow-canonical | # see transcode.ST5
    def Emit(self, Op: str, MediaFile, Context: Dict[str, Any]) -> AudioEmission:
        if Op == 'Reencode':
            return self._EmitReencode(MediaFile, Context)
        if Op == 'Copy':
            return AudioEmission(InputArgs=[], StreamArgs=['-map', '0:a?', '-c:a', 'copy'])
        raise ValueError(f"AudioSlot.Emit: unknown Op={Op!r}")

    # directive: transcode-flow-canonical | # see transcode.ST5
    def _EmitReencode(self, MediaFile, Context: Dict[str, Any]) -> AudioEmission:
        Policy = self.Resolver.GetEffectivePolicy(MediaFile)
        if not Policy:
            raise AudioPolicyUnresolvedError(
                'PolicyMissing',
                f'MediaFile.Id={getattr(MediaFile, "Id", None)} has no effective AudioPolicy; refusing legacy stream-copy fallback (starvation risk).',
                None,
            )
        SourceStreams = self.StreamProbe.Probe(Context.get('InputPath')) or None
        Blocks = self.Emitter.EmitTracks(
            MediaFile, Policy, AudioStreams=SourceStreams,
            DemucsPremixPath=Context.get('DemucsPremixPath'),
            VocalsRmsDbfs=Context.get('VocalsRmsDbfs'),
            PremixMeasuredI=Context.get('PremixMeasuredI'),
            PremixMeasuredLra=Context.get('PremixMeasuredLra'),
            PremixMeasuredTp=Context.get('PremixMeasuredTp'),
            PremixMeasuredThresh=Context.get('PremixMeasuredThresh'),
        )
        if not Blocks:
            raise AudioPolicyUnresolvedError(
                'EmitTracksReturnedEmpty',
                f'MediaFile.Id={getattr(MediaFile, "Id", None)} produced empty audio Blocks; refusing legacy ProfileAudioCeiling reencode fallback (starvation risk).',
                None,
            )
        Emission = AudioEmission()
        for Block in Blocks:
            if Block.InputArgs:
                for I in range(0, len(Block.InputArgs), 2):
                    Emission.InputArgs.append(Block.InputArgs[I])
                    Emission.InputArgs.append(f'"{Block.InputArgs[I + 1]}"')
        for Block in Blocks:
            Emission.StreamArgs.extend(Block.MapArgs)
            Emission.StreamArgs.extend(Block.CodecArgs)
            if Block.FilterArgs:
                Emission.StreamArgs.extend(Block.FilterArgs[:1])
                Emission.StreamArgs.append(f'"{Block.FilterArgs[1]}"')
            Emission.StreamArgs.extend(Block.MetadataArgs)
            Emission.StreamArgs.extend(Block.DispositionArgs)
        return Emission
