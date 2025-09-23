from flask import Blueprint, request, jsonify
from ViewModels.FileReplacementViewModel import FileReplacementViewModel
from Services.LoggingService import LoggingService


class FileReplacementController:
    """Controller for file replacement operations."""
    
    def __init__(self, app):
        self.Blueprint = Blueprint('FileReplacement', __name__, url_prefix='/api/FileReplacement')
        self.App = app
        self.FileReplacementViewModel = FileReplacementViewModel()
        self._register_routes()
    
    def _register_routes(self):
        """Register all routes for file replacement operations."""
        
        @self.Blueprint.route('/FailedReplacements', methods=['GET'])
        def GetFailedFileReplacements():
            """Get list of failed file replacements."""
            try:
                LoggingService.LogFunctionEntry("GetFailedFileReplacements", "FileReplacementController")
                
                result = self.FileReplacementViewModel.GetFailedFileReplacements()
                
                if result.get('Success', False):
                    LoggingService.LogInfo(f"Retrieved {result.get('TotalCount', 0)} failed file replacements", 
                                         "FileReplacementController", "GetFailedFileReplacements")
                    return jsonify(result)
                else:
                    LoggingService.LogError(f"Failed to get failed file replacements: {result.get('ErrorMessage', 'Unknown error')}", 
                                          "FileReplacementController", "GetFailedFileReplacements")
                    return jsonify(result), 500
                    
            except Exception as e:
                ErrorMsg = f"Exception getting failed file replacements: {str(e)}"
                LoggingService.LogException(ErrorMsg, e, "FileReplacementController", "GetFailedFileReplacements")
                return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500
        
        @self.Blueprint.route('/Process/<int:transcode_attempt_id>', methods=['POST'])
        def ProcessFileReplacement(transcode_attempt_id):
            """Process file replacement for a specific transcode attempt."""
            try:
                LoggingService.LogFunctionEntry("ProcessFileReplacement", "FileReplacementController", transcode_attempt_id)
                
                result = self.FileReplacementViewModel.ProcessFileReplacement(transcode_attempt_id)
                
                if result.get('Success', False):
                    LoggingService.LogInfo(f"File replacement processed successfully for attempt {transcode_attempt_id}", 
                                         "FileReplacementController", "ProcessFileReplacement")
                    return jsonify(result)
                else:
                    LoggingService.LogError(f"File replacement failed for attempt {transcode_attempt_id}: {result.get('ErrorMessage', 'Unknown error')}", 
                                          "FileReplacementController", "ProcessFileReplacement")
                    return jsonify(result), 400
                    
            except Exception as e:
                ErrorMsg = f"Exception processing file replacement for attempt {transcode_attempt_id}: {str(e)}"
                LoggingService.LogException(ErrorMsg, e, "FileReplacementController", "ProcessFileReplacement")
                return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500
        
        @self.Blueprint.route('/Status/<int:transcode_attempt_id>', methods=['GET'])
        def GetFileReplacementStatus(transcode_attempt_id):
            """Get file replacement status for a specific transcode attempt."""
            try:
                LoggingService.LogFunctionEntry("GetFileReplacementStatus", "FileReplacementController", transcode_attempt_id)
                
                result = self.FileReplacementViewModel.GetFileReplacementStatus(transcode_attempt_id)
                
                if result.get('Success', False):
                    return jsonify(result)
                else:
                    LoggingService.LogError(f"Failed to get file replacement status for attempt {transcode_attempt_id}: {result.get('ErrorMessage', 'Unknown error')}", 
                                          "FileReplacementController", "GetFileReplacementStatus")
                    return jsonify(result), 400
                    
            except Exception as e:
                ErrorMsg = f"Exception getting file replacement status for attempt {transcode_attempt_id}: {str(e)}"
                LoggingService.LogException(ErrorMsg, e, "FileReplacementController", "GetFileReplacementStatus")
                return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500
