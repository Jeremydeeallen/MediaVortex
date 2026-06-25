from typing import List, Optional

from Features.AudioNormalization.AudioStrategyResult import (
    Accept, Reject, AudioPolicyUnresolvedError,
)
from Features.AudioNormalization.Policies.IAudioBitratePolicy import (
    IAudioBitratePolicy, ProfileCeilingBitratePolicy,
)
from Features.AudioNormalization.Policies.IAudioCodecPolicy import (
    IAudioCodecPolicy, EAC3OrPassthroughCodecPolicy,
)
from Features.AudioNormalization.Policies.IAudioDefaultLanguagePolicy import (
    IAudioDefaultLanguagePolicy, RankPreferredDefaultPolicy,
)


# directive: audio-pipeline-fail-loud
class AudioTrackDisposition:

    # directive: audio-pipeline-fail-loud
    def __init__(self, TrackIndex: int, BitrateKbps: Optional[int], Codec: str, Mode: str, IsDefault: bool, Verdicts: List[dict]):
        self.TrackIndex = TrackIndex
        self.BitrateKbps = BitrateKbps
        self.Codec = Codec
        self.Mode = Mode
        self.IsDefault = IsDefault
        self.Verdicts = Verdicts


# directive: audio-pipeline-fail-loud
class AudioDispositionResolver:

    # directive: audio-pipeline-fail-loud
    def __init__(
        self,
        BitratePolicy: Optional[IAudioBitratePolicy] = None,
        CodecPolicy: Optional[IAudioCodecPolicy] = None,
        DefaultLanguagePolicy: Optional[IAudioDefaultLanguagePolicy] = None,
    ):
        self.BitratePolicy = BitratePolicy or ProfileCeilingBitratePolicy()
        self.CodecPolicy = CodecPolicy or EAC3OrPassthroughCodecPolicy()
        self.DefaultLanguagePolicy = DefaultLanguagePolicy or RankPreferredDefaultPolicy()

    # directive: audio-pipeline-fail-loud
    def PickDefaultLanguage(self, PresentLanguages: List[str], LibraryDefault: Optional[str]):
        Result = self.DefaultLanguagePolicy.Decide(PresentLanguages, LibraryDefault)
        return Result

    # directive: audio-pipeline-fail-loud
    def ResolveForTrack(
        self,
        TrackIndex: int,
        ProfileCeilingKbps: Optional[int],
        SourceBitrateKbps: Optional[int],
        ConfigBitrateKbps: Optional[int],
        SourceCodec: Optional[str],
        ForceReencode: bool,
        AudioCorruptSuspect: bool,
        IsDefault: bool,
    ) -> AudioTrackDisposition:
        Verdicts = []

        CodecResult = self.CodecPolicy.Decide(SourceCodec, ForceReencode, AudioCorruptSuspect)
        Verdicts.append(self._VerdictRow(TrackIndex, CodecResult))
        if isinstance(CodecResult, Reject):
            raise AudioPolicyUnresolvedError(CodecResult.PolicyName, CodecResult.Reason, TrackIndex)

        Mode = CodecResult.Plan['Mode']
        Codec = CodecResult.Plan['Codec']

        BitrateForOutput: Optional[int] = None
        if Mode == 'reencode':
            BitrateResult = self.BitratePolicy.Decide(ProfileCeilingKbps, SourceBitrateKbps, ConfigBitrateKbps)
            Verdicts.append(self._VerdictRow(TrackIndex, BitrateResult))
            if isinstance(BitrateResult, Reject):
                raise AudioPolicyUnresolvedError(BitrateResult.PolicyName, BitrateResult.Reason, TrackIndex)
            BitrateForOutput = BitrateResult.Plan

        return AudioTrackDisposition(
            TrackIndex=TrackIndex,
            BitrateKbps=BitrateForOutput,
            Codec=Codec,
            Mode=Mode,
            IsDefault=IsDefault,
            Verdicts=Verdicts,
        )

    # directive: audio-pipeline-fail-loud
    def _VerdictRow(self, TrackIndex: int, Result) -> dict:
        if isinstance(Result, Accept):
            return {
                'TrackIndex': TrackIndex,
                'PolicyName': Result.PolicyName,
                'PolicyReason': 'accept',
                'PlanText': str(Result.Plan),
            }
        return {
            'TrackIndex': TrackIndex,
            'PolicyName': Result.PolicyName,
            'PolicyReason': Result.Reason,
            'PlanText': None,
        }
