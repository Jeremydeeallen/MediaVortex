from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager


# directive: filereplacement-drain-bug
class FileReplacementSelfHealService:

    STUCK_QUERY = (
        "SELECT ta.Id AS attempt_id, ta.MediaFileId, ta.OldSizeBytes, "
        "tfp.Id AS tfp_id, m.SizeMB "
        "FROM TranscodeAttempts ta "
        "LEFT JOIN TemporaryFilePaths tfp ON tfp.TranscodeAttemptId = ta.Id "
        "LEFT JOIN MediaFiles m ON m.Id = ta.MediaFileId "
        "WHERE ta.Disposition = 'Replace' AND ta.FileReplaced = FALSE "
        "AND ta.AttemptDate < NOW() - INTERVAL '5 minutes' "
        "AND (ta.ErrorMessage IS NULL OR ta.ErrorMessage NOT ILIKE '%%Recovery refused%%') "
        "ORDER BY ta.Id LIMIT 50"
    )

    # directive: filereplacement-drain-bug
    def __init__(self, Db=None, Mgr=None):
        self._Db = Db or DatabaseService()
        self._Mgr = Mgr or DatabaseManager()

    # directive: filereplacement-drain-bug
    def Run(self):
        try:
            Rows = self._Db.ExecuteQuery(self.STUCK_QUERY)
        except Exception as Ex:
            LoggingService.LogException("Self-heal scan failed", Ex, "FileReplacementSelfHealService", "Run")
            return {'Scanned': 0, 'Recovered': 0, 'Refused': 0}

        if not Rows:
            return {'Scanned': 0, 'Recovered': 0, 'Refused': 0}

        Recovered = 0
        Refused = 0
        for R in Rows:
            Aid = R['attempt_id']
            OldBytes = R['oldsizebytes'] or 0
            SizeMb = float(R['sizemb'] or 0)
            TruthBytes = int(SizeMb * 1024 * 1024)
            TfpId = R['tfp_id']

            if OldBytes == 0 and TruthBytes > 0:
                try:
                    self._Db.ExecuteNonQuery(
                        "UPDATE TranscodeAttempts SET OldSizeBytes = %s WHERE Id = %s",
                        (TruthBytes, Aid),
                    )
                except Exception as UEx:
                    LoggingService.LogException(f"OldSizeBytes backfill failed for {Aid}", UEx,
                                                "FileReplacementSelfHealService", "Run")

            if TfpId is None:
                try:
                    self._Db.ExecuteNonQuery(
                        "UPDATE TranscodeAttempts SET ErrorMessage = %s WHERE Id = %s",
                        (f"Recovery refused: TFP missing (self-heal)", Aid),
                    )
                except Exception:
                    pass
                Refused += 1
                continue

            try:
                from Features.FileReplacement.FileReplacementBusinessService import FileReplacementBusinessService
                Res = FileReplacementBusinessService(self._Mgr).ProcessFileReplacement(Aid)
                if Res.get('Success'):
                    Recovered += 1
                    LoggingService.LogInfo(f"Self-heal recovered TranscodeAttempt {Aid}",
                                           "FileReplacementSelfHealService", "Run")
                else:
                    Refused += 1
                    Err = Res.get('ErrorMessage') or 'unknown'
                    self._Db.ExecuteNonQuery(
                        "UPDATE TranscodeAttempts SET ErrorMessage = %s WHERE Id = %s",
                        (f"Recovery refused (self-heal): {Err[:400]}", Aid),
                    )
            except Exception as PEx:
                Refused += 1
                LoggingService.LogException(f"Self-heal recovery raised for {Aid}", PEx,
                                            "FileReplacementSelfHealService", "Run")

        if Recovered or Refused:
            LoggingService.LogInfo(
                f"Self-heal sweep: scanned={len(Rows)} recovered={Recovered} refused={Refused}",
                "FileReplacementSelfHealService", "Run",
            )
        return {'Scanned': len(Rows), 'Recovered': Recovered, 'Refused': Refused}
