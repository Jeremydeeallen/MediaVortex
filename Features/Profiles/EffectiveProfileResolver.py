from typing import Optional
from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Core.Resolution.ResolutionTier import ResolutionTier
from Core.Resolution.ResolutionTierRegistry import ResolutionTierRegistry
from Models.MediaFileModel import MediaFileModel
from Features.Profiles.EffectiveProfile import EffectiveProfile
from Features.TranscodeQueue.CrfBitrateEstimateRepository import CrfBitrateEstimateRepository


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C12
class EffectiveProfileResolver:
    """Resolves MediaFile -> EffectiveProfile via Profile cascade + bitrate-strategy dispatch (fixed / VBR / CRF). SRP: profile resolution only. Returns TargetResolutionCategory as a typed ResolutionTier (resolution-types.C6)."""

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C11
    def __init__(self, DatabaseServiceInstance: Optional[DatabaseService] = None, CrfBitrateRepo: Optional[CrfBitrateEstimateRepository] = None, TierRegistry: Optional[ResolutionTierRegistry] = None):
        self.DB = DatabaseServiceInstance or DatabaseService()
        self.CrfBitrateRepo = CrfBitrateRepo or CrfBitrateEstimateRepository()
        # directive: resolution-types | # see resolution-types.C6
        self.TierRegistry = TierRegistry or ResolutionTierRegistry()

    # directive: compliance-symmetry
    def Resolve(self, Mf: MediaFileModel) -> Optional[EffectiveProfile]:
        ProfileName = self._ResolveAssignedProfileName(Mf)
        if not ProfileName or not Mf.ResolutionCategory:
            return None
        Bar = self._LookupComplianceBarRow(ProfileName)
        if Bar is None:
            return None
        Row = self._LookupThresholdsRow(ProfileName, Mf.ResolutionCategory)
        if Row:
            TargetResolutionStr = Row['TargetResolution']
            TargetAudioKbps = Row['AudioBitrateKbps'] if Row['AudioBitrateKbps'] else None
            TargetVideoKbps = self._ResolveTargetVideoKbps(Row, Mf, TargetResolutionStr)
        else:
            TargetResolutionStr = Bar.get('targetresolutioncategory')
            TargetVideoKbps = Bar.get('targetvideokbps')
            TargetAudioKbps = Bar.get('targetaudiokbps')
        TargetTier = self.TierRegistry.FromCategory(Bar.get('targetresolutioncategory') or TargetResolutionStr)
        return EffectiveProfile(
            ProfileName=ProfileName,
            TargetVideoKbps=TargetVideoKbps if TargetVideoKbps else Bar.get('targetvideokbps'),
            TargetAudioKbps=TargetAudioKbps if TargetAudioKbps else Bar.get('targetaudiokbps'),
            TargetResolutionCategory=TargetTier,
            StreamCodecName=Bar.get('streamcodecname'),
            AllowUpscale=bool(Bar.get('allowupscale')),
            AudioCodec=Bar.get('audiocodec'),
            Container=Bar.get('container'),
        )

    # directive: compliance-symmetry
    def _ResolveAssignedProfileName(self, Mf: MediaFileModel) -> Optional[str]:
        Assigned = (Mf.AssignedProfile or '').strip() or None
        if Assigned and self._IsFinalizedActive(Assigned):
            return Assigned
        DefaultRows = self.DB.ExecuteQuery(
            "SELECT SettingValue FROM SystemSettings WHERE SettingKey = 'DefaultProfileName' LIMIT 1"
        )
        if DefaultRows and DefaultRows[0].get('settingvalue') and self._IsFinalizedActive(DefaultRows[0]['settingvalue']):
            return DefaultRows[0]['settingvalue']
        FallbackRows = self.DB.ExecuteQuery(
            "SELECT ProfileName FROM Profiles WHERE Draft = FALSE AND Active = TRUE AND ProfileName = '_PreMigrationDefault' LIMIT 1"
        )
        if FallbackRows:
            return FallbackRows[0]['profilename']
        return None

    # directive: compliance-symmetry
    def _IsFinalizedActive(self, ProfileName: str) -> bool:
        Rows = self.DB.ExecuteQuery(
            "SELECT Draft, Active FROM Profiles WHERE ProfileName = %s LIMIT 1",
            (ProfileName,),
        )
        if not Rows:
            return False
        return bool(Rows[0].get('active')) and not bool(Rows[0].get('draft'))

    # directive: compliance-symmetry
    def _LookupComplianceBarRow(self, ProfileName: str) -> Optional[dict]:
        Rows = self.DB.ExecuteQuery(
            "SELECT StreamCodecName, TargetResolutionCategory, TargetVideoKbps, AllowUpscale, "
            "AudioCodec, TargetAudioKbps, Container "
            "FROM Profiles WHERE ProfileName = %s LIMIT 1",
            (ProfileName,),
        )
        return Rows[0] if Rows else None

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C12
    def _ResolveTargetVideoKbps(self, Row: dict, Mf: MediaFileModel, TargetResolution: Optional[str]) -> Optional[int]:
        """Strategy: fixed (>0) wins; else VBR (SourceBitratePercent>0 + MediaFile.VideoBitrateKbps) computes target; else CRF (Quality + Codec) looks up CrfBitrateEstimates; else None."""
        Vk = Row['VideoBitrateKbps']
        if Vk is not None and Vk > 0:
            return int(Vk)
        Percent = Row.get('SourceBitratePercent')
        if Percent and Percent > 0 and Mf.VideoBitrateKbps:
            # directive: mv-trust-savings-and-clamp -- AC2 VBR clamp.
            Computed = int(round(int(Mf.VideoBitrateKbps) * float(Percent) / 100.0))
            Floor = Row.get('MinBitrateKbps') or 0
            Ceil = Row.get('MaxBitrateKbps') or 10**9
            return max(int(Floor), min(int(Ceil), Computed))
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
                "SELECT pt.VideoBitrateKbps, pt.AudioBitrateKbps, pt.Quality, pt.SourceBitratePercent, pt.MinBitrateKbps, pt.MaxBitrateKbps, pt.TranscodeDownTo, p.Codec, p.RateControlMode "
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
                'MinBitrateKbps': R.get('MinBitrateKbps'),
                'MaxBitrateKbps': R.get('MaxBitrateKbps'),
                'TargetResolution': Target,
                'Codec': R.get('Codec'),
                'RateControlMode': R.get('RateControlMode'),
            }
        except Exception as Ex:
            LoggingService.LogException(f"Threshold lookup failed for ({ProfileName}, {SourceResolution})", Ex, "EffectiveProfileResolver", "_LookupThresholdsRow")
            return None
