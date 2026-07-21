# directive: e2e-bug-fixes | # see e2e-bug-fixes.C27
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Features.TranscodeJob.Emit.HwAccelResolver import HwAccelResolver, HwAccelConfig


class FakeDb:
    def __init__(self, HwAccelValue):
        self.HwAccelValue = HwAccelValue

    def ExecuteQuery(self, Sql, Args):
        return [{'hwacceldecodeenabled': self.HwAccelValue}]


class FakeMediaFile:
    def __init__(self, Codec):
        self.Codec = Codec


def RunCase(Label, HwEnabled, ProfileSettings, MediaFile, RequiresScale, InputScaleFilter=None):
    Resolver = HwAccelResolver(Db=FakeDb(HwEnabled))
    Cfg = Resolver.Resolve('wakko-worker-1', ProfileSettings, MediaFile, RequiresScale)
    print(f"\n=== {Label} ===")
    print(f"  HwEnabled={HwEnabled}, RequiresScale={RequiresScale}, codec={MediaFile.Codec}, UseNv={ProfileSettings.get('UseNvidiaHardware',0)}, UseQsv={ProfileSettings.get('UseIntelHardware',0)}")
    if Cfg:
        print(f"  Backend={Cfg.Backend}  InputArgs={' '.join(Cfg.InputArgs)}  ScaleFilterName={Cfg.ScaleFilterName}")
    else:
        print("  Backend=NONE (CPU decode fallback)")
    if InputScaleFilter is not None:
        Adapted = Resolver.AdaptScaleFilter(InputScaleFilter, Cfg)
        print(f"  Scale filter: {InputScaleFilter!r} -> {Adapted!r}")


if __name__ == '__main__':
    QsvProfile = {'UseIntelHardware': 1, 'UseNvidiaHardware': 0}
    NvProfile = {'UseIntelHardware': 0, 'UseNvidiaHardware': 1}
    Hevc = FakeMediaFile('hevc')
    Av1 = FakeMediaFile('av1')
    Weird = FakeMediaFile('theora')

    RunCase("QSV enabled + hevc + scale needed", True, QsvProfile, Hevc, True, 'scale=w=1280:h=-2')
    RunCase("QSV enabled + hevc + no scale", True, QsvProfile, Hevc, False)
    RunCase("QSV enabled + theora (unsupported codec) + scale needed", True, QsvProfile, Weird, True, 'scale=w=1280:h=-2')
    RunCase("NVENC enabled + av1 + NO scale", True, NvProfile, Av1, False)
    RunCase("NVENC enabled + av1 + scale needed (baseline better)", True, NvProfile, Av1, True, 'scale=w=1280:h=-2')
    RunCase("HwAccel DISABLED + any", False, QsvProfile, Hevc, True, 'scale=w=1280:h=-2')
    RunCase("SvtAv1 (no UseNv, no UseQsv) enabled + hevc", True, {}, Hevc, True, 'scale=w=1280:h=-2')
