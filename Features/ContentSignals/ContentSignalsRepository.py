"""Read/write for MediaFiles content-signal columns.

See Features/ContentSignals/content-signals.feature.md.
"""

from typing import Optional

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.ContentSignals.Models.ContentSignalsModel import ContentSignalsModel


class ContentSignalsRepository:
    def __init__(self):
        self.Db = DatabaseService()

    def WriteSignals(self, MediaFileId: int, Model: ContentSignalsModel) -> bool:
        try:
            self.Db.ExecuteNonQuery(
                "UPDATE MediaFiles "
                "SET MotionFraction = %s, SceneChangeRatePerMin = %s, LumaVariance = %s "
                "WHERE Id = %s",
                (Model.MotionFraction, Model.SceneChangeRatePerMin, Model.LumaVariance, MediaFileId),
            )
            return True
        except Exception as Ex:
            LoggingService.LogException(
                f"WriteSignals failed for MediaFileId {MediaFileId}", Ex,
                "ContentSignalsRepository", "WriteSignals",
            )
            return False

    def HasSignals(self, MediaFileId: int) -> bool:
        Rows = self.Db.ExecuteQuery(
            "SELECT MotionFraction FROM MediaFiles WHERE Id = %s AND MotionFraction IS NOT NULL",
            (MediaFileId,),
        )
        return bool(Rows)

    def GetSignals(self, MediaFileId: int) -> Optional[ContentSignalsModel]:
        Rows = self.Db.ExecuteQuery(
            "SELECT MotionFraction, SceneChangeRatePerMin, LumaVariance "
            "FROM MediaFiles WHERE Id = %s",
            (MediaFileId,),
        )
        if not Rows:
            return None
        R = Rows[0]
        return ContentSignalsModel(
            MotionFraction=R.get("MotionFraction"),
            SceneChangeRatePerMin=R.get("SceneChangeRatePerMin"),
            LumaVariance=R.get("LumaVariance"),
        )
