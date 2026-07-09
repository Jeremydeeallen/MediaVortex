# directive: transcode-flow-canonical | # see transcode-flow-canonical.C25
from typing import Optional, Tuple, Dict, Any

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


NVENC_OVERRIDES: Dict[str, Any] = {
    'Codec': 'av1_nvenc',
    'UseNvidiaHardware': 1,
    'UseIntelHardware': 0,
    'Preset': 7,
    'Tune': 'hq',
    'Multipass': 'fullres',
    'RateControlMode': 'vbr',
    'SpatialAq': 1,
    'TemporalAq': 1,
    'PixelFormat': 'p010le',
    'AudioCodec': 'libopus',
    'AudioBitrateKbps': 192,
    'AudioChannels': 6,
    'Container': 'mp4',
    'FastStart': True,
    'MaxBitrateMultiplier': 2.0,
}


QSV_OVERRIDES: Dict[str, Any] = {
    'Codec': 'av1_qsv',
    'UseNvidiaHardware': 0,
    'UseIntelHardware': 1,
    'Preset': 1,
    'RateControlMode': 'icq',
    'PixelFormat': 'p010le',
    'AudioCodec': 'libopus',
    'AudioBitrateKbps': 192,
    'AudioChannels': 6,
    'Container': 'mp4',
    'FastStart': True,
    'MaxBitrateMultiplier': 2.0,
}


# directive: transcode-flow-canonical
class WorkerEncoderResolverError(Exception):
    pass


# directive: transcode-flow-canonical
class WorkerEncoderResolver:

    # directive: transcode-flow-canonical
    def __init__(self, Db: Optional[DatabaseService] = None):
        self.Db = Db or DatabaseService()

    # directive: transcode-flow-canonical
    def Resolve(self, WorkerName: str) -> Tuple[str, Dict[str, Any]]:
        Rows = self.Db.ExecuteQuery(
            "SELECT nvenccapable, qsvcapable FROM Workers WHERE WorkerName = %s",
            (WorkerName,),
        )
        if not Rows:
            raise WorkerEncoderResolverError(f"Worker {WorkerName!r} not found in Workers table")
        Row = Rows[0]
        Nvenc = bool(Row.get('nvenccapable'))
        Qsv = bool(Row.get('qsvcapable'))
        if Nvenc:
            LoggingService.LogInfo(f"WorkerEncoderResolver: {WorkerName} -> NVENC", "WorkerEncoderResolver", "Resolve")
            return ('NVENC', dict(NVENC_OVERRIDES))
        if Qsv:
            LoggingService.LogInfo(f"WorkerEncoderResolver: {WorkerName} -> QSV", "WorkerEncoderResolver", "Resolve")
            return ('QSV', dict(QSV_OVERRIDES))
        raise WorkerEncoderResolverError(
            f"Worker {WorkerName!r} has no encode capability (nvenccapable=False AND qsvcapable=False)"
        )

    # directive: transcode-flow-canonical
    def ApplyOverrides(self, WorkerName: str, ProfileSettings: Dict[str, Any]) -> str:
        Family, Overrides = self.Resolve(WorkerName)
        for K, V in Overrides.items():
            ProfileSettings[K] = V
        return Family
