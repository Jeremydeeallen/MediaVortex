from typing import Optional
from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Models.MediaFileModel import MediaFileModel
from Features.Compliance.Models.EffectiveProfile import EffectiveProfile
from Features.TranscodeQueue.CrfBitrateEstimateRepository import CrfBitrateEstimateRepository


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C12
class EffectiveProfileResolver:
    """Resolves MediaFile -> EffectiveProfile via Profile cascade + bitrate-strategy dispatch (fixed / VBR / CRF). SRP: profile resolution only."""

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C11
    def __init__(self, DatabaseServiceInstance: Optional[DatabaseService] = None, CrfBitrateRepo: Optional[CrfBitrateEstimateRepository] = None):
        self.DB = DatabaseServiceInstance or DatabaseService()
        self.CrfBitrateRepo = CrfBitrateRepo or CrfBitrateEstimateRepository()

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C12
    def Resolve(self, Mf: MediaFileModel) -> Optional[EffectiveProfile]:
        """Cascade resolves the profile name (today: MediaFile.AssignedProfile denormalized cache); thresholds lookup picks the row for the source resolution; bitrate strategy fills TargetVideoKbps from fixed / VBR-percent / CRF-estimate; returns None when no profile assigned."""
        if not Mf.AssignedProfile or not Mf.ResolutionCategory:
            return None
        Row = self._LookupThresholdsRow(Mf.AssignedProfile, Mf.ResolutionCategory)
        if not Row:
            return EffectiveProfile(ProfileName=Mf.AssignedProfile, TargetVideoKbps=None, TargetAudioKbps=None, TargetResolutionCategory=None)
        TargetResolution = Row['TargetResolution']
        TargetAudioKbps = Row['AudioBitrateKbps'] if Row['AudioBitrateKbps'] is not None else None
        TargetVideoKbps = self._ResolveTargetVideoKbps(Row, Mf, TargetResolution)
        return EffectiveProfile(ProfileName=Mf.AssignedProfile, TargetVideoKbps=TargetVideoKbps, TargetAudioKbps=TargetAudioKbps, TargetResolutionCategory=TargetResolution)

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C12
    def _ResolveTargetVideoKbps(self, Row: dict, Mf: MediaFileModel, TargetResolution: Optional[str]) -> Optional[int]:
        """Strategy: fixed (>0) wins; else VBR (SourceBitratePercent>0 + MediaFile.VideoBitrateKbps) computes target; else CRF (Quality + Codec) looks up CrfBitrateEstimates; else None."""
        Vk = Row['VideoBitrateKbps']
        if Vk is not None and Vk > 0:
            return int(Vk)
        Percent = Row.get('SourceBitratePercent')
        if Percent and Percent > 0 and Mf.VideoBitrateKbps:
            return int(round(int(Mf.VideoBitrateKbps) * float(Percent) / 100.0))
        Crf = Row.get('Quality')
        Codec = Row.get('Codec')
        if Crf is not None and Codec and TargetResolution:
            Est = self.CrfBitrateRepo.GetEstimatedKbps(Codec, TargetResolution, int(Crf))
            if Est:
                return int(Est)
        return None

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C12
    def _LookupThresholdsRow(self, ProfileName: str, SourceResolution: str) -> Optional[dict]:
        """Single targeted JOIN -- pulls bitrates + Quality + Codec + SourceBitratePercent + TranscodeDownTo so the strategy dispatch has every input in one row."""
        try:
            Rows = self.DB.ExecuteQuery(
                "SELECT pt.VideoBitrateKbps, pt.AudioBitrateKbps, pt.Quality, pt.SourceBitratePercent, pt.TranscodeDownTo, p.Codec, p.RateControlMode "
                "FROM ProfileThresholds pt "
                "JOIN Profiles p ON pt.ProfileId = p.Id "
                "WHERE p.ProfileName = %s AND pt.Resolution = %s "
                "LIMIT 1",
                (ProfileName, SourceResolution),
            )
            if not Rows:
                return None
            R = Rows[0]
            Downto = R.get('TranscodeDownTo')
            Target = Downto if Downto and Downto != 'No downscaling' else SourceResolution
            return {
                'VideoBitrateKbps': R['VideoBitrateKbps'],
                'AudioBitrateKbps': R['AudioBitrateKbps'],
                'Quality': R.get('Quality'),
                'SourceBitratePercent': R.get('SourceBitratePercent'),
                'TargetResolution': Target,
                'Codec': R.get('Codec'),
                'RateControlMode': R.get('RateControlMode'),
            }
        except Exception as Ex:
            LoggingService.LogException(f"Threshold lookup failed for ({ProfileName}, {SourceResolution})", Ex, "EffectiveProfileResolver", "_LookupThresholdsRow")
            return None
