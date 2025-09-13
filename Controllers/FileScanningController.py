from flask import Blueprint, request, jsonify, render_template
from typing import Dict, Any
from ViewModels.FileScanningViewModel import FileScanningViewModel
from Services.DebugService import DebugService


class FileScanningController:
    """Provides REST API endpoints for scanning operations with Unicode character support."""
    
    def __init__(self):
        self.Blueprint = Blueprint('FileScanning', __name__)
        self.ViewModel = FileScanningViewModel()
        self.SetupRoutes()
    
    def SetupRoutes(self):
        """Setup all the API routes."""
        
        @self.Blueprint.route('/Scan/Start', methods=['POST'])
        def StartScan():
            """Start scanning a root folder."""
            try:
                data = request.get_json()
                rootFolderPath = data.get('RootFolderPath', '')
                recursive = data.get('Recursive', True)
                
                if not rootFolderPath:
                    return jsonify({
                        'Success': False,
                        'Message': 'RootFolderPath is required',
                        'Error': 'MissingPath'
                    }), 400
                
                result = self.ViewModel.StartScanning(rootFolderPath, recursive)
                
                if result['Success']:
                    return jsonify(result), 200
                else:
                    return jsonify(result), 400
                    
            except Exception as e:
                DebugService.LogException("Error in StartScan endpoint", e)
                return jsonify({
                    'Success': False,
                    'Message': f'Error starting scan: {str(e)}',
                    'Error': 'StartScanError'
                }), 500
        
        @self.Blueprint.route('/Scan/Status', methods=['GET'])
        def GetScanStatus():
            """Get current scan status and progress."""
            try:
                status = self.ViewModel.UpdateScanStatus()
                return jsonify(status), 200
                
            except Exception as e:
                DebugService.LogException("Error in GetScanStatus endpoint", e)
                return jsonify({
                    'Success': False,
                    'Message': f'Error getting scan status: {str(e)}',
                    'Error': 'StatusError'
                }), 500
        
        @self.Blueprint.route('/Scan/Stop', methods=['POST'])
        def StopScan():
            """Stop the current scan."""
            try:
                result = self.ViewModel.StopScanning()
                
                if result['Success']:
                    return jsonify(result), 200
                else:
                    return jsonify(result), 400
                    
            except Exception as e:
                DebugService.LogException("Error in StopScan endpoint", e)
                return jsonify({
                    'Success': False,
                    'Message': f'Error stopping scan: {str(e)}',
                    'Error': 'StopScanError'
                }), 500
        
        @self.Blueprint.route('/RootFolders', methods=['GET'])
        def GetRootFolders():
            """Get root folders with pagination and filtering."""
            try:
                page = int(request.args.get('Page', 1))
                pageSize = int(request.args.get('PageSize', 10))
                search = request.args.get('Search', '')
                
                result = self.ViewModel.GetRootFoldersPaginated(page, pageSize, search)
                return jsonify({
                    'Success': True,
                    'RootFolders': result['RootFolders'],
                    'TotalCount': result['TotalCount'],
                    'TotalPages': result['TotalPages'],
                    'AllRootFolders': result['AllRootFolders']
                }), 200
                
            except Exception as e:
                DebugService.LogException("Error in GetRootFolders endpoint", e)
                return jsonify({
                    'Success': False,
                    'Message': f'Error getting root folders: {str(e)}',
                    'Error': 'GetRootFoldersError'
                }), 500
        
        @self.Blueprint.route('/RootFolders/<int:RootFolderId>', methods=['DELETE'])
        def DeleteRootFolder(RootFolderId):
            """Delete a root folder."""
            try:
                success = self.ViewModel.DeleteRootFolder(RootFolderId)
                
                if success:
                    return jsonify({
                        'Success': True,
                        'Message': 'Root folder deleted successfully'
                    }), 200
                else:
                    return jsonify({
                        'Success': False,
                        'Message': 'Failed to delete root folder',
                        'Error': 'DeleteRootFolderError'
                    }), 400
                    
            except Exception as e:
                DebugService.LogException("Error in DeleteRootFolder endpoint", e)
                return jsonify({
                    'Success': False,
                    'Message': f'Error deleting root folder: {str(e)}',
                    'Error': 'DeleteRootFolderError'
                }), 500
        
        @self.Blueprint.route('/MediaFiles', methods=['GET'])
        def GetMediaFiles():
            """Get media files with pagination and filtering."""
            try:
                page = int(request.args.get('Page', 1))
                pageSize = int(request.args.get('PageSize', 20))
                search = request.args.get('Search', '')
                rootFolderPath = request.args.get('RootFolderPath', '')
                
                result = self.ViewModel.GetMediaFilesPaginated(page, pageSize, search, rootFolderPath)
                return jsonify({
                    'Success': True,
                    'MediaFiles': result['MediaFiles'],
                    'TotalCount': result['TotalCount'],
                    'TotalPages': result['TotalPages'],
                    'RootFolderPath': rootFolderPath
                }), 200
                
            except Exception as e:
                DebugService.LogException("Error in GetMediaFiles endpoint", e)
                return jsonify({
                    'Success': False,
                    'Message': f'Error getting media files: {str(e)}',
                    'Error': 'GetMediaFilesError'
                }), 500
        
        @self.Blueprint.route('/MediaFiles/<int:MediaFileId>', methods=['DELETE'])
        def DeleteMediaFile(MediaFileId):
            """Delete a media file."""
            try:
                success = self.ViewModel.DeleteMediaFile(MediaFileId)
                
                if success:
                    return jsonify({
                        'Success': True,
                        'Message': 'Media file deleted successfully'
                    }), 200
                else:
                    return jsonify({
                        'Success': False,
                        'Message': 'Failed to delete media file',
                        'Error': 'DeleteMediaFileError'
                    }), 400
                    
            except Exception as e:
                DebugService.LogException("Error in DeleteMediaFile endpoint", e)
                return jsonify({
                    'Success': False,
                    'Message': f'Error deleting media file: {str(e)}',
                    'Error': 'DeleteMediaFileError'
                }), 500
        
        @self.Blueprint.route('/Scan/TestUnicode', methods=['POST'])
        def TestUnicodeSupport():
            """Test Unicode character support with sample data."""
            try:
                data = request.get_json()
                testPath = data.get('TestPath', '')
                
                if not testPath:
                    return jsonify({
                        'Success': False,
                        'Message': 'TestPath is required',
                        'Error': 'MissingTestPath'
                    }), 400
                
                # Test Unicode path handling
                from Services.FileManagerService import FileManagerService
                fileManager = FileManagerService()
                isValid, sanitizedPath = fileManager.ValidateUnicodePath(testPath)
                
                return jsonify({
                    'Success': True,
                    'OriginalPath': testPath,
                    'IsValid': isValid,
                    'SanitizedPath': sanitizedPath,
                    'Message': 'Unicode test completed'
                }), 200
                
            except Exception as e:
                DebugService.LogException("Error in TestUnicodeSupport endpoint", e)
                return jsonify({
                    'Success': False,
                    'Message': f'Error testing Unicode support: {str(e)}',
                    'Error': 'UnicodeTestError'
                }), 500
        
        @self.Blueprint.route('/Scan/Progress', methods=['GET'])
        def GetScanProgress():
            """Get detailed scan progress information."""
            try:
                status = self.ViewModel.UpdateScanStatus()
                progress = self.ViewModel.GetScanProgressPercentage()
                statusText = self.ViewModel.GetScanStatusText()
                errorText = self.ViewModel.GetErrorText()
                hasErrors = self.ViewModel.HasErrors()
                scanResults = self.ViewModel.GetScanResults()
                scanErrors = self.ViewModel.GetScanErrors()
                
                return jsonify({
                    'Success': True,
                    'IsScanning': status['IsScanning'],
                    'Progress': progress,
                    'StatusText': statusText,
                    'ErrorText': errorText,
                    'HasErrors': hasErrors,
                    'ScanResults': scanResults,
                    'ScanErrors': scanErrors,
                    'CurrentDirectory': status['CurrentDirectory']
                }), 200
                
            except Exception as e:
                DebugService.LogException("Error in GetScanProgress endpoint", e)
                return jsonify({
                    'Success': False,
                    'Message': f'Error getting scan progress: {str(e)}',
                    'Error': 'ProgressError'
                }), 500
        
        @self.Blueprint.route('/Scan/Refresh', methods=['POST'])
        def RefreshData():
            """Refresh all data from the database."""
            try:
                self.ViewModel.RefreshData()
                
                return jsonify({
                    'Success': True,
                    'Message': 'Data refreshed successfully'
                }), 200
                
            except Exception as e:
                DebugService.LogException("Error in RefreshData endpoint", e)
                return jsonify({
                    'Success': False,
                    'Message': f'Error refreshing data: {str(e)}',
                    'Error': 'RefreshError'
                }), 500
        
        @self.Blueprint.route('/ScanDirectories', methods=['GET'])
        def GetScanDirectories():
            """Get all available scan directories from SystemSettings."""
            try:
                scanDirectories = self.ViewModel.GetScanDirectoriesForDisplay()
                return jsonify({
                    'Success': True,
                    'ScanDirectories': scanDirectories
                })
            except Exception as e:
                return jsonify({
                    'Success': False,
                    'Error': f'Error getting scan directories: {str(e)}'
                }), 500
        
        @self.Blueprint.route('/Scanning', methods=['GET'])
        def FileScanningPage():
            """Serve the file scanning web page."""
            try:
                return render_template('FileScanning.html')
                
            except Exception as e:
                DebugService.LogException("Error serving FileScanning page", e)
                return f"Error loading page: {str(e)}", 500
