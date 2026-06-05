"""AudioCompletionController -- admin endpoints for AudioComplete state.

Two symmetric POST endpoints:
  - /api/AudioCompletion/Reset       -- force re-normalize on next encode
  - /api/AudioCompletion/MarkComplete -- force trust-the-source, no normalize

Both accept the same scoping body: MediaFileIds[], ShowFolder, Drive.
At least one filter is required (refuses unbounded library-wide calls).

See audio-completion.feature.md criterion 19.
"""

from typing import List, Optional, Tuple

from flask import Blueprint, request, jsonify

from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern
from Core.Logging.LoggingService import LoggingService


AudioCompletionBlueprint = Blueprint(
    'AudioCompletion', __name__, url_prefix='/api/AudioCompletion'
)


def _ResolveMediaFileIds(Data: dict) -> Tuple[List[int], Optional[str]]:
    """Translate the request body into a concrete MediaFileIds list.

    Accepts at least one of:
      - MediaFileIds: List[int]
      - ShowFolder: str  (matches MediaFiles.FilePath via LIKE)
      - Drive: str       (matches MediaFiles.FilePath prefix via LIKE)

    Returns (Ids, ErrorMessage). On error, Ids is [] and ErrorMessage is set.
    """
    if not Data:
        return ([], "Request body required (JSON)")

    RawIds = Data.get('MediaFileIds') or []
    ShowFolder = (Data.get('ShowFolder') or '').strip()
    Drive = (Data.get('Drive') or '').strip()

    if not RawIds and not ShowFolder and not Drive:
        return ([], "At least one of MediaFileIds, ShowFolder, or Drive is required")

    if RawIds:
        try:
            ParsedIds = [int(x) for x in RawIds]
        except (TypeError, ValueError):
            return ([], "MediaFileIds must be a list of integers")
        return (ParsedIds, None)

    # directive: path-schema-migration | # see audio-completion.C19
    from Core.Path.Path import Path as _PathAC, PathError as _PEAC
    from Core.Path.PathStorageRoots import GetStorageRoots as _GSRAC
    Filters = []
    Params: List = []
    if ShowFolder:
        try:
            Parsed = _PathAC.FromLegacyString(ShowFolder, _GSRAC())
        except _PEAC:
            return ([], f"ShowFolder did not match any StorageRoot prefix: {ShowFolder!r}")
        Filters.append("(StorageRootId = %s AND RelativePath LIKE %s ESCAPE '!')")
        Params.append(Parsed.StorageRootId)
        Params.append(EscapeLikePattern(Parsed.RelativePath) + "%")
    if Drive:
        Escaped = EscapeLikePattern(Drive)
        Filters.append("StorageRootId = (SELECT Id FROM StorageRoots WHERE CanonicalPrefix LIKE %s ESCAPE '!' LIMIT 1)")
        Params.append(f"{Escaped}%")

    Where = " AND ".join(Filters)
    try:
        Rows = DatabaseService().ExecuteQuery(
            f"SELECT Id FROM MediaFiles WHERE {Where}",
            tuple(Params),
        )
        return ([int(R['Id']) for R in Rows], None)
    except Exception as Ex:
        LoggingService.LogException(
            "Failed to resolve MediaFileIds from scope filter",
            Ex, "AudioCompletionController", "_ResolveMediaFileIds",
        )
        return ([], f"Failed to resolve scope: {Ex}")


@AudioCompletionBlueprint.route('/Reset', methods=['POST'])
def Reset():
    """Force re-normalize on next encode for the matched rows.

    Sets AudioComplete=false, AudioCompletedAt=NULL, AudioCorruptReason=NULL
    where AudioCorruptSuspect=false. Suspect rows are left alone -- they
    require a separate code path to clear.
    """
    Data = request.get_json(silent=True) or {}
    Ids, Err = _ResolveMediaFileIds(Data)
    if Err:
        return jsonify({'Success': False, 'Message': Err}), 400
    if not Ids:
        return jsonify({'Success': True, 'Message': 'No matching rows', 'RowsAffected': 0})

    try:
        Db = DatabaseService()
        Conn = Db.GetConnection()
        try:
            Cur = Conn.cursor()
            Cur.execute(
                """
                UPDATE MediaFiles
                SET AudioComplete = FALSE,
                    AudioCompletedAt = NULL,
                    AudioCorruptReason = NULL
                WHERE Id = ANY(%s)
                  AND AudioCorruptSuspect = FALSE
                """,
                (Ids,),
            )
            RowsAffected = Cur.rowcount
            Conn.commit()
        finally:
            Db.CloseConnection(Conn)

        LoggingService.LogInfo(
            f"AudioCompletion/Reset: scope={len(Ids)} ids, RowsAffected={RowsAffected}",
            "AudioCompletionController", "Reset",
        )
        return jsonify({'Success': True, 'RowsAffected': RowsAffected})
    except Exception as Ex:
        LoggingService.LogException(
            "AudioCompletion/Reset failed", Ex,
            "AudioCompletionController", "Reset",
        )
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@AudioCompletionBlueprint.route('/MarkComplete', methods=['POST'])
def MarkComplete():
    """Force trust-the-source -- no normalize pass will ever run.

    Sets AudioComplete=true, AudioCompletedAt=NOW() for matched rows where
    AudioCorruptSuspect=false. Use for carefully-mastered imports (Blu-ray
    rips, etc.) the operator wants to skip the one-shot normalize pass.
    """
    Data = request.get_json(silent=True) or {}
    Ids, Err = _ResolveMediaFileIds(Data)
    if Err:
        return jsonify({'Success': False, 'Message': Err}), 400
    if not Ids:
        return jsonify({'Success': True, 'Message': 'No matching rows', 'RowsAffected': 0})

    try:
        Db = DatabaseService()
        Conn = Db.GetConnection()
        try:
            Cur = Conn.cursor()
            Cur.execute(
                """
                UPDATE MediaFiles
                SET AudioComplete = TRUE,
                    AudioCompletedAt = NOW()
                WHERE Id = ANY(%s)
                  AND AudioCorruptSuspect = FALSE
                """,
                (Ids,),
            )
            RowsAffected = Cur.rowcount
            Conn.commit()
        finally:
            Db.CloseConnection(Conn)

        LoggingService.LogInfo(
            f"AudioCompletion/MarkComplete: scope={len(Ids)} ids, RowsAffected={RowsAffected}",
            "AudioCompletionController", "MarkComplete",
        )
        return jsonify({'Success': True, 'RowsAffected': RowsAffected})
    except Exception as Ex:
        LoggingService.LogException(
            "AudioCompletion/MarkComplete failed", Ex,
            "AudioCompletionController", "MarkComplete",
        )
        return jsonify({'Success': False, 'Message': str(Ex)}), 500
