"""AudioFixPriorityHintsController -- folder-pin CRUD for the Audio Fix tab.

Pins persist in the AudioFixPriorityHints table. When a queue row is created
with ProcessingMode='AudioFix' AND its FilePath matches a pin's
FolderPattern, the row's Priority is boosted to BoostedPriority (default 195).

See media-tabs-and-loudness.feature.md criteria 21-22.
"""

from flask import Blueprint, request, jsonify

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


AudioFixPriorityHintsBlueprint = Blueprint(
    'AudioFixPriorityHints', __name__, url_prefix='/api/AudioFixPriorityHints'
)


@AudioFixPriorityHintsBlueprint.route('/List', methods=['GET'])
def ListPins():
    """Return all pins ordered most-recent first."""
    try:
        Rows = DatabaseService().ExecuteQuery(
            """
            SELECT Id, FolderPattern, BoostedPriority, CreatedAt, Description
            FROM AudioFixPriorityHints
            ORDER BY CreatedAt DESC
            """
        )
        # Normalize datetime to ISO string for JSON
        Data = [dict(R) for R in Rows]
        for D in Data:
            if D.get('CreatedAt') is not None:
                D['CreatedAt'] = D['CreatedAt'].isoformat()
        return jsonify({'Success': True, 'Data': Data})
    except Exception as Ex:
        LoggingService.LogException(
            "ListPins failed", Ex, "AudioFixPriorityHintsController", "ListPins",
        )
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@AudioFixPriorityHintsBlueprint.route('/Add', methods=['POST'])
def AddPin():
    """Add a folder pin. Body: {FolderPattern, BoostedPriority?, Description?}.

    FolderPattern is a substring matched against MediaFiles.FilePath. Bare
    folder names ('Westworld') work; absolute prefixes ('T:\\Show\\') work too.
    """
    Data = request.get_json(silent=True) or {}
    Pattern = (Data.get('FolderPattern') or '').strip()
    if not Pattern:
        return jsonify({'Success': False, 'Message': 'FolderPattern is required'}), 400

    Boost = Data.get('BoostedPriority', 195)
    try:
        Boost = int(Boost)
    except (TypeError, ValueError):
        return jsonify({'Success': False, 'Message': 'BoostedPriority must be an integer'}), 400
    if Boost < 195 or Boost > 200:
        return jsonify({'Success': False, 'Message': 'BoostedPriority must be 195-200'}), 400

    Description = (Data.get('Description') or '').strip() or None

    try:
        Db = DatabaseService()
        Conn = Db.GetConnection()
        try:
            Cur = Conn.cursor()
            Cur.execute(
                """
                INSERT INTO AudioFixPriorityHints (FolderPattern, BoostedPriority, Description)
                VALUES (%s, %s, %s)
                ON CONFLICT (FolderPattern) DO UPDATE
                    SET BoostedPriority = EXCLUDED.BoostedPriority,
                        Description = EXCLUDED.Description
                RETURNING Id
                """,
                (Pattern, Boost, Description),
            )
            NewId = Cur.fetchone()[0]
            Conn.commit()
        finally:
            Db.CloseConnection(Conn)
        LoggingService.LogInfo(
            f"AudioFixPriorityHint added: '{Pattern}' boost={Boost}",
            "AudioFixPriorityHintsController", "AddPin",
        )
        return jsonify({'Success': True, 'Id': NewId, 'FolderPattern': Pattern, 'BoostedPriority': Boost})
    except Exception as Ex:
        LoggingService.LogException(
            "AddPin failed", Ex, "AudioFixPriorityHintsController", "AddPin",
        )
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@AudioFixPriorityHintsBlueprint.route('/Remove/<int:HintId>', methods=['DELETE'])
def RemovePin(HintId):
    """Delete a single pin by Id."""
    try:
        Db = DatabaseService()
        Conn = Db.GetConnection()
        try:
            Cur = Conn.cursor()
            Cur.execute("DELETE FROM AudioFixPriorityHints WHERE Id = %s", (HintId,))
            Removed = Cur.rowcount
            Conn.commit()
        finally:
            Db.CloseConnection(Conn)
        return jsonify({'Success': True, 'Removed': Removed})
    except Exception as Ex:
        LoggingService.LogException(
            "RemovePin failed", Ex, "AudioFixPriorityHintsController", "RemovePin",
        )
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@AudioFixPriorityHintsBlueprint.route('/ApplyAll', methods=['POST'])
def ApplyAll():
    """Re-apply all pins to existing TranscodeQueue rows.

    Useful after adding/removing pins to backfill the priority boost on
    rows that were inserted before the pin was added. UPDATE only touches
    rows with ProcessingMode='AudioFix' whose FilePath matches a pin.
    """
    try:
        Db = DatabaseService()
        Conn = Db.GetConnection()
        try:
            Cur = Conn.cursor()
            Cur.execute(
                """
                UPDATE TranscodeQueue tq
                SET Priority = h.BoostedPriority
                FROM AudioFixPriorityHints h
                WHERE tq.ProcessingMode = 'AudioFix'
                  AND POSITION(h.FolderPattern IN tq.FilePath) > 0
                  AND tq.Priority < h.BoostedPriority
                """
            )
            Boosted = Cur.rowcount
            Conn.commit()
        finally:
            Db.CloseConnection(Conn)
        LoggingService.LogInfo(
            f"AudioFix pin re-apply boosted {Boosted} queue rows",
            "AudioFixPriorityHintsController", "ApplyAll",
        )
        return jsonify({'Success': True, 'Boosted': Boosted})
    except Exception as Ex:
        LoggingService.LogException(
            "ApplyAll failed", Ex, "AudioFixPriorityHintsController", "ApplyAll",
        )
        return jsonify({'Success': False, 'Message': str(Ex)}), 500
