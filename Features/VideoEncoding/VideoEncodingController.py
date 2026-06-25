from flask import Blueprint, jsonify, request

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


VideoEncodingBlueprint = Blueprint('VideoEncoding', __name__, url_prefix='/api/VideoEncoding')

_Db = DatabaseService()


# directive: compliance-tabbed-ui
@VideoEncodingBlueprint.route('/Rules', methods=['GET'])
def GetRules():
    Rows = _Db.ExecuteQuery(
        "SELECT Id, AcceptableVideoCodecsCsv, EstimatedSavingsMBThreshold, PreventUpscale, ResolutionExceedsProfileTarget, MinSourceBpp, LastUpdated "
        "FROM VideoComplianceRules ORDER BY Id LIMIT 1"
    )
    if not Rows:
        return jsonify({'Success': False, 'Message': 'VideoComplianceRules has no rows -- migration not applied'}), 500
    return jsonify({'Success': True, 'Data': Rows[0]}), 200


# directive: compliance-tabbed-ui
@VideoEncodingBlueprint.route('/Rules', methods=['PUT'])
def UpdateRules():
    Body = request.get_json(silent=True) or {}
    Codecs = (Body.get('AcceptableVideoCodecsCsv') or '').strip()
    Threshold = Body.get('EstimatedSavingsMBThreshold')
    PreventUpscale = Body.get('PreventUpscale')
    ResExceeds = Body.get('ResolutionExceedsProfileTarget')
    MinBpp = Body.get('MinSourceBpp')
    if not Codecs:
        return jsonify({'Success': False, 'Message': 'AcceptableVideoCodecsCsv is required'}), 400
    if Threshold is None or int(Threshold) < 0:
        return jsonify({'Success': False, 'Message': 'EstimatedSavingsMBThreshold must be a non-negative integer'}), 400
    if MinBpp is None or float(MinBpp) < 0:
        return jsonify({'Success': False, 'Message': 'MinSourceBpp must be a non-negative number'}), 400
    _Db.ExecuteNonQuery(
        "UPDATE VideoComplianceRules SET AcceptableVideoCodecsCsv = %s, EstimatedSavingsMBThreshold = %s, PreventUpscale = %s, ResolutionExceedsProfileTarget = %s, MinSourceBpp = %s, LastUpdated = NOW() WHERE Id = (SELECT Id FROM VideoComplianceRules ORDER BY Id LIMIT 1)",
        (Codecs, int(Threshold), bool(PreventUpscale), bool(ResExceeds), float(MinBpp)),
    )
    LoggingService.LogInfo(f"VideoComplianceRules updated: codecs={Codecs!r} threshold={Threshold} upscale={PreventUpscale} resexceeds={ResExceeds} minbpp={MinBpp}", 'VideoEncodingController', 'UpdateRules')
    # directive: worker-runtime-state
    _SpawnBackfill('Video')
    return jsonify({'Success': True, 'Message': 'Saved; library recompute kicked off in background.'}), 200


# directive: worker-runtime-state
def _SpawnBackfill(Which: str):
    import threading
    def _Run():
        try:
            Rows = DatabaseService().ExecuteQuery("SELECT Id FROM MediaFiles")
            Ids = [int(R['Id'] if 'Id' in R else R['id']) for R in (Rows or [])]
            if Which == 'Video':
                from Features.VideoEncoding.VideoVertical import VideoVertical
                VideoVertical().RecomputeFor(Ids)
            elif Which == 'Container':
                from Features.ContainerFormat.ContainerVertical import ContainerVertical
                ContainerVertical().RecomputeFor(Ids)
            LoggingService.LogInfo(f"{Which}Vertical backfill complete for {len(Ids)} files", 'ComplianceRulesUpdated', '_SpawnBackfill')
        except Exception as Ex:
            LoggingService.LogException(f"{Which}Vertical backfill failed", Ex, 'ComplianceRulesUpdated', '_SpawnBackfill')
    threading.Thread(target=_Run, daemon=True, name=f'{Which}Backfill').start()
