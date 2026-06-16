from typing import Optional
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService
from Features.Compliance.Models.ComplianceGatesModel import ComplianceGatesModel


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C6
class ComplianceGatesRepository(BaseRepository):
    """Single-row scalar config for the 8 hard-block gates; always reads/writes Id=1; no caching (db-is-authority)."""

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C6
    def Get(self) -> ComplianceGatesModel:
        """Read the Id=1 row fresh per call; fall back to dataclass defaults if missing."""
        try:
            Rows = self.ExecuteQuery("SELECT Id, RequireExplicitEnglishAudio, BlockOnAudioCorruptSuspect, RequireAudioStream, RequireLoudnessMeasurements, RequireProbeMetadata, RequireEffectiveProfile, RequireResolutionCategory, RequireProfileThresholds, BlockOnAudioPolicyDeferred, LastUpdated FROM ComplianceGates WHERE Id = 1")
            if not Rows:
                LoggingService.LogWarning("ComplianceGates row Id=1 missing -- returning defaults; run AddComplianceRuleTables.py", "ComplianceGatesRepository", "Get")
                return ComplianceGatesModel()
            R = Rows[0]
            return ComplianceGatesModel(
                Id=R['Id'],
                RequireExplicitEnglishAudio=R['RequireExplicitEnglishAudio'],
                BlockOnAudioCorruptSuspect=R['BlockOnAudioCorruptSuspect'],
                RequireAudioStream=R['RequireAudioStream'],
                RequireLoudnessMeasurements=R['RequireLoudnessMeasurements'],
                RequireProbeMetadata=R['RequireProbeMetadata'],
                RequireEffectiveProfile=R['RequireEffectiveProfile'],
                RequireResolutionCategory=R['RequireResolutionCategory'],
                RequireProfileThresholds=R['RequireProfileThresholds'],
                BlockOnAudioPolicyDeferred=R.get('BlockOnAudioPolicyDeferred', True),
                LastUpdated=R.get('LastUpdated'),
            )
        except Exception as Ex:
            LoggingService.LogException("Get failed", Ex, "ComplianceGatesRepository", "Get")
            return ComplianceGatesModel()

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C6
    def Update(self, RequireExplicitEnglishAudio: Optional[bool] = None,
               BlockOnAudioCorruptSuspect: Optional[bool] = None,
               RequireAudioStream: Optional[bool] = None,
               RequireLoudnessMeasurements: Optional[bool] = None,
               RequireProbeMetadata: Optional[bool] = None,
               RequireEffectiveProfile: Optional[bool] = None,
               RequireResolutionCategory: Optional[bool] = None,
               RequireProfileThresholds: Optional[bool] = None) -> bool:
        """Update non-None gate flags on the Id=1 row; stamps LastUpdated=NOW()."""
        try:
            Sets = []
            Values = []
            for Name, Val in (
                ("RequireExplicitEnglishAudio", RequireExplicitEnglishAudio),
                ("BlockOnAudioCorruptSuspect", BlockOnAudioCorruptSuspect),
                ("RequireAudioStream", RequireAudioStream),
                ("RequireLoudnessMeasurements", RequireLoudnessMeasurements),
                ("RequireProbeMetadata", RequireProbeMetadata),
                ("RequireEffectiveProfile", RequireEffectiveProfile),
                ("RequireResolutionCategory", RequireResolutionCategory),
                ("RequireProfileThresholds", RequireProfileThresholds),
            ):
                if Val is not None:
                    Sets.append(Name + " = %s"); Values.append(Val)
            if not Sets:
                return True
            Sets.append("LastUpdated = NOW()")
            Query = "UPDATE ComplianceGates SET " + ", ".join(Sets) + " WHERE Id = 1"
            self.ExecuteNonQuery(Query, tuple(Values))
            return True
        except Exception as Ex:
            LoggingService.LogException("Update failed", Ex, "ComplianceGatesRepository", "Update")
            return False
