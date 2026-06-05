from typing import List, Optional, Tuple

from flask import Blueprint, request, jsonify
from Features.MediaProbe.MediaProbeViewModel import MediaProbeViewModel
from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern
from Core.Logging.LoggingService import LoggingService
from Core.Path.Path import Path, PathError
from Core.Path.PathStorageRoots import GetStorageRoots


MediaProbeBlueprint = Blueprint('MediaProbe', __name__, url_prefix='/api/MediaProbe')

_ViewModel = MediaProbeViewModel()


# directive: path-schema-migration | # see path.S8
def _BuildReprobeWhere(Data: dict) -> Tuple[Optional[str], list, Optional[str]]:
    """Translate the request body into a typed-pair WHERE for MediaFiles; returns (WhereSql, Params, ErrorMessage)."""
    if not Data:
        return None, [], 'Request body required (JSON)'
    RawIds = Data.get('MediaFileIds') or []
    ShowFolder = (Data.get('ShowFolder') or '').strip()
    Drive = (Data.get('Drive') or '').strip()
    if not RawIds and not ShowFolder and not Drive:
        return None, [], 'At least one of MediaFileIds, ShowFolder, or Drive is required'

    Clauses, Params = [], []
    if RawIds:
        try:
            Ids = [int(x) for x in RawIds]
        except (TypeError, ValueError):
            return None, [], 'MediaFileIds must be integers'
        Clauses.append('Id = ANY(%s)')
        Params.append(Ids)
    if ShowFolder:
        try:
            Parsed = Path.FromLegacyString(ShowFolder, GetStorageRoots())
        except PathError:
            return None, [], 'ShowFolder did not match any StorageRoot prefix; expected canonical-shaped path (e.g. T:\\Show)'
        Clauses.append("StorageRootId = %s AND RelativePath LIKE %s ESCAPE '!'")
        Params.append(Parsed.StorageRootId)
        Params.append(EscapeLikePattern(Parsed.RelativePath) + '%')
    if Drive:
        Clauses.append("StorageRootId = (SELECT Id FROM StorageRoots WHERE CanonicalPrefix LIKE %s ESCAPE '!' LIMIT 1)")
        Params.append(EscapeLikePattern(Drive) + '%')
    return ' AND '.join(Clauses), Params, None


@MediaProbeBlueprint.route('/Reprobe', methods=['POST'])
def QueueReprobe():
    """Flag matching MediaFiles for reprobe. Body: MediaFileIds[] / ShowFolder / Drive.

    At least one filter required. Sets NeedsReprobe=TRUE; the existing batch
    probe loop picks these up regardless of whether other metadata columns
    are populated.
    """
    Data = request.get_json(silent=True) or {}
    Where, Params, Err = _BuildReprobeWhere(Data)
    if Err:
        return jsonify({'Success': False, 'Message': Err}), 400
    try:
        Db = DatabaseService()
        Conn = Db.GetConnection()
        try:
            Cur = Conn.cursor()
            Cur.execute(
                f"UPDATE MediaFiles SET NeedsReprobe = TRUE WHERE {Where} AND NeedsReprobe = FALSE",
                tuple(Params),
            )
            Queued = Cur.rowcount
            Conn.commit()
        finally:
            Db.CloseConnection(Conn)
        LoggingService.LogInfo(
            f"QueueReprobe: {Queued} rows flagged (filters: {list(Data.keys())})",
            "MediaProbeController", "QueueReprobe",
        )
        return jsonify({'Success': True, 'Queued': Queued})
    except Exception as Ex:
        LoggingService.LogException(
            "QueueReprobe failed", Ex, "MediaProbeController", "QueueReprobe",
        )
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@MediaProbeBlueprint.route('/Reprobe', methods=['DELETE'])
def CancelReprobe():
    """Clear the NeedsReprobe flag for matching MediaFiles (cancellation).

    Same body shape as POST. Files already in flight (claimed by the probe
    loop) finish naturally -- this just stops *new* claims for the scope.
    """
    Data = request.get_json(silent=True) or {}
    Where, Params, Err = _BuildReprobeWhere(Data)
    if Err:
        return jsonify({'Success': False, 'Message': Err}), 400
    try:
        Db = DatabaseService()
        Conn = Db.GetConnection()
        try:
            Cur = Conn.cursor()
            Cur.execute(
                f"UPDATE MediaFiles SET NeedsReprobe = FALSE WHERE {Where} AND NeedsReprobe = TRUE",
                tuple(Params),
            )
            Cancelled = Cur.rowcount
            Conn.commit()
        finally:
            Db.CloseConnection(Conn)
        LoggingService.LogInfo(
            f"CancelReprobe: {Cancelled} rows cleared (filters: {list(Data.keys())})",
            "MediaProbeController", "CancelReprobe",
        )
        return jsonify({'Success': True, 'Cancelled': Cancelled})
    except Exception as Ex:
        LoggingService.LogException(
            "CancelReprobe failed", Ex, "MediaProbeController", "CancelReprobe",
        )
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@MediaProbeBlueprint.route('/ReprobeQueueStatus', methods=['GET'])
def ReprobeQueueStatus():
    """Counts: pending reprobes, files that have measured loudness, etc."""
    try:
        Rows = DatabaseService().ExecuteQuery(
            """
            SELECT
              SUM(CASE WHEN NeedsReprobe = TRUE THEN 1 ELSE 0 END) AS Pending,
              SUM(CASE WHEN LoudnessMeasuredAt IS NOT NULL THEN 1 ELSE 0 END) AS LoudnessMeasured,
              SUM(CASE WHEN LoudnessMeasuredAt IS NOT NULL AND SourceIntegratedLufs IS NULL THEN 1 ELSE 0 END) AS LoudnessFailed,
              COUNT(*) AS Total
            FROM MediaFiles
            """
        )
        return jsonify({'Success': True, 'Data': dict(Rows[0]) if Rows else {}})
    except Exception as Ex:
        LoggingService.LogException(
            "ReprobeQueueStatus failed", Ex, "MediaProbeController", "ReprobeQueueStatus",
        )
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@MediaProbeBlueprint.route('/Probe/<int:MediaFileId>', methods=['POST'])
def ProbeFile(MediaFileId):
    """Probe a single file by ID. Optional JSON body: {"Force": true}."""
    try:
        Force = False
        Data = request.get_json(silent=True)
        if Data:
            Force = Data.get('Force', False)

        Result = _ViewModel.ProbeFile(MediaFileId, Force)
        StatusCode = 200 if Result.get('Success') else 400
        return jsonify(Result), StatusCode

    except Exception as Ex:
        LoggingService.LogException("Error in ProbeFile endpoint", Ex, "MediaProbeController", "ProbeFile")
        return jsonify({'Success': False, 'Message': f'Error: {str(Ex)}'}), 500


