import time

from Core.Logging.LoggingService import LoggingService
from Core.Path.Path import Path, PathError
from Core.Path.PathStorageRoots import GetStorageRoots
from Core.WorkerContext import WorkerContext
from Features.AudioNormalization.Services.AudioRemeasurementService import AudioRemeasurementService, REASON_INVALID_LOUDNESS


# directive: transcode-flow-canonical -- AudioRemeasurementService has Process() but nothing calls it in production; every MediaFile flagged AdmissionDeferReason='invalid_loudness_measurement' piled up unprocessed. This runner is the SSOT loop that drains that queue and populates SourceIntegratedLufs / LRA / TruePeakDbtp / IntegratedThresholdLufs on each file. Once every deferred row is measured, AudioVertical resolves them into Compliant or AudioFix.
class AudioRemeasurementRunner:

    def __init__(self, BatchSize=20, PollSec=30, Service=None):
        self.BatchSize = int(BatchSize)
        self.PollSec = int(PollSec)
        self._Service = Service or AudioRemeasurementService()

    def RunForever(self):
        while True:
            try:
                self.RunOneCycle()
            except Exception as Ex:
                LoggingService.LogException("AudioRemeasurementRunner cycle raised", Ex, "AudioRemeasurementRunner", "RunForever")
            time.sleep(self.PollSec)

    def RunOneCycle(self):
        Candidates = self._Service.FindCandidates(Limit=self.BatchSize, Reason=REASON_INVALID_LOUDNESS)
        if not Candidates:
            return 0
        Ctx = WorkerContext.TryCurrent()
        if Ctx is None:
            LoggingService.LogInfo("AudioRemeasurementRunner: no WorkerContext bound, skipping cycle", "AudioRemeasurementRunner", "RunOneCycle")
            return 0
        Prefixes = {Sr['Id']: Sr['CanonicalPrefix'] for Sr in GetStorageRoots()}
        Processed = 0
        for Row in Candidates:
            MediaFileId = int(Row['id'])
            Sid = Row.get('storagerootid')
            Rel = Row.get('relativepath')
            if Sid is None or Rel is None:
                continue
            try:
                LocalPath = Path(int(Sid), Rel).Resolve(Ctx)
            except PathError as Ex:
                LoggingService.LogWarning(f"AudioRemeasurementRunner: path resolution failed for MediaFileId={MediaFileId}: {Ex}", "AudioRemeasurementRunner", "RunOneCycle")
                continue
            Ok, Reason = self._Service.Process(MediaFileId, LocalPath)
            LoggingService.LogInfo(f"AudioRemeasurementRunner: MediaFileId={MediaFileId} ok={Ok} reason={Reason}", "AudioRemeasurementRunner", "RunOneCycle")
            Processed += 1
        return Processed
