from flask import Blueprint, request, jsonify
from Features.Optimization.OptimizationViewModel import OptimizationViewModel
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
from Core.Logging.LoggingService import LoggingService


OptimizationBlueprint = Blueprint('Optimization', __name__, url_prefix='/api/Optimization')


@OptimizationBlueprint.route('/LocalAnalysis', methods=['GET'])
def LocalAnalysis():
    """Get local MediaVortex DB analysis for optimization opportunities."""
    try:
        viewModel = OptimizationViewModel()
        result = viewModel.GetLocalAnalysis()
        if result.get("Success"):
            return jsonify(result)
        else:
            return jsonify(result), 500
    except Exception as e:
        LoggingService.LogException("Exception in LocalAnalysis", e, "OptimizationController", "LocalAnalysis")
        return jsonify({"Success": False, "ErrorMessage": str(e)}), 500


@OptimizationBlueprint.route('/LocalAnalysisDetails', methods=['GET'])
def LocalAnalysisDetails():
    """Get detailed file list for a specific optimization section."""
    try:
        section = request.args.get('section', '')
        limit = int(request.args.get('limit', 100))
        if not section:
            return jsonify({"Success": False, "ErrorMessage": "section parameter is required"}), 400

        viewModel = OptimizationViewModel()
        result = viewModel.GetLocalAnalysisDetails(section, limit)
        if result.get("Success"):
            return jsonify(result)
        else:
            return jsonify(result), 500
    except Exception as e:
        LoggingService.LogException("Exception in LocalAnalysisDetails", e, "OptimizationController", "LocalAnalysisDetails")
        return jsonify({"Success": False, "ErrorMessage": str(e)}), 500


@OptimizationBlueprint.route('/JellyfinAnalysis', methods=['GET'])
def JellyfinAnalysis():
    """Get Jellyfin server analysis from local DB."""
    try:
        viewModel = OptimizationViewModel()
        result = viewModel.GetJellyfinAnalysis()
        if result.get("Success"):
            return jsonify(result)
        else:
            return jsonify(result), 500
    except Exception as e:
        LoggingService.LogException("Exception in JellyfinAnalysis", e, "OptimizationController", "JellyfinAnalysis")
        return jsonify({"Success": False, "ErrorMessage": str(e)}), 500


@OptimizationBlueprint.route('/TestConnection', methods=['POST'])
def TestConnection():
    """Test SSH connection to Jellyfin server."""
    try:
        viewModel = OptimizationViewModel()
        result = viewModel.TestJellyfinConnection()
        if result.get("Success"):
            return jsonify(result)
        else:
            return jsonify(result), 500
    except Exception as e:
        LoggingService.LogException("Exception in TestConnection", e, "OptimizationController", "TestConnection")
        return jsonify({"Success": False, "ErrorMessage": str(e)}), 500


@OptimizationBlueprint.route('/ConnectionSettings', methods=['GET'])
def GetConnectionSettings():
    """Get Jellyfin connection settings."""
    try:
        viewModel = OptimizationViewModel()
        result = viewModel.GetConnectionSettings()
        return jsonify(result)
    except Exception as e:
        LoggingService.LogException("Exception in GetConnectionSettings", e, "OptimizationController", "GetConnectionSettings")
        return jsonify({"Success": False, "ErrorMessage": str(e)}), 500


@OptimizationBlueprint.route('/ConnectionSettings', methods=['POST'])
def SaveConnectionSettings():
    """Save Jellyfin connection settings."""
    try:
        data = request.get_json() or {}
        viewModel = OptimizationViewModel()
        result = viewModel.SaveConnectionSettings(data)
        if result.get("Success"):
            return jsonify(result)
        else:
            return jsonify(result), 500
    except Exception as e:
        LoggingService.LogException("Exception in SaveConnectionSettings", e, "OptimizationController", "SaveConnectionSettings")
        return jsonify({"Success": False, "ErrorMessage": str(e)}), 500


