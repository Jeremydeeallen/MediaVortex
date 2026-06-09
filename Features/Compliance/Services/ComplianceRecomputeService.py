from typing import List, Optional, Dict, Any
from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Models.MediaFileModel import MediaFileModel
from Features.Compliance.Models.EffectiveProfile import EffectiveProfile
from Features.Compliance.ComplianceComposition import BuildEvaluator, BuildRuleCache


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C23
class ComplianceRecomputeService:
    """Runs ComplianceEvaluator across MediaFileIds and writes back to MediaFiles.WorkBucket / OperationsNeededCsv / ComplianceGateBlocked / ComplianceEvaluatedAt -- Batch 1 standalone path; Batch 2 will merge with RecomputeForFiles."""

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C23
    def __init__(self, DatabaseServiceInstance: Optional[DatabaseService] = None):
        self.DB = DatabaseServiceInstance or DatabaseService()
        self.Evaluator = BuildEvaluator()

    # directive: compliance-solid-refactor | # see compliance-solid-refactor.C23
    def Recompute(self, MediaFileIds: List[int], DryRun: bool = False) -> Dict[str, Any]:
        """Evaluate each MediaFile and (unless DryRun) write the new compliance fields; returns counts + per-bucket breakdown."""
        if not MediaFileIds:
            return {'Evaluated': 0, 'Bucketed': {}, 'GateBlocked': {}, 'DryRun': DryRun}
        Cache = BuildRuleCache()
        Thresholds = self._LoadThresholdLookup()

        Bucketed: Dict[str, int] = {}
        GateBlocked: Dict[str, int] = {}
        Updates = []

        Rows = self.DB.ExecuteQuery(self._SelectSql(len(MediaFileIds)), tuple(MediaFileIds))
        for Row in Rows:
            Mf = self._RowToMediaFile(Row)
            Profile = self._ResolveProfile(Mf, Thresholds)
            Decision = self.Evaluator.Evaluate(Mf, Profile, Cache)
            if Decision.GateBlocked is not None:
                GateBlocked[Decision.GateBlocked] = GateBlocked.get(Decision.GateBlocked, 0) + 1
            elif Decision.WorkBucket is not None:
                Bucketed[Decision.WorkBucket] = Bucketed.get(Decision.WorkBucket, 0) + 1
            else:
                Bucketed['_Compliant'] = Bucketed.get('_Compliant', 0) + 1
            Updates.append((Mf.Id, Decision))

        if not DryRun:
            for MfId, Decision in Updates:
                OpsCsv = ','.join(sorted(Decision.OperationsNeeded)) if Decision.OperationsNeeded else None
                self.DB.ExecuteNonQuery(
                    "UPDATE MediaFiles SET WorkBucket = %s, OperationsNeededCsv = %s, ComplianceGateBlocked = %s, ComplianceEvaluatedAt = NOW() WHERE Id = %s",
                    (Decision.WorkBucket, OpsCsv, Decision.GateBlocked, MfId),
                )
            LoggingService.LogInfo(f"ComplianceRecomputeService: evaluated {len(Updates)} rows; bucketed={Bucketed}; gate_blocked={GateBlocked}", "ComplianceRecomputeService", "Recompute")

        return {'Evaluated': len(Updates), 'Bucketed': Bucketed, 'GateBlocked': GateBlocked, 'DryRun': DryRun}

    @staticmethod
    def _SelectSql(N: int) -> str:
        Placeholders = ','.join(['%s'] * N)
        return ("SELECT Id, FileName, SizeMB, DurationMinutes, Resolution, ResolutionCategory, Codec, VideoBitrateKbps, AudioCodec, AudioChannels, AudioBitrateKbps, AudioComplete, AudioCorruptSuspect, ContainerFormat, SubtitleFormats, AssignedProfile, HasExplicitEnglishAudio, HasForcedSubtitles, SourceIntegratedLufs, SourceLoudnessRangeLU, SourceTruePeakDbtp, SourceIntegratedThresholdLufs FROM MediaFiles WHERE Id IN (" + Placeholders + ")")

    @staticmethod
    def _RowToMediaFile(R: dict) -> MediaFileModel:
        return MediaFileModel(
            Id=R['Id'], FileName=R.get('FileName') or '',
            SizeMB=float(R.get('SizeMB') or 0), DurationMinutes=R.get('DurationMinutes'),
            Resolution=R.get('Resolution'), ResolutionCategory=R.get('ResolutionCategory'),
            Codec=R.get('Codec'), VideoBitrateKbps=R.get('VideoBitrateKbps'),
            AudioCodec=R.get('AudioCodec'), AudioChannels=R.get('AudioChannels'), AudioBitrateKbps=R.get('AudioBitrateKbps'),
            AudioComplete=R.get('AudioComplete'), AudioCorruptSuspect=R.get('AudioCorruptSuspect') if R.get('AudioCorruptSuspect') is not None else False,
            ContainerFormat=R.get('ContainerFormat'), SubtitleFormats=R.get('SubtitleFormats'),
            AssignedProfile=R.get('AssignedProfile'),
            HasExplicitEnglishAudio=R.get('HasExplicitEnglishAudio'), HasForcedSubtitles=R.get('HasForcedSubtitles'),
            SourceIntegratedLufs=R.get('SourceIntegratedLufs'), SourceLoudnessRangeLU=R.get('SourceLoudnessRangeLU'),
            SourceTruePeakDbtp=R.get('SourceTruePeakDbtp'), SourceIntegratedThresholdLufs=R.get('SourceIntegratedThresholdLufs'),
        )

    def _LoadThresholdLookup(self) -> Dict[tuple, tuple]:
        """Return {(ProfileName, SourceResolutionCategory): (TargetVideoKbps, TargetAudioKbps, TargetResolutionCategory)} for all profiles."""
        Rows = self.DB.ExecuteQuery("SELECT p.ProfileName, pt.Resolution, pt.VideoBitrateKbps, pt.AudioBitrateKbps, pt.TranscodeDownTo FROM Profiles p JOIN ProfileThresholds pt ON pt.ProfileId = p.Id")
        Lookup = {}
        for R in Rows:
            Target = R['TranscodeDownTo'] or R['Resolution']
            Lookup[(R['ProfileName'], R['Resolution'])] = (R['VideoBitrateKbps'] or None, R['AudioBitrateKbps'] or None, Target)
        return Lookup

    def _ResolveProfile(self, Mf: MediaFileModel, Thresholds: Dict[tuple, tuple]) -> Optional[EffectiveProfile]:
        """Minimal cascade for Batch 1: use MediaFile.AssignedProfile + ResolutionCategory key; ShowSettings overlay deferred to Batch 2."""
        if not Mf.AssignedProfile or not Mf.ResolutionCategory:
            return None
        Hit = Thresholds.get((Mf.AssignedProfile, Mf.ResolutionCategory))
        if not Hit:
            return EffectiveProfile(ProfileName=Mf.AssignedProfile, TargetVideoKbps=None, TargetAudioKbps=None, TargetResolutionCategory=None)
        Vk, Ak, Tgt = Hit
        return EffectiveProfile(ProfileName=Mf.AssignedProfile, TargetVideoKbps=Vk, TargetAudioKbps=Ak, TargetResolutionCategory=Tgt)
