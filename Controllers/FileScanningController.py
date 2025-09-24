from flask import Blueprint, request, jsonify, render_template
from typing import Dict, Any
from ViewModels.FileScanningViewModel import FileScanningViewModel
from Services.LoggingService import LoggingService


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
            """Start scanning a root folder using subprocess."""
            try:
                LoggingService.LogInfo("StartScan endpoint called", "FileScanningController", "StartScan")
                data = request.get_json()
                LoggingService.LogInfo(f"Request data received: {data}", "FileScanningController", "StartScan")
                
                RootFolderPath = data.get('RootFolderPath', '')
                Recursive = data.get('Recursive', True)
                
                LoggingService.LogInfo(f"Parsed parameters - RootFolderPath: {RootFolderPath}, Recursive: {Recursive}", "FileScanningController", "StartScan")
                
                if not RootFolderPath:
                    LoggingService.LogError("RootFolderPath is missing", "FileScanningController", "StartScan")
                    return jsonify({
                        'Success': False,
                        'Message': 'RootFolderPath is required',
                        'Error': 'MissingPath'
                    }), 400
                
                LoggingService.LogInfo("Calling ViewModel.StartScanning", "FileScanningController", "StartScan")
                result = self.ViewModel.StartScanning(RootFolderPath, Recursive)
                LoggingService.LogInfo(f"ViewModel.StartScanning result: {result}", "FileScanningController", "StartScan")
                
                if result['Success']:
                    return jsonify(result), 200
                else:
                    return jsonify(result), 400
                    
            except Exception as e:
                LoggingService.LogException("Error in StartScan endpoint", e, "FileScanningController", "StartScan")
                return jsonify({
                    'Success': False,
                    'Message': f'Error starting scan: {str(e)}',
                    'Error': 'StartScanError'
                }), 500
        
        @self.Blueprint.route('/Scan/Status', methods=['GET'])
        def GetScanStatus():
            """Get current scan status and progress."""
            try:
                # Remove verbose logging - only log errors
                status = self.ViewModel.UpdateScanStatus()
                return jsonify(status), 200
                
            except Exception as e:
                LoggingService.LogException("Error in GetScanStatus endpoint", e, "FileScanningController", "GetScanStatus")
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
                LoggingService.LogException("Error in StopScan endpoint", e, "FileScanningController", "StopScan")
                return jsonify({
                    'Success': False,
                    'Message': f'Error stopping scan: {str(e)}',
                    'Error': 'StopScanError'
                }), 500
        
        @self.Blueprint.route('/RootFolders', methods=['GET'])
        def GetRootFolders():
            """Get root folders with pagination, filtering, and sorting."""
            try:
                page = int(request.args.get('Page', 1))
                pageSize = int(request.args.get('PageSize', 10))
                search = request.args.get('Search', '')
                sortColumn = request.args.get('SortColumn', 'RootFolder')
                sortOrder = request.args.get('SortOrder', 'ASC')
                
                result = self.ViewModel.GetRootFoldersPaginated(page, pageSize, search, sortColumn, sortOrder)
                return jsonify({
                    'Success': True,
                    'RootFolders': result['RootFolders'],
                    'TotalCount': result['TotalCount'],
                    'TotalPages': result['TotalPages'],
                    'AllRootFolders': result['AllRootFolders']
                }), 200
                
            except Exception as e:
                LoggingService.LogException("Error in GetRootFolders endpoint", e, "FileScanningController", "GetRootFolders")
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
                LoggingService.LogException("Error in DeleteRootFolder endpoint", e, "FileScanningController", "DeleteRootFolder")
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
                sortBy = request.args.get('SortBy', 'SizeMB')
                sortOrder = request.args.get('SortOrder', 'DESC')
                
                LoggingService.LogInfo(f"MediaFiles API called with SortBy={sortBy}, SortOrder={sortOrder}", "FileScanningController", "GetMediaFiles")
                
                result = self.ViewModel.GetMediaFilesPaginated(page, pageSize, search, rootFolderPath, sortBy, sortOrder)
                return jsonify({
                    'Success': True,
                    'MediaFiles': result['MediaFiles'],
                    'TotalCount': result['TotalCount'],
                    'TotalPages': result['TotalPages'],
                    'RootFolderPath': rootFolderPath
                }), 200
                
            except Exception as e:
                LoggingService.LogException("Error in GetMediaFiles endpoint", e, "FileScanningController", "GetMediaFiles")
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
                LoggingService.LogException("Error in DeleteMediaFile endpoint", e, "FileScanningController", "DeleteMediaFile")
                return jsonify({
                    'Success': False,
                    'Message': f'Error deleting media file: {str(e)}',
                    'Error': 'DeleteMediaFileError'
                }), 500
        
        @self.Blueprint.route('/MediaFiles/<int:MediaFileId>/Refresh', methods=['POST'])
        def RefreshMediaFile(MediaFileId):
            """Refresh a single media file's details."""
            try:
                result = self.ViewModel.RefreshMediaFile(MediaFileId)
                return jsonify(result), 200 if result.get('Success') else 400
            except Exception as e:
                return jsonify({
                    'Success': False,
                    'Message': f'Error refreshing media file: {str(e)}'
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
                LoggingService.LogException("Error in TestUnicodeSupport endpoint", e, "FileScanningController", "TestUnicodeSupport")
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
                LoggingService.LogException("Error in GetScanProgress endpoint", e, "FileScanningController", "GetScanProgress")
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
                LoggingService.LogException("Error in RefreshData endpoint", e, "FileScanningController", "RefreshData")
                return jsonify({
                    'Success': False,
                    'Message': f'Error refreshing data: {str(e)}',
                    'Error': 'RefreshError'
                }), 500
        
        @self.Blueprint.route('/Scan/ExtractMetadata', methods=['POST'])
        def ExtractMetadata():
            """Extract metadata for existing files that need it."""
            try:
                LoggingService.LogInfo("ExtractMetadata endpoint called", "FileScanningController", "ExtractMetadata")
                data = request.get_json() or {}
                
                RootFolderId = data.get('RootFolderId', None)
                
                LoggingService.LogInfo(f"ExtractMetadata parameters - RootFolderId: {RootFolderId}", "FileScanningController", "ExtractMetadata")
                
                LoggingService.LogInfo("Calling ViewModel.ExtractMetadataForExistingFiles", "FileScanningController", "ExtractMetadata")
                result = self.ViewModel.ExtractMetadataForExistingFiles(RootFolderId)
                LoggingService.LogInfo(f"ViewModel.ExtractMetadataForExistingFiles result: {result}", "FileScanningController", "ExtractMetadata")
                
                if result['Success']:
                    return jsonify(result), 200
                else:
                    return jsonify(result), 400
                    
            except Exception as e:
                LoggingService.LogException("Error in ExtractMetadata endpoint", e, "FileScanningController", "ExtractMetadata")
                return jsonify({
                    'Success': False,
                    'Message': f'Error extracting metadata: {str(e)}',
                    'Error': 'ExtractMetadataError'
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
        
        @self.Blueprint.route('/ScanDirectories', methods=['POST'])
        def AddScanDirectory():
            """Add or update a scan directory in SystemSettings."""
            try:
                data = request.get_json() or {}
                Key = data.get('Key')
                Path = data.get('Path', '').strip()
                Description = data.get('Description', '').strip()
                
                if not Path:
                    return jsonify({
                        'Success': False,
                        'Error': 'Directory path is required'
                    }), 400
                
                result = self.ViewModel.AddOrUpdateScanDirectory(Key, Path, Description)
                
                if result['Success']:
                    return jsonify({
                        'Success': True,
                        'Message': result['Message']
                    }), 200
                else:
                    return jsonify({
                        'Success': False,
                        'Error': result['Error']
                    }), 400
                    
            except Exception as e:
                LoggingService.LogException("Error in AddScanDirectory endpoint", e, "FileScanningController", "AddScanDirectory")
                return jsonify({
                    'Success': False,
                    'Error': f'Error adding scan directory: {str(e)}'
                }), 500
        
        @self.Blueprint.route('/ScanDirectories/<string:key>', methods=['DELETE'])
        def DeleteScanDirectory(key):
            """Delete a scan directory from SystemSettings."""
            try:
                result = self.ViewModel.DeleteScanDirectory(key)
                
                if result['Success']:
                    return jsonify({
                        'Success': True,
                        'Message': result['Message']
                    }), 200
                else:
                    return jsonify({
                        'Success': False,
                        'Error': result['Error']
                    }), 400
                    
            except Exception as e:
                LoggingService.LogException("Error in DeleteScanDirectory endpoint", e, "FileScanningController", "DeleteScanDirectory")
                return jsonify({
                    'Success': False,
                    'Error': f'Error deleting scan directory: {str(e)}'
                }), 500
        
        @self.Blueprint.route('/Statistics', methods=['GET'])
        def GetStatistics():
            """Get database statistics for the file scanning page."""
            try:
                result = self.ViewModel.GetStatistics()
                return jsonify({
                    'Success': True,
                    'Statistics': result
                }), 200
                
            except Exception as e:
                LoggingService.LogException("Error getting statistics", e, "FileScanningController", "GetStatistics")
                return jsonify({
                    'Success': False,
                    'Message': f'Error getting statistics: {str(e)}',
                    'Error': 'StatisticsError'
                }), 500
        
        @self.Blueprint.route('/Scanning', methods=['GET'])
        def FileScanningPage():
            """Serve the file scanning web page."""
            try:
                return render_template('FileScanning.html')
                
            except Exception as e:
                LoggingService.LogException("Error serving FileScanning page", e, "FileScanningController", "FileScanning")
                return f"Error loading page: {str(e)}", 500
