from flask import Blueprint, request, jsonify
from Features.MediaProbe.MediaProbeViewModel import MediaProbeViewModel
from Core.Logging.LoggingService import LoggingService


MediaProbeBlueprint = Blueprint('MediaProbe', __name__, url_prefix='/api/MediaProbe')

_ViewModel = MediaProbeViewModel()


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
