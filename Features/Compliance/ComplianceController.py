from dataclasses import asdict
from flask import Blueprint, request, jsonify
from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.Compliance.Repositories.TranscodeRulesRepository import TranscodeRulesRepository
from Features.Compliance.Repositories.RemuxRulesRepository import RemuxRulesRepository
from Features.Compliance.Repositories.AudioFixRulesRepository import AudioFixRulesRepository
from Features.Compliance.Repositories.SubtitleFixRulesRepository import SubtitleFixRulesRepository
from Features.Compliance.Repositories.ComplianceGatesRepository import ComplianceGatesRepository
from Features.Compliance.Services.ComplianceRecomputeService import ComplianceRecomputeService


ComplianceBlueprint = Blueprint('Compliance', __name__, url_prefix='/api/Compliance')


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C18
def _Envelope(Success, Data=None, Message=None, Status=200):
    """{Success, Message, Data} envelope per CLAUDE.md API contract."""
    Body = {'Success': Success}
    if Message is not None:
        Body['Message'] = Message
    if Data is not None:
        Body['Data'] = Data
    return jsonify(Body), Status


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C16
def _ModelToJson(Model):
    """Convert a dataclass model to a JSON-safe dict; LastUpdated -> ISO string."""
    D = asdict(Model)
    Lu = D.get('LastUpdated')
    if Lu is not None and hasattr(Lu, 'isoformat'):
        D['LastUpdated'] = Lu.isoformat()
    return D


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C16
@ComplianceBlueprint.route('/TranscodeRules', methods=['GET'])
def GetTranscodeRules():
    return _Envelope(True, Data=_ModelToJson(TranscodeRulesRepository().Get()))


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C16
@ComplianceBlueprint.route('/TranscodeRules', methods=['PUT'])
def UpdateTranscodeRules():
    Body = request.get_json(silent=True) or {}
    Ok = TranscodeRulesRepository().Update(
        ResolutionExceedsProfileTarget=Body.get('ResolutionExceedsProfileTarget'),
        AcceptableVideoCodecsCsv=Body.get('AcceptableVideoCodecsCsv'),
        EstimatedSavingsMBThreshold=Body.get('EstimatedSavingsMBThreshold'),
        PreventUpscale=Body.get('PreventUpscale'),
    )
    if not Ok:
        return _Envelope(False, Message='Update failed -- see logs', Status=500)
    return _Envelope(True, Data=_ModelToJson(TranscodeRulesRepository().Get()))


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C16
@ComplianceBlueprint.route('/RemuxRules', methods=['GET'])
def GetRemuxRules():
    return _Envelope(True, Data=_ModelToJson(RemuxRulesRepository().Get()))


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C16
@ComplianceBlueprint.route('/RemuxRules', methods=['PUT'])
def UpdateRemuxRules():
    Body = request.get_json(silent=True) or {}
    Ok = RemuxRulesRepository().Update(
        AcceptableContainersCsv=Body.get('AcceptableContainersCsv'),
        AcceptableAudioCodecsMp4Csv=Body.get('AcceptableAudioCodecsMp4Csv'),
        RequireAudioNormalized=Body.get('RequireAudioNormalized'),
    )
    if not Ok:
        return _Envelope(False, Message='Update failed -- see logs', Status=500)
    return _Envelope(True, Data=_ModelToJson(RemuxRulesRepository().Get()))


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C16
@ComplianceBlueprint.route('/AudioFixRules', methods=['GET'])
def GetAudioFixRules():
    return _Envelope(True, Data=_ModelToJson(AudioFixRulesRepository().Get()))


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C16
@ComplianceBlueprint.route('/AudioFixRules', methods=['PUT'])
def UpdateAudioFixRules():
    Body = request.get_json(silent=True) or {}
    Ok = AudioFixRulesRepository().Update(
        TargetLoudnessLufs=Body.get('TargetLoudnessLufs'),
        ToleranceLufs=Body.get('ToleranceLufs'),
        RequireLufsMeasured=Body.get('RequireLufsMeasured'),
    )
    if not Ok:
        return _Envelope(False, Message='Update failed -- see logs', Status=500)
    return _Envelope(True, Data=_ModelToJson(AudioFixRulesRepository().Get()))


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C16
@ComplianceBlueprint.route('/SubtitleFixRules', methods=['GET'])
def GetSubtitleFixRules():
    return _Envelope(True, Data=_ModelToJson(SubtitleFixRulesRepository().Get()))


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C16
@ComplianceBlueprint.route('/SubtitleFixRules', methods=['PUT'])
def UpdateSubtitleFixRules():
    Body = request.get_json(silent=True) or {}
    Ok = SubtitleFixRulesRepository().Update(
        Enabled=Body.get('Enabled'),
        MovTextRequiredForMp4=Body.get('MovTextRequiredForMp4'),
        NonNativeSubtitleFormatsCsv=Body.get('NonNativeSubtitleFormatsCsv'),
        RequireForcedSubtitlesPresent=Body.get('RequireForcedSubtitlesPresent'),
    )
    if not Ok:
        return _Envelope(False, Message='Update failed -- see logs', Status=500)
    return _Envelope(True, Data=_ModelToJson(SubtitleFixRulesRepository().Get()))


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C16
@ComplianceBlueprint.route('/Gates', methods=['GET'])
def GetGates():
    return _Envelope(True, Data=_ModelToJson(ComplianceGatesRepository().Get()))


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C16
@ComplianceBlueprint.route('/Gates', methods=['PUT'])
def UpdateGates():
    Body = request.get_json(silent=True) or {}
    Ok = ComplianceGatesRepository().Update(
        RequireExplicitEnglishAudio=Body.get('RequireExplicitEnglishAudio'),
        BlockOnAudioCorruptSuspect=Body.get('BlockOnAudioCorruptSuspect'),
        RequireAudioStream=Body.get('RequireAudioStream'),
        RequireLoudnessMeasurements=Body.get('RequireLoudnessMeasurements'),
        RequireProbeMetadata=Body.get('RequireProbeMetadata'),
        RequireEffectiveProfile=Body.get('RequireEffectiveProfile'),
        RequireResolutionCategory=Body.get('RequireResolutionCategory'),
        RequireProfileThresholds=Body.get('RequireProfileThresholds'),
    )
    if not Ok:
        return _Envelope(False, Message='Update failed -- see logs', Status=500)
    return _Envelope(True, Data=_ModelToJson(ComplianceGatesRepository().Get()))


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C19
@ComplianceBlueprint.route('/Buckets', methods=['GET'])
def GetBucketCounts():
    """Live per-WorkBucket count from MediaFiles for the GUI widget."""
    Rows = DatabaseService().ExecuteQuery("SELECT WorkBucket, COUNT(*) AS N FROM MediaFiles GROUP BY WorkBucket")
    Counts = {(R['WorkBucket'] or '_Unevaluated'): int(R['N']) for R in Rows}
    GateRows = DatabaseService().ExecuteQuery("SELECT ComplianceGateBlocked, COUNT(*) AS N FROM MediaFiles WHERE ComplianceGateBlocked IS NOT NULL GROUP BY ComplianceGateBlocked")
    Gates = {R['ComplianceGateBlocked']: int(R['N']) for R in GateRows}
    return _Envelope(True, Data={'Buckets': Counts, 'GateBlocked': Gates})


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C17
@ComplianceBlueprint.route('/Preview', methods=['POST'])
def PreviewRecompute():
    """Dry recompute against a 1,000-row sample; returns bucket + gate breakdown without DB writes."""
    Limit = request.get_json(silent=True) or {}
    Sample = max(1, min(5000, int(Limit.get('SampleSize', 1000))))
    Ids = [R['Id'] for R in DatabaseService().ExecuteQuery("SELECT Id FROM MediaFiles ORDER BY RANDOM() LIMIT %s", (Sample,))]
    Result = ComplianceRecomputeService().Recompute(Ids, DryRun=True)
    return _Envelope(True, Data=Result)


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C23
@ComplianceBlueprint.route('/Recompute', methods=['POST'])
def Recompute():
    """Run ComplianceEvaluator across MediaFileIds and write WorkBucket/OperationsNeededCsv/ComplianceGateBlocked. Body: {MediaFileIds: [..]} OR {All: true} OR {Drive: 'T:'}."""
    Body = request.get_json(silent=True) or {}
    Ids = []
    if Body.get('All') is True:
        Ids = [R['Id'] for R in DatabaseService().ExecuteQuery("SELECT Id FROM MediaFiles ORDER BY Id")]
    elif Body.get('MediaFileIds'):
        Ids = [int(I) for I in Body['MediaFileIds']]
    else:
        return _Envelope(False, Message='Body must include MediaFileIds[] or All=true', Status=400)
    try:
        Result = ComplianceRecomputeService().Recompute(Ids, DryRun=False)
        return _Envelope(True, Data=Result)
    except Exception as Ex:
        LoggingService.LogException("Recompute failed", Ex, "ComplianceController", "Recompute")
        return _Envelope(False, Message=str(Ex), Status=500)
