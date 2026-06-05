"""Read/write for ContentClassificationRules and MediaFiles.AssignedProfile.

See Features/ContentClassifier/content-classifier.feature.md.
"""

from typing import List, Optional

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.ContentClassifier.Models.ContentClassificationRuleModel import (
    ContentClassificationRuleModel,
)


class ContentClassifierRepository:
    def __init__(self):
        self.Db = DatabaseService()

    def GetActiveRules(self) -> List[ContentClassificationRuleModel]:
        Rows = self.Db.ExecuteQuery(
            "SELECT Id, Priority, RuleName, IsActive, AssignProfileName, "
            "       BitrateKbpsMin, BitrateKbpsMax, ResolutionCategory, CodecIn, "
            "       MotionFractionMin, MotionFractionMax, SceneChangeRateMin, SceneChangeRateMax, "
            "       LumaVarianceMin, LumaVarianceMax, FolderPathPattern, Description "
            "FROM ContentClassificationRules "
            "WHERE IsActive = TRUE "
            "ORDER BY Priority ASC",
            (),
        )
        Rules = []
        for R in Rows:
            Rules.append(ContentClassificationRuleModel(
                Id=R.get("Id"),
                Priority=R.get("Priority"),
                RuleName=R.get("RuleName"),
                IsActive=bool(R.get("IsActive")),
                AssignProfileName=R.get("AssignProfileName"),
                BitrateKbpsMin=R.get("BitrateKbpsMin"),
                BitrateKbpsMax=R.get("BitrateKbpsMax"),
                ResolutionCategory=R.get("ResolutionCategory"),
                CodecIn=R.get("CodecIn"),
                MotionFractionMin=R.get("MotionFractionMin"),
                MotionFractionMax=R.get("MotionFractionMax"),
                SceneChangeRateMin=R.get("SceneChangeRateMin"),
                SceneChangeRateMax=R.get("SceneChangeRateMax"),
                LumaVarianceMin=R.get("LumaVarianceMin"),
                LumaVarianceMax=R.get("LumaVarianceMax"),
                FolderPathPattern=R.get("FolderPathPattern"),
                Description=R.get("Description"),
            ))
        return Rules

    def WriteAssignment(self, MediaFileId: int, ProfileName: Optional[str], Source: str) -> bool:
        try:
            self.Db.ExecuteNonQuery(
                "UPDATE MediaFiles "
                "SET AssignedProfile = %s, AssignedProfileSource = %s "
                "WHERE Id = %s AND AssignedProfile IS NULL",
                (ProfileName, Source, MediaFileId),
            )
            return True
        except Exception as Ex:
            LoggingService.LogException(
                f"WriteAssignment failed for MediaFileId {MediaFileId}", Ex,
                "ContentClassifierRepository", "WriteAssignment",
            )
            return False

    # directive: path-schema-migration | # see content-classifier.C5 -- typed-pair SELECT; FilePath synthesized for FolderPathPattern matching
    def GetMediaFileForClassification(self, MediaFileId: int) -> Optional[dict]:
        """Return row dict for the classifier; FilePath is computed via PathStorageRoots, not the renamed column."""
        Rows = self.Db.ExecuteQuery(
            "SELECT Id, StorageRootId, RelativePath, Codec, ResolutionCategory, VideoBitrateKbps, "
            "       MotionFraction, SceneChangeRatePerMin, LumaVariance, AssignedProfile "
            "FROM MediaFiles WHERE Id = %s",
            (MediaFileId,),
        )
        if not Rows:
            return None
        from Core.Path.Path import Path as _PathCC, PathError as _PECC
        from Core.Path.PathStorageRoots import GetPrefixMap as _GPMCC
        _PmCC = _GPMCC()
        Row = dict(Rows[0])
        Sid = Row.get('StorageRootId') or Row.get('storagerootid')
        Rel = Row.get('RelativePath') or Row.get('relativepath') or ''
        FilePath = ''
        if Sid is not None:
            try:
                FilePath = _PathCC(Sid, Rel).CanonicalDisplay(_PmCC)
            except _PECC:
                FilePath = ''
        Row['FilePath'] = FilePath
        return Row
