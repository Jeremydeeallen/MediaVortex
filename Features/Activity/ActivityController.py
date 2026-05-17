"""ActivityController -- panel data endpoints for the /Activity page.

Currently exposes:
  - GET /api/Activity/LibraryCompliance -- counts driving the Library
    Compliance panel: compliance state, RecommendedMode breakdown,
    AudioComplete distribution, loudness band distribution.

See media-tabs-and-loudness.feature.md criteria 23-24.
"""

from flask import Blueprint, jsonify

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


ActivityBlueprint = Blueprint('Activity', __name__, url_prefix='/api/Activity')


@ActivityBlueprint.route('/LibraryCompliance', methods=['GET'])
def LibraryCompliance():
    """Aggregate counts for the Library Compliance panel.

    One single SELECT per axis, all cheap GROUP BY queries against MediaFiles.
    No per-row work; intended for live polling on the Activity page.
    """
    try:
        Db = DatabaseService()

        # Compliance breakdown
        ComplianceRows = Db.ExecuteQuery(
            """
            SELECT
              COUNT(*) AS Total,
              SUM(CASE WHEN IsCompliant IS TRUE THEN 1 ELSE 0 END) AS CompliantTrue,
              SUM(CASE WHEN IsCompliant IS FALSE THEN 1 ELSE 0 END) AS CompliantFalse,
              SUM(CASE WHEN IsCompliant IS NULL THEN 1 ELSE 0 END) AS CompliantNull
            FROM MediaFiles
            """
        )
        Compliance = dict(ComplianceRows[0]) if ComplianceRows else {}

        # RecommendedMode breakdown (only for non-compliant rows)
        ModeRows = Db.ExecuteQuery(
            """
            SELECT
              SUM(CASE WHEN RecommendedMode = 'Transcode' THEN 1 ELSE 0 END) AS Transcode,
              SUM(CASE WHEN RecommendedMode = 'Remux' THEN 1 ELSE 0 END) AS Remux,
              SUM(CASE WHEN RecommendedMode = 'AudioFix' THEN 1 ELSE 0 END) AS AudioFix,
              SUM(CASE WHEN RecommendedMode IS NULL AND IsCompliant IS FALSE THEN 1 ELSE 0 END) AS NoMode
            FROM MediaFiles
            WHERE IsCompliant IS FALSE OR RecommendedMode IS NOT NULL
            """
        )
        Mode = dict(ModeRows[0]) if ModeRows else {}

        # AudioComplete + Suspect-by-reason
        AudioRows = Db.ExecuteQuery(
            """
            SELECT
              SUM(CASE WHEN AudioComplete IS TRUE THEN 1 ELSE 0 END) AS AudioTrue,
              SUM(CASE WHEN AudioComplete IS FALSE THEN 1 ELSE 0 END) AS AudioFalse,
              SUM(CASE WHEN AudioComplete IS NULL THEN 1 ELSE 0 END) AS AudioNull
            FROM MediaFiles
            """
        )
        Audio = dict(AudioRows[0]) if AudioRows else {}

        SuspectRows = Db.ExecuteQuery(
            """
            SELECT COALESCE(AudioCorruptReason, 'unspecified') AS Reason, COUNT(*) AS N
            FROM MediaFiles
            WHERE AudioCorruptSuspect = TRUE
            GROUP BY 1
            ORDER BY 2 DESC
            """
        )
        SuspectByReason = {Row['Reason']: Row['N'] for Row in SuspectRows}

        # Loudness band distribution
        # On target: integrated LUFS within +/- 1 of -23
        # Off target (>3 LU off): outside [-26, -20]
        # Wide LRA: SourceLoudnessRangeLU > 18
        LoudnessRows = Db.ExecuteQuery(
            """
            SELECT
              SUM(CASE WHEN LoudnessMeasuredAt IS NOT NULL AND SourceIntegratedLufs IS NOT NULL THEN 1 ELSE 0 END) AS Measured,
              SUM(CASE WHEN LoudnessMeasuredAt IS NULL THEN 1 ELSE 0 END) AS Unmeasured,
              SUM(CASE WHEN SourceIntegratedLufs BETWEEN -24 AND -22 THEN 1 ELSE 0 END) AS OnTarget,
              SUM(CASE WHEN SourceIntegratedLufs IS NOT NULL AND (SourceIntegratedLufs > -20 OR SourceIntegratedLufs < -26) THEN 1 ELSE 0 END) AS OffTarget,
              SUM(CASE WHEN SourceLoudnessRangeLU > 18 THEN 1 ELSE 0 END) AS WideLRA
            FROM MediaFiles
            """
        )
        Loudness = dict(LoudnessRows[0]) if LoudnessRows else {}

        return jsonify({
            'Success': True,
            'Compliance': Compliance,
            'Mode': Mode,
            'Audio': Audio,
            'SuspectByReason': SuspectByReason,
            'Loudness': Loudness
        })
    except Exception as Ex:
        LoggingService.LogException(
            "LibraryCompliance endpoint failed", Ex,
            "ActivityController", "LibraryCompliance",
        )
        return jsonify({'Success': False, 'Message': str(Ex)}), 500
