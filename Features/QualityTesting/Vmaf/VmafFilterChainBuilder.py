# directive: transcode-flow-canonical
from Features.QualityTesting.Vmaf.AlignmentSpec import AlignmentSpec
from Features.QualityTesting.Vmaf.VmafModelSelector import VmafModel


# directive: transcode-flow-canonical
def _Append(Chain: str, Fragment: str) -> str:
    if not Fragment:
        return Chain
    if not Chain:
        return Fragment
    return f"{Chain},{Fragment}"


# directive: transcode-flow-canonical
def _StageSetpts(Spec: AlignmentSpec, Chain: str) -> str:
    return _Append(Chain, "setpts=PTS-STARTPTS")


# directive: transcode-flow-canonical
def _StageDeinterlace(Spec: AlignmentSpec, Chain: str) -> str:
    return _Append(Chain, "yadif=1") if Spec.DeinterlaceNeeded else Chain


# directive: transcode-flow-canonical
def _StageDetelecine(Spec: AlignmentSpec, Chain: str) -> str:
    return _Append(Chain, "fieldmatch,decimate") if Spec.DetelecineNeeded else Chain


# directive: transcode-flow-canonical
def _StageFps(Spec: AlignmentSpec, Chain: str) -> str:
    return _Append(Chain, f"fps={Spec.TargetFps}")


# directive: transcode-flow-canonical
def _StageColorspace(Spec: AlignmentSpec, Chain: str) -> str:
    return _Append(Chain, f"scale=in_range=auto:out_range={Spec.ColorRange}")


# directive: transcode-flow-canonical
def _StageCrop(Spec: AlignmentSpec, Chain: str) -> str:
    if not Spec.EncodedCrop:
        return Chain
    X, Y, W, H = Spec.EncodedCrop
    return _Append(Chain, f"crop={W}:{H}:{X}:{Y}")


# directive: transcode-flow-canonical
def _StageScale(Spec: AlignmentSpec, Chain: str) -> str:
    W, H = Spec.TargetResolution
    return _Append(Chain, f"scale={W}:{H}:flags=lanczos")


# directive: transcode-flow-canonical
def _StageChroma(Spec: AlignmentSpec, Chain: str) -> str:
    Sub = Spec.ChromaSubsampling
    TenBit = Spec.TargetBitDepth >= 10
    if Sub == "4:2:0":
        Fmt = "yuv420p10le" if TenBit else "yuv420p"
    elif Sub == "4:2:2":
        Fmt = "yuv422p10le" if TenBit else "yuv422p"
    elif Sub == "4:4:4":
        Fmt = "yuv444p10le" if TenBit else "yuv444p"
    else:
        Fmt = "yuv420p10le" if TenBit else "yuv420p"
    return _Append(Chain, f"format={Fmt}")


# directive: transcode-flow-canonical
def _StageLibvmaf(Model: VmafModel, XmlLogPath: str, NThreads: int) -> str:
    return f"libvmaf=model=version={Model.value}:log_fmt=xml:log_path={XmlLogPath}:n_threads={NThreads}"


# directive: transcode-flow-canonical
class VmafFilterChainBuilder:

    # directive: transcode-flow-canonical
    @staticmethod
    def BuildPerBranchChain(Spec: AlignmentSpec) -> str:
        Chain = ""
        Chain = _StageSetpts(Spec, Chain)
        Chain = _StageDeinterlace(Spec, Chain)
        Chain = _StageDetelecine(Spec, Chain)
        Chain = _StageFps(Spec, Chain)
        Chain = _StageColorspace(Spec, Chain)
        Chain = _StageCrop(Spec, Chain)
        Chain = _StageScale(Spec, Chain)
        Chain = _StageChroma(Spec, Chain)
        return Chain

    # directive: transcode-flow-canonical
    @staticmethod
    def Build(Spec: AlignmentSpec, Model: VmafModel, XmlLogPath: str, NThreads: int = 4) -> str:
        if not XmlLogPath:
            raise ValueError("XmlLogPath must be non-empty")
        if NThreads <= 0:
            raise ValueError(f"NThreads must be > 0, got {NThreads}")
        Branch = VmafFilterChainBuilder.BuildPerBranchChain(Spec)
        Libvmaf = _StageLibvmaf(Model, XmlLogPath, NThreads)
        return f"[0:v]{Branch}[dist];[1:v]{Branch}[ref];[dist][ref]{Libvmaf}"
