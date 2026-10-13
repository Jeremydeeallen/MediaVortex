# directive: tv-tier1-classifier-pin | # see classifier.feature.md
from typing import List, Optional, Tuple

from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern
from Core.Logging.LoggingService import LoggingService
from Features.ContentClassifier.ContentClassifierRepository import ContentClassifierRepository
from Features.ContentClassifier.Models.ContentClassificationRuleModel import (
    ContentClassificationRuleModel,
)
from Features.MediaFiles.ProfileAssignmentService import ProfileAssignmentService
from Features.Profiles.FileTierResolver import FileTierResolver
from Features.Profiles.TierLadderRepository import TierLadderRepository


_SKIP_SENTINEL = "__skip__"
_SKIP_SOURCE = "classifier_skip_av1"
_CLASSIFIER_SOURCE = "classifier"
_LIBRARY_TIER_SOURCE = "library_default_tier"
_GENRE_TIER_SOURCE = "genre_tier"
_OPERATOR_SOURCES = ['operator', 'series', 'root_folder', 'manual_sql']


def _MatchesNumericRange(Value, MinV, MaxV) -> bool:
    if MinV is None and MaxV is None:
        return True
    if Value is None:
        return False
    try:
        V = float(Value)
    except (TypeError, ValueError):
        return False
    if MinV is not None and V < float(MinV):
        return False
    if MaxV is not None and V > float(MaxV):
        return False
    return True


def _MatchesCodec(MediaCodec: Optional[str], CodecIn: Optional[str]) -> bool:
    if not CodecIn:
        return True
    if not MediaCodec:
        return False
    Wanted = {C.strip().lower() for C in CodecIn.split(",") if C.strip()}
    return MediaCodec.strip().lower() in Wanted


def _MatchesResolution(MediaRes: Optional[str], RuleRes: Optional[str]) -> bool:
    if not RuleRes:
        return True
    if not MediaRes:
        return False
    return MediaRes.strip().lower() == RuleRes.strip().lower()


def _MatchesFolderPattern(MediaPath: Optional[str], Pattern: Optional[str], Db: DatabaseService) -> bool:
    if not Pattern:
        return True
    if not MediaPath:
        return False
    Rows = Db.ExecuteQuery(
        "SELECT 1 WHERE %s LIKE %s ESCAPE '!'",
        (MediaPath, Pattern),
    )
    return bool(Rows)


def _RuleMatches(Rule: ContentClassificationRuleModel, Media: dict, Db: DatabaseService) -> bool:
    if not _MatchesNumericRange(Media.get("VideoBitrateKbps"), Rule.BitrateKbpsMin, Rule.BitrateKbpsMax):
        return False
    if not _MatchesResolution(Media.get("ResolutionCategory"), Rule.ResolutionCategory):
        return False
    if not _MatchesCodec(Media.get("Codec"), Rule.CodecIn):
        return False
    if not _MatchesFolderPattern(Media.get("FilePath"), Rule.FolderPathPattern, Db):
        return False
    return True


