from typing import Optional
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService
from Features.QualityTesting.Models.PostTranscodeGateConfigModel import PostTranscodeGateConfigModel


class PostTranscodeGateConfigRepository(BaseRepository):
    """Single-row scalar config for the post-transcode disposition gate.

    Always reads/writes Id=1 (enforced by table CHECK). No caching -- every
    disposition decision reads fresh per the standing rule against cached
    DB-backed settings.
    """

    def Get(self) -> PostTranscodeGateConfigModel:
        try:
            Rows = self.ExecuteQuery(
                "SELECT Id, VmafAutoReplaceMinThreshold, VmafAutoReplaceMaxThreshold, "
                "WhenVmafUnavailable, QualityTestEnabled, MaxRequeueAttempts, "
                "WorkerHeartbeatWindowSec, RetranscodeVmafThreshold, "
                "MinConfidenceSampleCount, MinConfidencePassRate, SigmaMargin, "
                "LastUpdated "
                "FROM PostTranscodeGateConfig WHERE Id = 1"
            )
            if not Rows:
                LoggingService.LogWarning(
                    "PostTranscodeGateConfig row Id=1 missing -- returning defaults. "
                    "Run Scripts/SQLScripts/AddPostTranscodeDisposition.py to seed.",
                    "PostTranscodeGateConfigRepository", "Get",
                )
                return PostTranscodeGateConfigModel()
            R = Rows[0]
            return PostTranscodeGateConfigModel(
                Id=R['Id'],
                VmafAutoReplaceMinThreshold=float(R['VmafAutoReplaceMinThreshold']),
                VmafAutoReplaceMaxThreshold=float(R['VmafAutoReplaceMaxThreshold']),
                WhenVmafUnavailable=R['WhenVmafUnavailable'],
                QualityTestEnabled=bool(R['QualityTestEnabled']),
                MaxRequeueAttempts=int(R['MaxRequeueAttempts']),
                WorkerHeartbeatWindowSec=int(R['WorkerHeartbeatWindowSec']),
                RetranscodeVmafThreshold=int(R['RetranscodeVmafThreshold']),
                MinConfidenceSampleCount=int(R.get('MinConfidenceSampleCount') or 10),
                MinConfidencePassRate=float(R.get('MinConfidencePassRate') or 0.95),
                SigmaMargin=float(R.get('SigmaMargin') or 2.0),
                LastUpdated=R.get('LastUpdated'),
            )
        except Exception as Ex:
            LoggingService.LogException(
                "Get failed", Ex, "PostTranscodeGateConfigRepository", "Get",
            )
            return PostTranscodeGateConfigModel()

    # directive: transcode-flow-canonical | # see post-transcode-disposition.C26
    def Update(self, VmafAutoReplaceMinThreshold: Optional[float] = None,
               VmafAutoReplaceMaxThreshold: Optional[float] = None,
               WhenVmafUnavailable: Optional[str] = None,
               QualityTestEnabled: Optional[bool] = None,
               MinConfidenceSampleCount: Optional[int] = None,
               MinConfidencePassRate: Optional[float] = None,
               SigmaMargin: Optional[float] = None) -> bool:
        try:
            Sets = []
            Values = []
            if VmafAutoReplaceMinThreshold is not None:
                Sets.append("VmafAutoReplaceMinThreshold = %s")
                Values.append(float(VmafAutoReplaceMinThreshold))
            if VmafAutoReplaceMaxThreshold is not None:
                Sets.append("VmafAutoReplaceMaxThreshold = %s")
                Values.append(float(VmafAutoReplaceMaxThreshold))
            if WhenVmafUnavailable is not None:
                if WhenVmafUnavailable not in ('block', 'bypass'):
                    LoggingService.LogError(
                        f"Update rejected: WhenVmafUnavailable={WhenVmafUnavailable!r} "
                        f"must be 'block' or 'bypass'",
                        "PostTranscodeGateConfigRepository", "Update",
                    )
                    return False
                Sets.append("WhenVmafUnavailable = %s")
                Values.append(WhenVmafUnavailable)
            if QualityTestEnabled is not None:
                Sets.append("QualityTestEnabled = %s")
                Values.append(bool(QualityTestEnabled))
            if MinConfidenceSampleCount is not None:
                Count = int(MinConfidenceSampleCount)
                if Count < 1:
                    LoggingService.LogError(f"Update rejected: MinConfidenceSampleCount={Count} must be >= 1", "PostTranscodeGateConfigRepository", "Update")
                    return False
                Sets.append("MinConfidenceSampleCount = %s")
                Values.append(Count)
            if MinConfidencePassRate is not None:
                Rate = float(MinConfidencePassRate)
                if not (0.0 <= Rate <= 1.0):
                    LoggingService.LogError(f"Update rejected: MinConfidencePassRate={Rate} must be in [0.0,1.0]", "PostTranscodeGateConfigRepository", "Update")
                    return False
                Sets.append("MinConfidencePassRate = %s")
                Values.append(Rate)
            if SigmaMargin is not None:
                Sigma = float(SigmaMargin)
                if Sigma < 0.0:
                    LoggingService.LogError(f"Update rejected: SigmaMargin={Sigma} must be >= 0.0", "PostTranscodeGateConfigRepository", "Update")
                    return False
                Sets.append("SigmaMargin = %s")
                Values.append(Sigma)
            if not Sets:
                return True
            Sets.append("LastUpdated = NOW()")
            Query = f"UPDATE PostTranscodeGateConfig SET {', '.join(Sets)} WHERE Id = 1"
            self.ExecuteNonQuery(Query, tuple(Values))
            return True
        except Exception as Ex:
            LoggingService.LogException(
                "Update failed", Ex, "PostTranscodeGateConfigRepository", "Update",
            )
            return False