@MediaProbeBlueprint.route('/ProbeAll', methods=['POST'])
def ProbeAll():
    """Probe all files needing metadata. Optional JSON body: {"RootFolderId": 1}."""
    try:
        RootFolderId = None
        Data = request.get_json(silent=True)
        if Data:
            RootFolderId = Data.get('RootFolderId')

        Result = _ViewModel.ProbeFilesNeedingMetadata(RootFolderId)
        return jsonify(Result), 200

    except Exception as Ex:
        LoggingService.LogException("Error in ProbeAll endpoint", Ex, "MediaProbeController", "ProbeAll")
        return jsonify({'Success': False, 'Message': f'Error: {str(Ex)}'}), 500


@MediaProbeBlueprint.route('/Statistics', methods=['GET'])
def GetStatistics():
    """Get probe status statistics."""
    try:
        Result = _ViewModel.GetProbeStatistics()
        return jsonify(Result), 200
    except Exception as Ex:
        LoggingService.LogException("Error in GetStatistics endpoint", Ex, "MediaProbeController", "GetStatistics")
        return jsonify({'Success': False, 'Message': f'Error: {str(Ex)}'}), 500


@MediaProbeBlueprint.route('/Failed', methods=['GET'])
def GetFailedFiles():
    """Get list of permanently failed files."""
    try:
        Result = _ViewModel.GetFailedFiles()
        return jsonify(Result), 200
    except Exception as Ex:
        LoggingService.LogException("Error in GetFailedFiles endpoint", Ex, "MediaProbeController", "GetFailedFiles")
        return jsonify({'Success': False, 'Message': f'Error: {str(Ex)}'}), 500


@MediaProbeBlueprint.route('/ResetFailures/<int:MediaFileId>', methods=['POST'])
def ResetFailures(MediaFileId):
    """Reset probe failures for a single file so it can be retried."""
    try:
        Result = _ViewModel.ResetFailures(MediaFileId)
        StatusCode = 200 if Result.get('Success') else 400
        return jsonify(Result), StatusCode
    except Exception as Ex:
        LoggingService.LogException("Error in ResetFailures endpoint", Ex, "MediaProbeController", "ResetFailures")
        return jsonify({'Success': False, 'Message': f'Error: {str(Ex)}'}), 500


@MediaProbeBlueprint.route('/ResetAllFailures', methods=['POST'])
def ResetAllFailures():
    """Reset probe failures for all files."""
    try:
        Result = _ViewModel.ResetAllFailures()
        return jsonify(Result), 200
    except Exception as Ex:
        LoggingService.LogException("Error in ResetAllFailures endpoint", Ex, "MediaProbeController", "ResetAllFailures")
        return jsonify({'Success': False, 'Message': f'Error: {str(Ex)}'}), 500
