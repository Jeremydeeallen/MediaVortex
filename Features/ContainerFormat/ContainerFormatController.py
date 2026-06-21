from flask import Blueprint, jsonify, request

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


ContainerFormatBlueprint = Blueprint('ContainerFormat', __name__, url_prefix='/api/ContainerFormat')

_Db = DatabaseService()


# directive: compliance-tabbed-ui
@ContainerFormatBlueprint.route('/Rules', methods=['GET'])
def GetRules():
    Rows = _Db.ExecuteQuery(
        "SELECT Id, AcceptableContainersCsv, AcceptableAudioCodecsCsv, LastUpdated "
        "FROM ContainerComplianceRules ORDER BY Id LIMIT 1"
    )
    if not Rows:
        return jsonify({'Success': False, 'Message': 'ContainerComplianceRules has no rows -- migration not applied'}), 500
    return jsonify({'Success': True, 'Data': Rows[0]}), 200


# directive: compliance-tabbed-ui
@ContainerFormatBlueprint.route('/Rules', methods=['PUT'])
def UpdateRules():
    Body = request.get_json(silent=True) or {}
    Containers = (Body.get('AcceptableContainersCsv') or '').strip()
    AudioCodecs = (Body.get('AcceptableAudioCodecsCsv') or '').strip()
    if not Containers:
        return jsonify({'Success': False, 'Message': 'AcceptableContainersCsv is required'}), 400
    if not AudioCodecs:
        return jsonify({'Success': False, 'Message': 'AcceptableAudioCodecsCsv is required'}), 400
    _Db.ExecuteNonQuery(
        "UPDATE ContainerComplianceRules SET AcceptableContainersCsv = %s, AcceptableAudioCodecsCsv = %s, LastUpdated = NOW() WHERE Id = (SELECT Id FROM ContainerComplianceRules ORDER BY Id LIMIT 1)",
        (Containers, AudioCodecs),
    )
    LoggingService.LogInfo(f"ContainerComplianceRules updated: containers={Containers!r} audio={AudioCodecs!r}", 'ContainerFormatController', 'UpdateRules')
    return jsonify({'Success': True, 'Message': 'Saved'}), 200
