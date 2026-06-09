from Features.Compliance.Repositories.TranscodeRulesRepository import TranscodeRulesRepository
from Features.Compliance.Repositories.RemuxRulesRepository import RemuxRulesRepository
from Features.Compliance.Repositories.AudioFixRulesRepository import AudioFixRulesRepository
from Features.Compliance.Repositories.SubtitleFixRulesRepository import SubtitleFixRulesRepository
from Features.Compliance.Repositories.ComplianceGatesRepository import ComplianceGatesRepository
from Features.Compliance.Models.ComplianceRuleCache import ComplianceRuleCache
from Features.Compliance.Operations.TranscodeOperation import TranscodeOperation
from Features.Compliance.Operations.RemuxOperation import RemuxOperation
from Features.Compliance.Operations.AudioFixOperation import AudioFixOperation
from Features.Compliance.Operations.SubtitleFixOperation import SubtitleFixOperation
from Features.Compliance.Gates.EnglishAudioGate import EnglishAudioGate
from Features.Compliance.Gates.AudioCorruptSuspectGate import AudioCorruptSuspectGate
from Features.Compliance.Gates.AudioStreamGate import AudioStreamGate
from Features.Compliance.Gates.LoudnessMeasurementsGate import LoudnessMeasurementsGate
from Features.Compliance.Gates.ProbeMetadataGate import ProbeMetadataGate
from Features.Compliance.Gates.EffectiveProfileGate import EffectiveProfileGate
from Features.Compliance.Gates.ResolutionCategoryGate import ResolutionCategoryGate
from Features.Compliance.Gates.ProfileThresholdsGate import ProfileThresholdsGate
from Features.Compliance.Services.ComplianceGateChain import ComplianceGateChain
from Features.Compliance.Services.ComplianceRuleEngine import ComplianceRuleEngine
from Features.Compliance.Services.ComplianceBucketResolver import ComplianceBucketResolver
from Features.Compliance.Services.ComplianceEvaluator import ComplianceEvaluator


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C11
def BuildEvaluator() -> ComplianceEvaluator:
    """Composition root -- wires gates + operations + resolver into a ready-to-use ComplianceEvaluator."""
    Gates = [
        EnglishAudioGate(),
        AudioCorruptSuspectGate(),
        AudioStreamGate(),
        ProbeMetadataGate(),
        EffectiveProfileGate(),
        ResolutionCategoryGate(),
        ProfileThresholdsGate(),
        LoudnessMeasurementsGate(),
    ]
    Operations = [
        TranscodeOperation(),
        RemuxOperation(),
        AudioFixOperation(),
        SubtitleFixOperation(),
    ]
    return ComplianceEvaluator(
        GateChain=ComplianceGateChain(Gates),
        RuleEngine=ComplianceRuleEngine(Operations),
        BucketResolver=ComplianceBucketResolver(),
    )


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C12
def BuildRuleCache() -> ComplianceRuleCache:
    """Load every rule table once; returned snapshot is the input to ComplianceEvaluator.Evaluate for bulk recompute."""
    return ComplianceRuleCache(
        Gates=ComplianceGatesRepository().Get(),
        TranscodeRules=TranscodeRulesRepository().Get(),
        RemuxRules=RemuxRulesRepository().Get(),
        AudioFixRules=AudioFixRulesRepository().Get(),
        SubtitleFixRules=SubtitleFixRulesRepository().Get(),
    )
