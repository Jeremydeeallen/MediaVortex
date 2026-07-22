import json
import time
from dataclasses import asdict
from flask import Blueprint, Response, jsonify, stream_with_context

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


ActivityBlueprint = Blueprint('Activity', __name__, url_prefix='/api/Activity')


def _BuildSnapshotPayload():
    def _jsonable(D):
        return {k: (v.isoformat() if hasattr(v, 'isoformat') and v is not None else v) for k, v in D.items()}
    from Features.Activity.Services.DashboardSnapshotService import DashboardSnapshotService
    Snap = DashboardSnapshotService().BuildSnapshot()
    return {
        'ActiveJobs': [_jsonable(asdict(J)) for J in Snap.ActiveJobs],
        'ActiveScans': [_jsonable(S) for S in Snap.ActiveScans],
        'QueueCounts': Snap.QueueCounts,
        'BadgeState': Snap.BadgeState,
        'HungAttempts': [_jsonable(H) for H in Snap.HungAttempts],
        'ActiveQualityTests': [_jsonable(Q) for Q in Snap.ActiveQualityTests],
        'StaleProgressThresholdSec': Snap.StaleProgressThresholdSec,
    }


# directive: transcode-worker-unification
@ActivityBlueprint.route('/Stream', methods=['GET'])
def Stream():
    """SSE push of dashboard snapshots; replaces 5s polling in Templates/Activity.html with EventSource."""
    def _Events():
        LastPayload = None
        while True:
            try:
                Payload = _BuildSnapshotPayload()
            except Exception as Ex:
                LoggingService.LogException("Stream snapshot build failed", Ex, "ActivityController", "Stream")
                yield f": error {str(Ex)[:120]}\n\n"
                time.sleep(5)
                continue
            Serialized = json.dumps(Payload)
            if Serialized != LastPayload:
                yield f"data: {Serialized}\n\n"
                LastPayload = Serialized
            else:
                yield ": keepalive\n\n"
            time.sleep(1.5)
    Headers = {
        'Cache-Control': 'no-store',
        'X-Accel-Buffering': 'no',
    }
    return Response(stream_with_context(_Events()), mimetype='text/event-stream', headers=Headers)


@ActivityBlueprint.route('/Snapshot', methods=['GET'])
# directive: worker-runtime-state | # see activity.C5
def Snapshot():
    """Single dashboard payload -- {ActiveJobs, ActiveScans, QueueCounts, BadgeState, thresholds}."""
    # directive: worker-runtime-state | # see activity.C5
    def _jsonable(D):
        return {k: (v.isoformat() if hasattr(v, 'isoformat') and v is not None else v) for k, v in D.items()}
    try:
        from Features.Activity.Services.DashboardSnapshotService import DashboardSnapshotService
        Snap = DashboardSnapshotService().BuildSnapshot()
        return jsonify({
            'Success': True,
            'Data': {
                'ActiveJobs': [_jsonable(asdict(J)) for J in Snap.ActiveJobs],
                'ActiveScans': [_jsonable(S) for S in Snap.ActiveScans],
                'QueueCounts': Snap.QueueCounts,
                'BadgeState': Snap.BadgeState,
                'HungAttempts': [_jsonable(H) for H in Snap.HungAttempts],
                'ActiveQualityTests': [_jsonable(Q) for Q in Snap.ActiveQualityTests],
                'StaleProgressThresholdSec': Snap.StaleProgressThresholdSec,
            },
        })
    except Exception as Ex:
        LoggingService.LogException("Snapshot endpoint failed", Ex, "ActivityController", "Snapshot")
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


# directive: transcode-worker-unification | # see activity.W5
@ActivityBlueprint.route('/NavBadges', methods=['GET'])
def NavBadges():
    """Single aggregate of every nav-bar badge -- replaces the 4 parallel polls in Base.html."""
    try:
        Db = DatabaseService()
        QueueRow = Db.ExecuteQuery("SELECT COUNT(*)::int AS n FROM TranscodeQueue WHERE Status='Pending'")
        QueueCount = int((QueueRow or [{}])[0].get('n') or 0)
        ActiveRow = Db.ExecuteQuery("SELECT COUNT(*)::int AS n FROM ActiveJobs WHERE Status = 'Running'")
        ActiveJobsCount = int((ActiveRow or [{}])[0].get('n') or 0)
        from Features.FailureAccounting.Repositories.FailedJobsRepository import FailedJobsRepository
        FailedJobsCount = int(FailedJobsRepository(Db).CountCapped())
        from Features.Activity.ActivityRepository import ActivityRepository
        Mode = ActivityRepository().GetWorkBucketBreakdown() or {}
        return jsonify({
            'Success': True,
            'Data': {
                'QueueCount': QueueCount,
                'ActiveJobsCount': ActiveJobsCount,
                'FailedJobsCount': FailedJobsCount,
                'Transcode': int(Mode.get('Transcode') or 0),
                'Remux': int(Mode.get('Remux') or 0),
                'AudioFix': int(Mode.get('AudioFix') or 0),
            },
        })
    except Exception as Ex:
        LoggingService.LogException("NavBadges endpoint failed", Ex, "ActivityController", "NavBadges")
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
