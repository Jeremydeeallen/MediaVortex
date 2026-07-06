# directive: transcode-flow-canonical
from enum import Enum
from Features.QualityTesting.Vmaf.AlignmentSpec import AlignmentSpec


# directive: transcode-flow-canonical
class VmafModel(Enum):
    Default = "vmaf_v0.6.1"
    Model4K = "vmaf_4k_v0.6.1"
    Phone = "vmaf_v0.6.1_phone"
    Neg = "vmaf_v0.6.1neg"


# directive: transcode-flow-canonical
class VmafModelSelector:

    # directive: transcode-flow-canonical
    @staticmethod
    def Select(Spec: AlignmentSpec) -> VmafModel:
        if Spec.MaxEdgePx >= 1440:
            return VmafModel.Model4K
        if Spec.MaxEdgePx <= 540:
            return VmafModel.Phone
        if Spec.HdrDetected:
            return VmafModel.Neg
        return VmafModel.Default
