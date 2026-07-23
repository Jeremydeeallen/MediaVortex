import time
from flask import Blueprint, jsonify, request

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


VideoEncodingBlueprint = Blueprint('VideoEncoding', __name__, url_prefix='/api/VideoEncoding')

_Db = DatabaseService()

# directive: worker-runtime-state
_BackfillStatus = {'Running': False, 'Total': 0, 'Completed': 0, 'StartedAt': None, 'FinishedAt': None, 'DurationSec': None, 'LastError': None}


# directive: transcode-flow-canonical | # see video-encoding.C2
@VideoEncodingBlueprint.route('/Rules', methods=['GET'])
def GetRules():
    Rows = _Db.ExecuteQuery(
        "SELECT Id, AcceptableVideoCodecsCsv, LastUpdated FROM VideoComplianceRules ORDER BY Id LIMIT 1"
    )
    if not Rows:
        return jsonify({'Success': False, 'Message': 'VideoComplianceRules has no rows -- migration not applied'}), 500
    return jsonify({'Success': True, 'Data': Rows[0]}), 200


# directive: transcode-flow-canonical | # see video-encoding.C2
@VideoEncodingBlueprint.route('/Rules', methods=['PUT'])
def UpdateRules():
    Body = request.get_json(silent=True) or {}
    Codecs = (Body.get('AcceptableVideoCodecsCsv') or '').strip()
    if not Codecs:
        return jsonify({'Success': False, 'Message': 'AcceptableVideoCodecsCsv is required'}), 400
    _Db.ExecuteNonQuery(
        "UPDATE VideoComplianceRules SET AcceptableVideoCodecsCsv = %s, LastUpdated = NOW() WHERE Id = (SELECT Id FROM VideoComplianceRules ORDER BY Id LIMIT 1)",
        (Codecs,),
    )
    LoggingService.LogInfo(f"VideoComplianceRules updated: codecs={Codecs!r}", 'VideoEncodingController', 'UpdateRules')
    _SpawnBackfill('Video')
    return jsonify({'Success': True, 'Message': 'Saved; library recompute kicked off in background.'}), 200


# directive: worker-runtime-state
@VideoEncodingBlueprint.route('/BackfillStatus', methods=['GET'])
def GetBackfillStatus():
    return jsonify({'Success': True, 'Data': dict(_BackfillStatus)}), 200


# directive: worker-runtime-state
def _SpawnBackfill(Which: str):
    import threading
    def _Run():
        Status = _BackfillStatus
        Status['Running'] = True
        Status['Completed'] = 0
        Status['StartedAt'] = time.strftime('%Y-%m-%dT%H:%M:%S')
        Status['FinishedAt'] = None
        Status['DurationSec'] = None
        Status['LastError'] = None
        StartedAt = time.time()
        try:
            Rows = DatabaseService().ExecuteQuery("SELECT Id FROM MediaFiles")
            Ids = [int(R['Id'] if 'Id' in R else R['id']) for R in (Rows or [])]
            Status['Total'] = len(Ids)
            if Which == 'Video':
                from Features.VideoEncoding.VideoVertical import VideoVertical
                Vertical = VideoVertical()
            else:
                from Features.ContainerFormat.ContainerVertical import ContainerVertical
                Vertical = ContainerVertical()
            ChunkSize = 500
            for I in range(0, len(Ids), ChunkSize):
                Vertical.RecomputeFor(Ids[I:I + ChunkSize])
                Status['Completed'] = min(I + ChunkSize, len(Ids))
            Status['FinishedAt'] = time.strftime('%Y-%m-%dT%H:%M:%S')
            Status['DurationSec'] = round(time.time() - StartedAt, 2)
            LoggingService.LogInfo(f"{Which}Vertical backfill complete for {len(Ids)} files in {Status['DurationSec']}s", 'ComplianceRulesUpdated', '_SpawnBackfill')
        except Exception as Ex:
            Status['LastError'] = str(Ex)
            LoggingService.LogException(f"{Which}Vertical backfill failed", Ex, 'ComplianceRulesUpdated', '_SpawnBackfill')
        finally:
            Status['Running'] = False
    threading.Thread(target=_Run, daemon=True, name=f'{Which}Backfill').start()
