from flask import Blueprint, jsonify

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


ActivityBlueprint = Blueprint('Activity', __name__, url_prefix='/api/Activity')


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
        })
    except Exception as Ex:
        LoggingService.LogException(
            "LibraryCompliance endpoint failed", Ex,
            "ActivityController", "LibraryCompliance",
        )
        return jsonify({'Success': False, 'Message': str(Ex)}), 500
