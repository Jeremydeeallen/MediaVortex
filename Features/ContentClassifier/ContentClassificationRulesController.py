# directive: tv-tier1-classifier-pin | # see classifier.feature.md W1
from flask import Blueprint, request, jsonify

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


_EDITABLE_FIELDS = (
    'Priority', 'RuleName', 'IsActive', 'AssignProfileName',
    'BitrateKbpsMin', 'BitrateKbpsMax', 'ResolutionCategory', 'CodecIn',
    'FolderPathPattern', 'Description',
)


# directive: tv-tier1-classifier-pin
def _RowToDict(R):
    return {
        'Id': R.get('Id'),
        'Priority': R.get('Priority'),
        'RuleName': R.get('RuleName'),
        'IsActive': bool(R.get('IsActive')) if R.get('IsActive') is not None else None,
        'AssignProfileName': R.get('AssignProfileName'),
        'BitrateKbpsMin': R.get('BitrateKbpsMin'),
        'BitrateKbpsMax': R.get('BitrateKbpsMax'),
        'ResolutionCategory': R.get('ResolutionCategory'),
        'CodecIn': R.get('CodecIn'),
        'FolderPathPattern': R.get('FolderPathPattern'),
        'Description': R.get('Description'),
    }


# directive: tv-tier1-classifier-pin
def _ValidatePayload(Payload):
    if not isinstance(Payload, dict):
        return None, 'body must be a JSON object'
    Cleaned = {}
    for Field in _EDITABLE_FIELDS:
        if Field in Payload:
            Cleaned[Field] = Payload[Field]
    if 'Priority' in Cleaned and Cleaned['Priority'] is not None:
        try:
            Cleaned['Priority'] = int(Cleaned['Priority'])
        except (TypeError, ValueError):
            return None, 'Priority must be an integer'
    if 'IsActive' in Cleaned and Cleaned['IsActive'] is not None:
        Cleaned['IsActive'] = bool(Cleaned['IsActive'])
    for Field in ('BitrateKbpsMin', 'BitrateKbpsMax'):
        V = Cleaned.get(Field)
        if V is None or V == '':
            Cleaned[Field] = None
        else:
            try:
                Cleaned[Field] = int(V)
            except (TypeError, ValueError):
                return None, f'{Field} must be an integer or null'
    for Field in ('FolderPathPattern', 'ResolutionCategory', 'CodecIn', 'Description'):
        V = Cleaned.get(Field)
        if V == '':
            Cleaned[Field] = None
    return Cleaned, None


ContentClassificationRulesBlueprint = Blueprint(
    'ContentClassificationRules', __name__, url_prefix='/api/ContentClassification/Rules'
)


# directive: tv-tier1-classifier-pin
@ContentClassificationRulesBlueprint.route('', methods=['GET'])
@ContentClassificationRulesBlueprint.route('/', methods=['GET'])
def ListRules():
    try:
        Db = DatabaseService()
        Rows = Db.ExecuteQuery(
            "SELECT Id, Priority, RuleName, IsActive, AssignProfileName, "
            "       BitrateKbpsMin, BitrateKbpsMax, ResolutionCategory, CodecIn, "
            "       FolderPathPattern, Description "
            "  FROM ContentClassificationRules "
            "ORDER BY Priority ASC, Id ASC",
            (),
        )
        return jsonify({'Success': True, 'Data': [_RowToDict(R) for R in (Rows or [])]})
    except Exception as Ex:
        LoggingService.LogException("ListRules failed", Ex, 'ContentClassificationRulesController', 'ListRules')
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


# directive: tv-tier1-classifier-pin
@ContentClassificationRulesBlueprint.route('', methods=['POST'])
@ContentClassificationRulesBlueprint.route('/', methods=['POST'])
def CreateRule():
    Payload, Err = _ValidatePayload(request.get_json(silent=True) or {})
    if Err:
        return jsonify({'Success': False, 'Message': Err}), 400
    if 'Priority' not in Payload or Payload['Priority'] is None:
        return jsonify({'Success': False, 'Message': 'Priority required'}), 400
    if 'RuleName' not in Payload or not Payload.get('RuleName'):
        return jsonify({'Success': False, 'Message': 'RuleName required'}), 400
    try:
        Db = DatabaseService()
        Rows = Db.ExecuteReturning(
            "INSERT INTO ContentClassificationRules "
            "  (Priority, RuleName, IsActive, AssignProfileName, "
            "   BitrateKbpsMin, BitrateKbpsMax, ResolutionCategory, CodecIn, "
            "   FolderPathPattern, Description) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (Priority) DO NOTHING "
            "RETURNING Id",
            (
                Payload['Priority'], Payload['RuleName'],
                Payload.get('IsActive', True), Payload.get('AssignProfileName'),
                Payload.get('BitrateKbpsMin'), Payload.get('BitrateKbpsMax'),
                Payload.get('ResolutionCategory'), Payload.get('CodecIn'),
                Payload.get('FolderPathPattern'), Payload.get('Description'),
            ),
        )
        if not Rows:
            return jsonify({'Success': False, 'Message': f"Priority {Payload['Priority']} already in use"}), 409
        return jsonify({'Success': True, 'Data': {'Id': Rows[0].get('Id')}}), 201
    except Exception as Ex:
        LoggingService.LogException("CreateRule failed", Ex, 'ContentClassificationRulesController', 'CreateRule')
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


# directive: tv-tier1-classifier-pin
@ContentClassificationRulesBlueprint.route('/<int:RuleId>', methods=['PUT'])
def UpdateRule(RuleId: int):
    Payload, Err = _ValidatePayload(request.get_json(silent=True) or {})
    if Err:
        return jsonify({'Success': False, 'Message': Err}), 400
    if not Payload:
        return jsonify({'Success': False, 'Message': 'no editable fields in body'}), 400
    Sets = []
    Params = []
    for Field, Value in Payload.items():
        Sets.append(f"{Field} = %s")
        Params.append(Value)
    Params.append(RuleId)
    try:
        Db = DatabaseService()
        Rows = Db.ExecuteReturning(
            "UPDATE ContentClassificationRules SET " + ", ".join(Sets) + " WHERE Id = %s RETURNING Id",
            tuple(Params),
        )
        if not Rows:
            return jsonify({'Success': False, 'Message': f'RuleId {RuleId} not found'}), 404
        return jsonify({'Success': True, 'Data': {'Id': RuleId}})
    except Exception as Ex:
        LoggingService.LogException("UpdateRule failed", Ex, 'ContentClassificationRulesController', 'UpdateRule')
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


# directive: tv-tier1-classifier-pin
@ContentClassificationRulesBlueprint.route('/<int:RuleId>', methods=['DELETE'])
def DeleteRule(RuleId: int):
    try:
        Db = DatabaseService()
        Rows = Db.ExecuteReturning(
            "DELETE FROM ContentClassificationRules WHERE Id = %s RETURNING Id",
            (RuleId,),
        )
        if not Rows:
            return jsonify({'Success': False, 'Message': f'RuleId {RuleId} not found'}), 404
        return jsonify({'Success': True, 'Data': {'Id': RuleId}})
    except Exception as Ex:
        LoggingService.LogException("DeleteRule failed", Ex, 'ContentClassificationRulesController', 'DeleteRule')
        return jsonify({'Success': False, 'Message': str(Ex)}), 500
