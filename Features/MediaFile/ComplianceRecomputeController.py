from flask import Blueprint, jsonify, request

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService


ComplianceRecomputeBlueprint = Blueprint('compliance_recompute', __name__)


# directive: transcode-flow-canonical -- C33
BATCH_SIZE = 500


# directive: transcode-flow-canonical -- C33
def _FetchIds(Db, ProfileName, StorageRootId, Limit):
    Wheres = []
    Args = []
    if ProfileName:
        Wheres.append("AssignedProfile = %s")
        Args.append(ProfileName)
    if StorageRootId is not None:
        Wheres.append("StorageRootId = %s")
        Args.append(int(StorageRootId))
    WhereClause = ("WHERE " + " AND ".join(Wheres)) if Wheres else ""
    LimitClause = f"LIMIT {int(Limit)}" if Limit else ""
    Sql = f"SELECT Id FROM MediaFiles {WhereClause} ORDER BY Id ASC {LimitClause}"
    Rows = Db.ExecuteQuery(Sql, tuple(Args))
    return [int(R['id']) for R in Rows]


# directive: transcode-flow-canonical -- C33
def _SnapshotBuckets(Db, Ids):
    if not Ids:
        return {}
    Placeholders = ",".join(["%s"] * len(Ids))
    Rows = Db.ExecuteQuery(
        f"SELECT Id, WorkBucket FROM MediaFiles WHERE Id IN ({Placeholders})",
        tuple(Ids),
    )
    return {int(R['id']): R['workbucket'] for R in Rows}


# directive: transcode-flow-canonical -- C33
@ComplianceRecomputeBlueprint.route('/api/Compliance/Recompute', methods=['POST'])
def recompute_compliance():
    try:
        Body = request.get_json(silent=True) or {}
        ProfileName = Body.get('ProfileName')
        StorageRootId = Body.get('StorageRootId')
        Limit = Body.get('Limit')
        Db = DatabaseService()
        Qmbs = QueueManagementBusinessService()
        Ids = _FetchIds(Db, ProfileName, StorageRootId, Limit)
        Total = len(Ids)
        BucketChanges = {}
        for Start in range(0, Total, BATCH_SIZE):
            Batch = Ids[Start:Start + BATCH_SIZE]
            PreBuckets = _SnapshotBuckets(Db, Batch)
            Qmbs.RecomputeForFiles(Batch)
            PostBuckets = _SnapshotBuckets(Db, Batch)
            for Mid in Batch:
                Pre = PreBuckets.get(Mid)
                Post = PostBuckets.get(Mid)
                if Pre != Post:
                    Key = f"{Pre} -> {Post}"
                    BucketChanges[Key] = BucketChanges.get(Key, 0) + 1
        return jsonify({
            'Success': True,
            'Message': f'Recomputed {Total} MediaFile rows',
            'Data': {
                'Processed': Total,
                'BucketChanges': BucketChanges,
                'Filters': {'ProfileName': ProfileName, 'StorageRootId': StorageRootId, 'Limit': Limit},
            },
        })
    except Exception as Ex:
        LoggingService.LogException("Compliance recompute failed", Ex, "ComplianceRecomputeController", "recompute_compliance")
        return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500
