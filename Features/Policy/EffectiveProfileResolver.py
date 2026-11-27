from typing import Optional
from Core.Database.DatabaseService import DatabaseService
from Core.Resolution.ResolutionTierRegistry import ResolutionTierRegistry
from Models.MediaFileModel import MediaFileModel
from Features.Policy.ContentClassResolver import ContentClassResolver
from Features.Policy.EffectiveProfile import EffectiveProfile
from Features.Policy.TierLadderRepository import TierLadderRepository


# directive: compliance-solid-refactor, profile-row-lookup | # see compliance-solid-refactor.C12, profile-tier-ladder.S5
class EffectiveProfileResolver:
    """Resolves MediaFile -> EffectiveProfile: profile-name cascade, then the encode row for (profile, content class, source resolution) plus the profile's compliance-bar columns. Returns TargetResolutionCategory as a typed ResolutionTier (resolution-types.C6)."""

    # directive: compliance-solid-refactor, profile-row-lookup | # see compliance-solid-refactor.C11, profile-tier-ladder.S5
    def __init__(self, DatabaseServiceInstance: Optional[DatabaseService] = None, TierRegistry: Optional[ResolutionTierRegistry] = None,
                 Tiers: Optional[TierLadderRepository] = None, Classes: Optional[ContentClassResolver] = None):
        self.DB = DatabaseServiceInstance or DatabaseService()
        # directive: resolution-types | # see resolution-types.C6
        self.TierRegistry = TierRegistry or ResolutionTierRegistry()
        self.Tiers = Tiers or TierLadderRepository(self.DB)
        self.Classes = Classes or ContentClassResolver(self.DB)

    # directive: transcode-worker-unification | # see profiles.C23
    def ResolveProfileName(self, Mf: MediaFileModel) -> Optional[str]:
        # Name-only cascade entry -- delegates to _ResolveAssignedProfileName; no EffectiveProfile struct needed.
        return self._ResolveAssignedProfileName(Mf)

    # directive: compliance-symmetry, profile-row-lookup | # see profile-tier-ladder.C9 -- targets come from the encode row; bar fields stay profile-level
    def Resolve(self, Mf: MediaFileModel) -> Optional[EffectiveProfile]:
        ProfileName = self._ResolveAssignedProfileName(Mf)
        if not ProfileName or not Mf.ResolutionCategory:
            return None
        ContentClass = self.Classes.Resolve(getattr(Mf, 'StorageRootId', None), getattr(Mf, 'Id', None))
        if ContentClass is None:
            return None
        Encode = self.Tiers.GetEncodeRow(ProfileName, ContentClass, Mf.ResolutionCategory)
        if Encode is None:
            return None
        Bar = self._LookupComplianceBarRow(ProfileName)
        if Bar is None:
            return None
        return EffectiveProfile(
            ProfileName=ProfileName,
            TargetVideoKbps=Encode.TargetKbps,
            TargetAudioKbps=Encode.AudioBitrateKbps,
            TargetResolutionCategory=self.TierRegistry.FromCategory(Encode.Resolution),
            StreamCodecName=Bar.get('streamcodecname'),
            AllowUpscale=bool(Bar.get('allowupscale')),
            AudioCodec=Bar.get('audiocodec'),
            Container=Bar.get('container'),
        )

    # directive: compliance-symmetry | # see profiles.C23
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

    # directive: compliance-symmetry | # see work-bucket.G6
    def _IsFinalizedActive(self, ProfileName: str) -> bool:
        from Features.Policy.ProfileRepository import ProfileRepository
        return ProfileRepository().IsFinalizedActive(ProfileName)

    # directive: compliance-symmetry | # see profiles.C23
    def _LookupComplianceBarRow(self, ProfileName: str) -> Optional[dict]:
        Rows = self.DB.ExecuteQuery(
            "SELECT StreamCodecName, AllowUpscale, AudioCodec, Container "
            "FROM Profiles WHERE ProfileName = %s LIMIT 1",
            (ProfileName,),
        )
        return Rows[0] if Rows else None
