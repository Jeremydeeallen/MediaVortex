# directive: transcode-flow-canonical
from typing import List, Optional
from Features.QualityTesting.Vmaf.AlignmentSpec import AlignmentSpec
from Features.QualityTesting.Vmaf.VmafFilterChainBuilder import VmafFilterChainBuilder
from Features.QualityTesting.Vmaf.VmafModelSelector import VmafModelSelector, VmafModel


# directive: transcode-flow-canonical
class VmafCommandComposer:

    # directive: transcode-flow-canonical
    @staticmethod
    def Build(
        FFmpegPath: str,
        DistortedPath: str,
        ReferencePath: str,
        Spec: AlignmentSpec,
        XmlLogPath: str,
        StartTime: Optional[str] = None,
        NThreads: int = 4,
        Model: Optional[VmafModel] = None,
    ) -> List[str]:
        if not FFmpegPath:
            raise ValueError("FFmpegPath must be non-empty")
        if not DistortedPath:
            raise ValueError("DistortedPath must be non-empty")
        if not ReferencePath:
            raise ValueError("ReferencePath must be non-empty")
        if not XmlLogPath:
            raise ValueError("XmlLogPath must be non-empty")
        ChosenModel = Model if Model is not None else VmafModelSelector.Select(Spec)
        FilterChain = VmafFilterChainBuilder.Build(Spec, ChosenModel, XmlLogPath, NThreads)
        Argv: List[str] = [FFmpegPath]
        if StartTime:
            Argv.extend(["-ss", StartTime])
        Argv.extend(["-i", DistortedPath, "-i", ReferencePath])
        Argv.extend(["-lavfi", FilterChain, "-f", "null", "-"])
        return Argv