@OptimizationBlueprint.route('/RefreshJellyfin', methods=['POST'])
def RefreshJellyfin():
    """SSH to Jellyfin server, fetch new FFmpeg log entries, store in local DB."""
    try:
        viewModel = OptimizationViewModel()
        result = viewModel.RefreshJellyfinData()
        if result.get("Success"):
            return jsonify(result)
        else:
            return jsonify(result), 500
    except Exception as e:
        LoggingService.LogException("Exception in RefreshJellyfin", e, "OptimizationController", "RefreshJellyfin")
        return jsonify({"Success": False, "ErrorMessage": str(e)}), 500


@OptimizationBlueprint.route('/OperationDetails', methods=['GET'])
def OperationDetails():
    """Get detailed file list for a Jellyfin FFmpeg operation type."""
    try:
        opType = request.args.get('type', '')
        limit = int(request.args.get('limit', 100))
        if opType not in ('DirectStream', 'Transcode', 'Remux'):
            return jsonify({"Success": False, "ErrorMessage": "type must be DirectStream, Transcode, or Remux"}), 400

        viewModel = OptimizationViewModel()
        result = viewModel.GetOperationDetails(opType, limit)
        if result.get("Success"):
            return jsonify(result)
        else:
            return jsonify(result), 500
    except Exception as e:
        LoggingService.LogException("Exception in OperationDetails", e, "OptimizationController", "OperationDetails")
        return jsonify({"Success": False, "ErrorMessage": str(e)}), 500


@OptimizationBlueprint.route('/RecheckFile', methods=['POST'])
def RecheckFile():
    """Re-analyze a file with ffprobe and return updated mitigation status."""
    try:
        data = request.get_json() or {}
        fileName = data.get('FileName', '')
        filePath = data.get('FilePath', '')
        opType = data.get('OperationType', '')
        reason = data.get('Reason', '')
        if not fileName:
            return jsonify({"Success": False, "ErrorMessage": "FileName is required"}), 400

        viewModel = OptimizationViewModel()
        result = viewModel.RecheckFile(fileName, filePath, opType, reason)
        if result.get("Success"):
            return jsonify(result)
        else:
            return jsonify(result), 500
    except Exception as e:
        LoggingService.LogException("Exception in RecheckFile", e, "OptimizationController", "RecheckFile")
        return jsonify({"Success": False, "ErrorMessage": str(e)}), 500


@OptimizationBlueprint.route('/CopyAnalysis', methods=['GET'])
def CopyAnalysis():
    """Get token-optimized text summary for AI analysis."""
    try:
        viewModel = OptimizationViewModel()
        result = viewModel.CopyAnalysisForAI()
        if result.get("Success"):
            return jsonify(result)
        else:
            return jsonify(result), 500
    except Exception as e:
        LoggingService.LogException("Exception in CopyAnalysis", e, "OptimizationController", "CopyAnalysis")
        return jsonify({"Success": False, "ErrorMessage": str(e)}), 500


@OptimizationBlueprint.route('/DeviceAnalysis', methods=['GET'])
def DeviceAnalysis():
    """Get device-level analysis from Jellyfin (devices, playback history, log fields)."""
    try:
        viewModel = OptimizationViewModel()
        result = viewModel.GetDeviceAnalysis()
        if result.get("Success"):
            return jsonify(result)
        else:
            return jsonify(result), 500
    except Exception as e:
        LoggingService.LogException("Exception in DeviceAnalysis", e, "OptimizationController", "DeviceAnalysis")
        return jsonify({"Success": False, "ErrorMessage": str(e)}), 500


@OptimizationBlueprint.route('/QueueSubtitleFix', methods=['POST'])
def QueueSubtitleFix():
    """Queue files for subtitle fix processing (ASS/SSA -> mov_text).
    Body: { "FileIds": [1,2,3] } for specific files, or {} for all eligible."""
    try:
        data = request.get_json() or {}
        fileIds = data.get('FileIds', None)
        service = QueueManagementBusinessService()
        result = service.PopulateQueueForSubtitleFix(fileIds)
        if result.get("Success"):
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:
        LoggingService.LogException("Exception in QueueSubtitleFix", e, "OptimizationController", "QueueSubtitleFix")
        return jsonify({"Success": False, "ErrorMessage": str(e)}), 500
