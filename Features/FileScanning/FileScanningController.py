from flask import Blueprint, request, jsonify, render_template
from typing import Dict, Any
from Features.FileScanning.FileScanningViewModel import FileScanningViewModel
from Core.Logging.LoggingService import LoggingService


class FileScanningController:
    """Provides REST API endpoints for scanning operations with Unicode character support."""

    def __init__(self):
        self.Blueprint = Blueprint('FileScanning', __name__, url_prefix='/api')
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

                LoggingService.LogInfo(f"Parsed parameters - RootFolderPath: '{RootFolderPath}' (type: {type(RootFolderPath)}), Recursive: {Recursive}", "FileScanningController", "StartScan")


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

        @self.Blueprint.route('/Scan/<string:JobId>/Stop', methods=['POST'])
        def StopScanByJobId(JobId):
            """Soft-stop a specific scan by JobId.

            Directive 2026-05-27 criterion 21. Flips ScanJobs.Status='Stopping'; the
            owning worker's heartbeat thread observes the transition and flips
            self._StopRequested, the per-file / per-probe loops exit, and the worker
            writes the terminal Status='Stopped' row.

            Returns 404 if the JobId is not in a Running state.
            """
            try:
                from Core.Database.DatabaseService import DatabaseService
                Db = DatabaseService()
                Rows = Db.ExecuteQuery(
                    "SELECT Status, WorkerName FROM ScanJobs WHERE JobId = %s", (JobId,)
                )
                if not Rows:
                    return jsonify({'Success': False, 'Message': f'Scan {JobId} not found'}), 404
                CurrentStatus = (Rows[0].get('Status') or '').lower()
                if CurrentStatus != 'running':
                    return jsonify({
                        'Success': False,
                        'Message': f'Scan {JobId} is not Running (current: {Rows[0].get("Status")})',
                    }), 409
                Db.ExecuteNonQuery(
                    "UPDATE ScanJobs SET Status = 'Stopping' WHERE JobId = %s AND Status = 'Running'",
                    (JobId,),
                )
                LoggingService.LogInfo(
                    f"Soft-stop requested for scan {JobId} (worker: {Rows[0].get('WorkerName')})",
                    "FileScanningController", "StopScanByJobId",
                )
                return jsonify({
                    'Success': True,
                    'Message': f'Stop requested for scan {JobId}; worker will exit on next heartbeat (~5s).',
                    'JobId': JobId,
                    'Worker': Rows[0].get('WorkerName'),
                }), 200
            except Exception as e:
                LoggingService.LogException("Error in StopScanByJobId endpoint", e, "FileScanningController", "StopScanByJobId")
                return jsonify({
                    'Success': False,
                    'Message': f'Error stopping scan: {str(e)}',
                    'Error': 'StopScanError',
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

        @self.Blueprint.route('/RootFolders', methods=['POST'])
        def AddRootFolder():
            """Add a new root folder for scanning."""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({'Success': False, 'Message': 'Request body is required'}), 400

                RootFolderPath = data.get('RootFolderPath', '').strip()
                PreferredWorkerName = data.get('PreferredWorkerName', None)

                if not RootFolderPath:
                    return jsonify({'Success': False, 'Message': 'RootFolderPath is required'}), 400

                result = self.ViewModel.AddRootFolder(RootFolderPath, PreferredWorkerName)
                StatusCode = 201 if result.get('Success') else 400
                return jsonify(result), StatusCode

            except Exception as e:
                LoggingService.LogException("Error in AddRootFolder endpoint", e, "FileScanningController", "AddRootFolder")
                return jsonify({
                    'Success': False,
                    'Message': f'Error adding root folder: {str(e)}',
                    'Error': 'AddRootFolderError'
                }), 500

        @self.Blueprint.route('/RootFolders/<int:RootFolderId>/Subfolders', methods=['GET'])
        def GetRootFolderSubfolders(RootFolderId):
            """Get subfolders for a root folder with pagination and filtering."""
            try:
                rootFolder = self.ViewModel.BusinessService.Repository.GetRootFolderById(RootFolderId)
                if not rootFolder:
                    return jsonify({
                        'Success': False,
                        'Message': 'Root folder not found',
                        'Error': 'RootFolderNotFound'
                    }), 404

                page = int(request.args.get('Page', 1))
                pageSize = int(request.args.get('PageSize', 25))
                search = request.args.get('Search', '')
                sortColumn = request.args.get('SortColumn', 'TotalSizeMB')
                sortOrder = request.args.get('SortOrder', 'DESC')

                result = self.ViewModel.GetSubfoldersPaginated(
                    rootFolder.RootFolder, page, pageSize, search, sortColumn, sortOrder
                )
                return jsonify({
                    'Success': True,
                    'Subfolders': result['Subfolders'],
                    'TotalCount': result['TotalCount'],
                    'TotalPages': result['TotalPages'],
                    'RootFolderPath': rootFolder.RootFolder
                }), 200

            except Exception as e:
                LoggingService.LogException("Error in GetRootFolderSubfolders endpoint", e, "FileScanningController", "GetRootFolderSubfolders")
                return jsonify({
                    'Success': False,
                    'Message': f'Error getting subfolders: {str(e)}',
                    'Error': 'GetSubfoldersError'
                }), 500

        @self.Blueprint.route('/RootFolders/SubfoldersByPath', methods=['GET'])
        def GetSubfoldersByPath():
            """Get subfolders for a root folder path with pagination and filtering."""
            try:
                rootFolderPath = request.args.get('RootFolderPath', '')
                LoggingService.LogInfo(f"GetSubfoldersByPath called with RootFolderPath={repr(rootFolderPath)}", "FileScanningController", "GetSubfoldersByPath")
                if not rootFolderPath:
                    return jsonify({
                        'Success': False,
                        'Message': 'RootFolderPath is required',
                        'Error': 'MissingParameter'
                    }), 400

                page = int(request.args.get('Page', 1))
                pageSize = int(request.args.get('PageSize', 25))
                search = request.args.get('Search', '')
                sortColumn = request.args.get('SortColumn', 'TotalSizeMB')
                sortOrder = request.args.get('SortOrder', 'DESC')

                result = self.ViewModel.GetSubfoldersPaginated(
                    rootFolderPath, page, pageSize, search, sortColumn, sortOrder
                )
                return jsonify({
                    'Success': True,
                    'Subfolders': result['Subfolders'],
                    'TotalCount': result['TotalCount'],
                    'TotalPages': result['TotalPages'],
                    'RootFolderPath': rootFolderPath
                }), 200

            except Exception as e:
                LoggingService.LogException("Error in GetSubfoldersByPath endpoint", e, "FileScanningController", "GetSubfoldersByPath")
                return jsonify({
                    'Success': False,
                    'Message': f'Error getting subfolders: {str(e)}',
                    'Error': 'GetSubfoldersError'
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

        @self.Blueprint.route('/TranscodeCandidates', methods=['GET'])
        def GetTranscodeCandidates():
            """Get transcode candidate subfolders ranked by estimated savings."""
            try:
                rootFolderPath = request.args.get('RootFolderPath', '')
                if not rootFolderPath:
                    return jsonify({
                        'Success': False,
                        'Message': 'RootFolderPath is required',
                        'Error': 'MissingParameter'
                    }), 400

                page = int(request.args.get('Page', 1))
                pageSize = int(request.args.get('PageSize', 25))
                search = request.args.get('Search', '')
                sortColumn = request.args.get('SortColumn', 'EstimatedSavingsMB')
                sortOrder = request.args.get('SortOrder', 'DESC')

                result = self.ViewModel.GetTranscodeCandidatesPaginated(
                    rootFolderPath, page, pageSize, search, sortColumn, sortOrder
                )
                return jsonify({
                    'Success': True,
                    'Subfolders': result['Subfolders'],
                    'TotalCount': result['TotalCount'],
                    'TotalPages': result['TotalPages'],
                    'RootFolderPath': rootFolderPath
                }), 200

            except Exception as e:
                LoggingService.LogException("Error in GetTranscodeCandidates endpoint", e, "FileScanningController", "GetTranscodeCandidates")
                return jsonify({
                    'Success': False,
                    'Message': f'Error getting transcode candidates: {str(e)}',
                    'Error': 'GetTranscodeCandidatesError'
                }), 500

        @self.Blueprint.route('/TranscodeCandidates/Files', methods=['GET'])
        def GetTranscodeCandidateFiles():
            """Get individual untranscoded files in a subfolder for drill-down."""
            try:
                subfolderPath = request.args.get('SubfolderPath', '')
                if not subfolderPath:
                    return jsonify({
                        'Success': False,
                        'Message': 'SubfolderPath is required',
                        'Error': 'MissingParameter'
                    }), 400

                page = int(request.args.get('Page', 1))
                pageSize = int(request.args.get('PageSize', 25))

                result = self.ViewModel.GetTranscodeCandidateFiles(subfolderPath, page, pageSize)
                return jsonify({
                    'Success': True,
                    'Files': result['Files'],
                    'TotalCount': result['TotalCount'],
                    'TotalPages': result['TotalPages'],
                    'SubfolderPath': subfolderPath
                }), 200

            except Exception as e:
                LoggingService.LogException("Error in GetTranscodeCandidateFiles endpoint", e, "FileScanningController", "GetTranscodeCandidateFiles")
                return jsonify({
                    'Success': False,
                    'Message': f'Error getting candidate files: {str(e)}',
                    'Error': 'GetCandidateFilesError'
                }), 500

        @self.Blueprint.route('/TranscodeCandidates/AllFiles', methods=['GET'])
        def GetAllTranscodeCandidateFiles():
            """Get individual transcode candidate files across a root folder, sortable by bitrate."""
            try:
                RootFolderPath = request.args.get('RootFolderPath', '')
                if not RootFolderPath:
                    return jsonify({
                        'Success': False,
                        'Message': 'RootFolderPath is required',
                        'Error': 'MissingParameter'
                    }), 400

                Page = int(request.args.get('Page', 1))
                PageSize = int(request.args.get('PageSize', 25))
                Search = request.args.get('Search', '')
                SortColumn = request.args.get('SortColumn', 'VideoBitrateKbps')
                SortOrder = request.args.get('SortOrder', 'DESC')

                Result = self.ViewModel.GetAllTranscodeCandidateFilesPaginated(
                    RootFolderPath, Page, PageSize, Search, SortColumn, SortOrder
                )
                return jsonify({
                    'Success': True,
                    'Files': Result['Files'],
                    'TotalCount': Result['TotalCount'],
                    'TotalPages': Result['TotalPages'],
                    'RootFolderPath': RootFolderPath
                }), 200

            except Exception as e:
                LoggingService.LogException("Error in GetAllTranscodeCandidateFiles endpoint", e, "FileScanningController", "GetAllTranscodeCandidateFiles")
                return jsonify({
                    'Success': False,
                    'Message': f'Error getting candidate files: {str(e)}',
                    'Error': 'GetAllCandidateFilesError'
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

        @self.Blueprint.route('/Scan/CleanupDuplicates', methods=['POST'])
        def CleanupDuplicates():
            """Remove duplicate media file records from the database."""
            try:
                LoggingService.LogInfo("CleanupDuplicates endpoint called", "FileScanningController", "CleanupDuplicates")
                # directive: path-schema-migration | # see path.S8 -- CleanupDuplicateMediaFiles lives on MediaFilesRepository
                from Features.MediaFiles.MediaFilesRepository import MediaFilesRepository
                result = MediaFilesRepository(self.ViewModel.BusinessService.Repository.DatabaseService).CleanupDuplicateMediaFiles()
                return jsonify(result), 200 if result.get('Success') else 500
            except Exception as e:
                LoggingService.LogException("Error cleaning up duplicates", e, "FileScanningController", "CleanupDuplicates")
                return jsonify({
                    'Success': False,
                    'Message': f'Error cleaning up duplicates: {str(e)}',
                    'Error': 'CleanupError'
                }), 500

        @self.Blueprint.route('/MediaFiles/Corrupt', methods=['GET'])
        # directive: path-schema-migration | # see path.S8
        def GetCorruptFiles():
            """Get media files that failed FFprobe 3+ times (possibly corrupt)."""
            try:
                import ntpath
                from Core.Database.DatabaseService import DatabaseService
                from Core.Path.Path import Path
                from Core.Path.PathStorageRoots import GetPrefixMap
                Query = "SELECT Id, StorageRootId, RelativePath, FileName, SizeMB, FFProbeFailureCount, LastFFprobeError FROM MediaFiles WHERE FFProbeFailureCount >= 3 ORDER BY SizeMB DESC"
                Rows = DatabaseService().ExecuteQuery(Query)
                PrefixMap = GetPrefixMap()
                Files = []
                for r in Rows:
                    Sid = r.get('StorageRootId')
                    Rel = r.get('RelativePath') or ''
                    DisplayPath = Path(Sid, Rel).CanonicalDisplay(PrefixMap) if Sid is not None else ''
                    Directory = ntpath.dirname(DisplayPath) if DisplayPath else ''
                    Files.append({'Id': r['Id'], 'FilePath': DisplayPath, 'Directory': Directory, 'FileName': r['FileName'],
                                  'SizeMB': float(r['SizeMB']) if r['SizeMB'] else 0,
                                  'FailCount': r['FFProbeFailureCount'],
                                  'Error': r.get('LastFFprobeError', '')})
                return jsonify({'Success': True, 'Files': Files, 'Count': len(Files)}), 200
            except Exception as e:
                LoggingService.LogException("Error getting corrupt files", e, "FileScanningController", "GetCorruptFiles")
                return jsonify({'Success': False, 'Message': str(e)}), 500

        @self.Blueprint.route('/MediaFiles/CleanCorrupt', methods=['POST'])
        def CleanCorruptFiles():
            """Delete all media files that failed FFprobe 3+ times."""
            try:
                from Core.Database.DatabaseService import DatabaseService
                CountQuery = "SELECT COUNT(*) as Count FROM MediaFiles WHERE FFProbeFailureCount >= 3"
                CountResult = DatabaseService().ExecuteQuery(CountQuery)
                Count = CountResult[0]['Count'] if CountResult else 0

                if Count == 0:
                    return jsonify({'Success': True, 'Message': 'No corrupt files to clean', 'Cleaned': 0}), 200

                DeleteQuery = "DELETE FROM MediaFiles WHERE FFProbeFailureCount >= 3"
                DatabaseService().ExecuteNonQuery(DeleteQuery)
                LoggingService.LogInfo(f"Cleaned {Count} corrupt media files from database", "FileScanningController", "CleanCorruptFiles")
                return jsonify({'Success': True, 'Message': f'Removed {Count} corrupt files from database', 'Cleaned': Count}), 200
            except Exception as e:
                LoggingService.LogException("Error cleaning corrupt files", e, "FileScanningController", "CleanCorruptFiles")
                return jsonify({'Success': False, 'Message': str(e)}), 500

        @self.Blueprint.route('/Scan/EnableContinuous', methods=['POST'])
        def EnableContinuousScanning():
            """Enable continuous/periodic scanning."""
            try:
                LoggingService.LogInfo("EnableContinuousScanning endpoint called", "FileScanningController", "EnableContinuousScanning")
                data = request.get_json() or {}
                IntervalMinutes = data.get('IntervalMinutes', 60)

                from Features.FileScanning.ContinuousScanService import ContinuousScanService
                from Features.FileScanning.FileScanningRepository import FileScanningRepository

                # Use shared instance or create one
                if not hasattr(self.ViewModel, 'ContinuousScanService') or self.ViewModel.ContinuousScanService is None:
                    self.ViewModel.ContinuousScanService = ContinuousScanService()

                result = self.ViewModel.ContinuousScanService.StartContinuousScanning(IntervalMinutes)

                if result['Success']:
                    try:
                        from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
                        settings = SystemSettingsRepository()
                        settings.AddOrUpdateSystemSetting('ContinuousScanEnabled', '1', 'Enable/disable continuous file scanning', 'boolean')
                        settings.AddOrUpdateSystemSetting('ContinuousScanIntervalMinutes', str(IntervalMinutes), 'Interval in minutes for continuous scanning', 'integer')
                        LoggingService.LogInfo(f"Saved continuous scanning settings to database (enabled, interval: {IntervalMinutes})", "FileScanningController", "EnableContinuousScanning")
                    except Exception as e:
                        LoggingService.LogWarning(f"Could not save continuous scan settings to database: {e}", "FileScanningController", "EnableContinuousScanning")

                    return jsonify(result), 200
                else:
                    return jsonify(result), 400

            except Exception as e:
                LoggingService.LogException("Error enabling continuous scanning", e, "FileScanningController", "EnableContinuousScanning")
                return jsonify({
                    'Success': False,
                    'Message': f'Error enabling continuous scanning: {str(e)}',
                    'Error': 'EnableContinuousScanError'
                }), 500

        @self.Blueprint.route('/Scan/DisableContinuous', methods=['POST'])
        def DisableContinuousScanning():
            """Disable continuous/periodic scanning."""
            try:
                LoggingService.LogInfo("DisableContinuousScanning endpoint called", "FileScanningController", "DisableContinuousScanning")

                if not hasattr(self.ViewModel, 'ContinuousScanService') or self.ViewModel.ContinuousScanService is None:
                    return jsonify({
                        'Success': False,
                        'Message': 'Continuous scanning is not running',
                        'Error': 'NotRunning'
                    }), 400

                result = self.ViewModel.ContinuousScanService.StopContinuousScanning()

                if result['Success']:
                    try:
                        from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
                        SystemSettingsRepository().AddOrUpdateSystemSetting('ContinuousScanEnabled', '0', 'Enable/disable continuous file scanning', 'boolean')
                        LoggingService.LogInfo("Saved continuous scanning disabled state to database", "FileScanningController", "DisableContinuousScanning")
                    except Exception as e:
                        LoggingService.LogWarning(f"Could not save continuous scan settings to database: {e}", "FileScanningController", "DisableContinuousScanning")

                    return jsonify(result), 200
                else:
                    return jsonify(result), 400

            except Exception as e:
                LoggingService.LogException("Error disabling continuous scanning", e, "FileScanningController", "DisableContinuousScanning")
                return jsonify({
                    'Success': False,
                    'Message': f'Error disabling continuous scanning: {str(e)}',
                    'Error': 'DisableContinuousScanError'
                }), 500

        @self.Blueprint.route('/Scan/ContinuousStatus', methods=['GET'])
        def GetContinuousScanStatus():
            """Get the status of continuous scanning."""
            try:
                from Features.FileScanning.ContinuousScanService import ContinuousScanService

                # Use shared instance or create one
                if not hasattr(self.ViewModel, 'ContinuousScanService') or self.ViewModel.ContinuousScanService is None:
                    self.ViewModel.ContinuousScanService = ContinuousScanService()

                result = self.ViewModel.ContinuousScanService.GetStatus()

                return jsonify(result), 200

            except Exception as e:
                LoggingService.LogException("Error getting continuous scan status", e, "FileScanningController", "GetContinuousScanStatus")
                return jsonify({
                    'Success': False,
                    'Message': f'Error getting continuous scan status: {str(e)}',
                    'Error': 'GetContinuousStatusError'
                }), 500

        @self.Blueprint.route('/Scanning', methods=['GET'])
        def FileScanningPage():
            """Serve the file scanning web page."""
            try:
                return render_template('FileScanning.html')

            except Exception as e:
                LoggingService.LogException("Error serving FileScanning page", e, "FileScanningController", "FileScanning")
                return f"Error loading page: {str(e)}", 500
