from dataclasses import asdict
from flask import Blueprint, jsonify

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


ActivityBlueprint = Blueprint('Activity', __name__, url_prefix='/api/Activity')


@ActivityBlueprint.route('/Snapshot', methods=['GET'])
# directive: activity-dashboard-solid | # see activity-dashboard-solid.C1
def Snapshot():
    """Single dashboard payload -- {Workers, ActiveJobs, QueueCounts, BadgeState, thresholds}. One round-trip per /Activity poll."""
    # directive: activity-dashboard-solid | # see activity-dashboard-solid.C1
    def _jsonable(D):
        return {k: (v.isoformat() if hasattr(v, 'isoformat') and v is not None else v) for k, v in D.items()}
    try:
        from Features.Activity.Services.DashboardSnapshotService import DashboardSnapshotService
        Snap = DashboardSnapshotService().BuildSnapshot()
        return jsonify({
            'Success': True,
            'Data': {
                'Workers': [_jsonable(asdict(W)) for W in Snap.Workers],
                'ActiveJobs': [_jsonable(asdict(J)) for J in Snap.ActiveJobs],
                'QueueCounts': Snap.QueueCounts,
                'BadgeState': Snap.BadgeState,
                'StaleProgressThresholdSec': Snap.StaleProgressThresholdSec,
                'HeartbeatStaleThresholdSec': Snap.HeartbeatStaleThresholdSec,
            },
        })
    except Exception as Ex:
        LoggingService.LogException("Snapshot endpoint failed", Ex, "ActivityController", "Snapshot")
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C20
@ActivityBlueprint.route('/LibraryCompliance', methods=['GET'])
def LibraryCompliance():
    """Aggregate counts for the Library Compliance panel -- delegates to ActivityRepository (R12 mandate #2: SQL-in-Repository); Mode breakdown now sources from MediaFiles.WorkBucket per compliance-solid-refactor.C20."""
    try:
        from Features.Activity.ActivityRepository import ActivityRepository
        Repo = ActivityRepository()
        return jsonify({
            'Success': True,
            'Compliance': Repo.GetComplianceBreakdown(),
            'Mode': Repo.GetWorkBucketBreakdown(),
            'Audio': Repo.GetAudioCompleteBreakdown(),
            'SuspectByReason': Repo.GetSuspectByReason(),
            'Loudness': Repo.GetLoudnessBreakdown(),
            'AudioNormalization': Repo.GetAudioNormalizationBreakdown(),
            'AudioConsistencyBands': Repo.GetAudioConsistencyBands(),
        })
    except Exception as Ex:
        LoggingService.LogException(
            "LibraryCompliance endpoint failed", Ex,
            "ActivityController", "LibraryCompliance",
        )
        return jsonify({'Success': False, 'Message': str(Ex)}), 500