class ContentClassifierService:
    # directive: movies-video-rule | # see classifier.C9
    def __init__(self, ProfileWriter: Optional[ProfileAssignmentService] = None):
        self.Repository = ContentClassifierRepository()
        self.Db = DatabaseService()
        self.ProfileWriter = ProfileWriter or ProfileAssignmentService(Db=self.Db)
        self.FileTiers = FileTierResolver(self.Db)
        self.Tiers = TierLadderRepository(self.Db)

    # directive: movies-video-rule | # see classifier.C9
    def _TierProfile(self, StorageRootId, MediaFileId) -> Optional[Tuple[Optional[str], str]]:
        Resolved = self.FileTiers.Resolve(StorageRootId, MediaFileId)
        if Resolved is None:
            return None
        if Resolved.Tier is None:
            return (None, Resolved.Origin)
        ProfileName = self.Tiers.GetTierProfileName(Resolved.Tier)
        if not ProfileName:
            raise RuntimeError(f"No Family='ANY' profile exists for tier {Resolved.Tier}")
        return (ProfileName, _GENRE_TIER_SOURCE if Resolved.Origin else _LIBRARY_TIER_SOURCE)

    # directive: movies-video-rule | # see classifier.C9
    def ReassignTierProfiles(self, MediaFileIds: List[int]) -> int:
        Ids = [int(I) for I in (MediaFileIds or [])]
        if not Ids:
            return 0
        Rows = self.Db.ExecuteQuery(
            "SELECT mf.Id, mf.StorageRootId, mf.AssignedProfile FROM MediaFiles mf "
            "JOIN StorageRoots sr ON sr.Id = mf.StorageRootId "
            "WHERE mf.Id = ANY(%s) AND sr.GenreSource IS NOT NULL "
            "  AND COALESCE(mf.AssignedProfileSource, '') <> ALL(%s) "
            "ORDER BY mf.Id",
            (Ids, _OPERATOR_SOURCES),
        )
        Targets = {}
        for R in Rows:
            Target = self._TierProfile(R.get('StorageRootId'), R.get('Id'))
            if Target is None or Target[0] is None or Target[0] == R.get('AssignedProfile'):
                continue
            Targets.setdefault(Target, []).append(int(R.get('Id')))
        Written = 0
        for (ProfileName, Source), Group in Targets.items():
            Written += len(self.ProfileWriter.Assign(Group, ProfileName, Source))
        return Written

    # directive: tv-video-rule-tier1 | # see classifier.C2
    def _Walk(self, Rules: List[ContentClassificationRuleModel], Media: dict) -> Optional[ContentClassificationRuleModel]:
        for Rule in Rules:
            if _RuleMatches(Rule, Media, self.Db):
                return Rule
        return None

    # directive: tv-tier1-classifier-pin | # see writer-owns-cascade.md
    def ClassifyAndAssign(self, MediaFileId: int) -> Optional[str]:
        try:
            Media = self.Repository.GetMediaFileForClassification(MediaFileId)
            if not Media:
                LoggingService.LogWarning(
                    f"ContentClassifier: MediaFileId {MediaFileId} not found",
                    "ContentClassifierService", "ClassifyAndAssign",
                )
                return None

            if Media.get("AssignedProfile"):
                return Media.get("AssignedProfile")

            TierProfile = self._TierProfile(Media.get('StorageRootId') or Media.get('storagerootid'), MediaFileId)
            if TierProfile is not None:
                LibraryProfile, TierSource = TierProfile
                if LibraryProfile is None:
                    LoggingService.LogInfo(
                        f"ContentClassifier: MediaFileId {MediaFileId} has no tier yet ({TierSource}); profile left unset",
                        "ContentClassifierService", "ClassifyAndAssign",
                    )
                    return None
                self.ProfileWriter.Assign([MediaFileId], LibraryProfile, TierSource, IfUnsetOnly=True)
                LoggingService.LogInfo(
                    f"ContentClassifier: {TierSource} -> profile '{LibraryProfile}' for MediaFileId {MediaFileId}",
                    "ContentClassifierService", "ClassifyAndAssign",
                )
                return LibraryProfile

            Rules = self.Repository.GetActiveRules()
            Matched = self._Walk(Rules, Media)
            if not Matched:
                LoggingService.LogWarning(
                    f"ContentClassifier: no rule matched MediaFileId {MediaFileId} "
                    f"(codec={Media.get('Codec')} bitrate={Media.get('VideoBitrateKbps')} "
                    f"res={Media.get('ResolutionCategory')}); leaving AssignedProfile NULL",
                    "ContentClassifierService", "ClassifyAndAssign",
                )
                return None

            if Matched.AssignProfileName == _SKIP_SENTINEL:
                self.ProfileWriter.Assign([MediaFileId], None, _SKIP_SOURCE, IfUnsetOnly=True)
                LoggingService.LogInfo(
                    f"ContentClassifier: rule '{Matched.RuleName}' skipped MediaFileId {MediaFileId} (codec={Media.get('Codec')})",
                    "ContentClassifierService", "ClassifyAndAssign",
                )
                return None

            self.ProfileWriter.Assign([MediaFileId], Matched.AssignProfileName, _CLASSIFIER_SOURCE, IfUnsetOnly=True)
            LoggingService.LogInfo(
                f"ContentClassifier: matched rule '{Matched.RuleName}' -> profile '{Matched.AssignProfileName}' for MediaFileId {MediaFileId}",
                "ContentClassifierService", "ClassifyAndAssign",
            )
            return Matched.AssignProfileName
        except Exception as Ex:
            LoggingService.LogException(
                f"ContentClassifier crashed for MediaFileId {MediaFileId}", Ex,
                "ContentClassifierService", "ClassifyAndAssign",
            )
            return None

    # directive: tv-tier1-classifier-pin
    def ClassifyAndAssignBatch(self, MediaFileIds: List[int]) -> dict:
        Rules = self.Repository.GetActiveRules()
        HitCounts = {}
        Skipped = 0
        Unmatched = 0
        ProfileToIds = {}
        LibraryProfileToIds = {}
        SkipIds = []
        for MfId in MediaFileIds:
            try:
                Media = self.Repository.GetMediaFileForClassification(MfId)
                if not Media or Media.get("AssignedProfile"):
                    Skipped += 1
                    continue
                TierProfile = self._TierProfile(Media.get('StorageRootId') or Media.get('storagerootid'), MfId)
                if TierProfile is not None:
                    if TierProfile[0] is None:
                        Unmatched += 1
                        continue
                    LibraryProfileToIds.setdefault(TierProfile, []).append(MfId)
                    HitCounts['LibraryDefaultTier'] = HitCounts.get('LibraryDefaultTier', 0) + 1
                    continue
                Matched = self._Walk(Rules, Media)
                if not Matched:
                    Unmatched += 1
                    continue
                if Matched.AssignProfileName == _SKIP_SENTINEL:
                    SkipIds.append(MfId)
                else:
                    ProfileToIds.setdefault(Matched.AssignProfileName, []).append(MfId)
                HitCounts[Matched.RuleName] = HitCounts.get(Matched.RuleName, 0) + 1
            except Exception as Ex:
                LoggingService.LogException(
                    f"ClassifyAndAssignBatch: failure on MediaFileId {MfId}", Ex,
                    "ContentClassifierService", "ClassifyAndAssignBatch",
                )
        if SkipIds:
            self.ProfileWriter.Assign(SkipIds, None, _SKIP_SOURCE, IfUnsetOnly=True)
        for (ProfileName, TierSource), Ids in LibraryProfileToIds.items():
            self.ProfileWriter.Assign(Ids, ProfileName, TierSource, IfUnsetOnly=True)
        for ProfileName, Ids in ProfileToIds.items():
            self.ProfileWriter.Assign(Ids, ProfileName, _CLASSIFIER_SOURCE, IfUnsetOnly=True)
        return {"HitCounts": HitCounts, "Skipped": Skipped, "Unmatched": Unmatched}
