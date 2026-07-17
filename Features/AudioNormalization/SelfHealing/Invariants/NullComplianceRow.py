from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.AudioNormalization.SelfHealing.IAudioVerticalInvariant import IAudioVerticalInvariant


DETECT_SQL = (
    "SELECT Id FROM MediaFiles "
    "WHERE (VideoCompliant IS NULL AND VideoCompliantReason IS NULL) "
    "   OR (ContainerCompliant IS NULL AND ContainerCompliantReason IS NULL) "
    "   OR (AudioCompliant IS NULL AND AudioCompliantReason IS NULL) "
    "ORDER BY Id LIMIT 5000"
)


# directive: transcode-flow-canonical -- WorkBucket depends on 3 compliance flags being non-NULL. Scanner + probe cover the normal write path; this invariant catches any row that slipped through (crash mid-scan, migration import, manual DB insert) and hands the ids to RecomputeCompliance so they re-enter the workbucket pipeline.
class NullComplianceRow(IAudioVerticalInvariant):

    Name = "NullComplianceRow"

    def Detect(self):
        try:
            Rows = DatabaseService().ExecuteQuery(DETECT_SQL)
            return [R['id'] for R in (Rows or [])]
        except Exception as Ex:
            LoggingService.LogException("NullComplianceRow.Detect failed", Ex, self.Name, "Detect")
            return []
