# directive: e2e-bug-fixes | # see e2e-bug-fixes.C27
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from Core.Database.DatabaseService import DatabaseService


QSV_DECODE_ALLOW = frozenset({'h264', 'hevc', 'av1', 'vp9', 'mpeg2video', 'vc1'})
NVDEC_ALLOW = frozenset({'h264', 'hevc', 'av1', 'vp9', 'mpeg2video', 'vc1'})


@dataclass(frozen=True)
# directive: e2e-bug-fixes | # see e2e-bug-fixes.C27
class HwAccelConfig:
    Backend: str
    InputArgs: List[str] = field(default_factory=list)
    ScaleFilterName: Optional[str] = None


# directive: e2e-bug-fixes | # see e2e-bug-fixes.C27
class HwAccelResolver:

    # directive: e2e-bug-fixes | # see e2e-bug-fixes.C27
    def __init__(self, Db: Optional[DatabaseService] = None):
        self.Db = Db or DatabaseService()

    # directive: e2e-bug-fixes | # see e2e-bug-fixes.C27
    def Resolve(self, WorkerName: Optional[str], ProfileSettings: Dict[str, Any],
                MediaFile, RequiresScale: bool) -> Optional[HwAccelConfig]:
        if not WorkerName:
            return None
        Rows = self.Db.ExecuteQuery(
            "SELECT HwAccelDecodeEnabled FROM Workers WHERE WorkerName = %s LIMIT 1",
            (WorkerName,),
        )
        if not Rows or not Rows[0].get('hwacceldecodeenabled'):
            return None
        SourceCodec = (getattr(MediaFile, 'Codec', '') or '').strip().lower()
        UseNv = ProfileSettings.get('UseNvidiaHardware', 0)
        UseQsv = ProfileSettings.get('UseIntelHardware', 0)
        if UseQsv == 1 and SourceCodec in QSV_DECODE_ALLOW:
            return HwAccelConfig(
                Backend='qsv',
                InputArgs=['-hwaccel', 'qsv', '-hwaccel_output_format', 'qsv'],
                ScaleFilterName='scale_qsv',
            )
        if UseNv == 1 and not RequiresScale and SourceCodec in NVDEC_ALLOW:
            return HwAccelConfig(
                Backend='cuda',
                InputArgs=['-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda'],
                ScaleFilterName=None,
            )
        return None

    # directive: e2e-bug-fixes | # see e2e-bug-fixes.C27 -- scale_qsv/scale_cuda accept h=-1 (keep aspect) but reject h=-2 (scale filter's even-round shorthand). Swap prefix + coerce -2 to -1.
    def AdaptScaleFilter(self, ScaleFilter: Optional[str], HwAccel: Optional[HwAccelConfig]) -> Optional[str]:
        if not ScaleFilter or not HwAccel or not HwAccel.ScaleFilterName:
            return ScaleFilter
        if ScaleFilter.startswith('scale='):
            Rest = ScaleFilter[len('scale='):].replace('h=-2', 'h=-1')
            return HwAccel.ScaleFilterName + '=' + Rest
        return ScaleFilter
