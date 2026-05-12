"""
QualityTestController - Simple controller for quality testing operations
Implements MVVM pattern using MVVM architecture
"""

import os
import json
from flask import Blueprint, request, jsonify
from Repositories.DatabaseManager import DatabaseManager
from Core.Logging.LoggingService import LoggingService
from Services.QualityTestQueueService import QualityTestQueueService

QualityTestBlueprint = Blueprint('QualityTest', __name__)

class QualityTestController:
    def __init__(self):
        self.DatabaseManager = DatabaseManager()
        self.LoggingService = LoggingService()
        self.QualityTestQueueService = QualityTestQueueService(self.DatabaseManager)

    def StartQualityTest(self, JobId: int) -> dict:
        """Trigger quality test processing - the job is already in the queue, just verify it exists."""
        try:
            self.LoggingService.LogInfo(f"Triggering quality test for job {JobId}")

            # Verify the job exists in the queue
            JobDetails = self.DatabaseManager.GetQualityTestJob(JobId)

            if JobDetails:
                return {"Success": True, "Message": "Quality test job exists in queue and will be processed"}
            else:
                return {"Success": False, "Message": "Quality test job not found in queue"}

        except Exception as e:
            self.LoggingService.LogError(f"Error triggering quality test: {str(e)}")
            return {"Success": False, "Message": str(e)}


    def GetQualityTestStatus(self, JobId: int) -> dict:
        """Get status of a quality test job by checking both queue and results tables."""
        try:
            JobDetails = self.DatabaseManager.GetQualityTestJob(JobId)
            if not JobDetails:
                return {"Success": False, "Message": "Job not found"}

            # Determine status from queue dates
            if JobDetails.get("DateCompleted"):
                Status = "Completed"
            elif JobDetails.get("DateStarted"):
                Status = "Running"
            else:
                Status = "Pending"

            # Get VMAF score from QualityTestResults if available
            TranscodeAttemptId = JobDetails.get("TranscodeAttemptId")
            VMAFScore = None
            if TranscodeAttemptId:
                query = "SELECT VMAFScore FROM QualityTestResults WHERE TranscodeAttemptId = %s ORDER BY DateTested DESC LIMIT 1"
                results = self.DatabaseManager.DatabaseService.ExecuteQuery(query, (TranscodeAttemptId,))
                if results:
                    VMAFScore = results[0].get("VMAFScore")

            return {"Success": True, "Status": Status, "VMAFScore": VMAFScore, "JobDetails": JobDetails}
        except Exception as e:
            return {"Success": False, "Message": str(e)}

    def GetQualityTestQueue(self) -> dict:
        """Get all quality test jobs in queue"""
        try:
            Jobs = self.DatabaseManager.GetQualityTestQueue()
            return {"Success": True, "Jobs": Jobs}
        except Exception as e:
            return {"Success": False, "Message": str(e)}

    def GetQualityTestServiceStatus(self) -> dict:
        """Get overall quality test service status"""
        try:
            # Check if there are any active quality test jobs
            ActiveJobs = self.DatabaseManager.GetActiveJobsByService("QualityTest")
            IsRunning = len(ActiveJobs) > 0

            return {"Success": True, "IsRunning": IsRunning, "ActiveJobs": len(ActiveJobs)}
        except Exception as e:
            return {"Success": False, "Message": str(e)}


    def LogError(self, ErrorMessage: str, ErrorContext: str, RequestUrl: str) -> dict:
        """Log an error to the database"""
        try:
            self.LoggingService.LogError(f"Quality Test Error - Context: {ErrorContext}, URL: {RequestUrl}, Message: {ErrorMessage}")
            return {"Success": True, "Message": "Error logged successfully"}
        except Exception as e:
            return {"Success": False, "Message": str(e)}

    def RetryQualityTest(self, JobId: int) -> dict:
        """Retry a failed quality test job by deleting old results and re-queuing."""
        try:
            self.LoggingService.LogInfo(f"Retrying quality test for job {JobId}")

            # Get job details from queue
            JobDetails = self.DatabaseManager.GetQualityTestJob(JobId)
            if not JobDetails:
                return {"Success": False, "Message": "Job not found"}

            TranscodeAttemptId = JobDetails.get("TranscodeAttemptId")
            if not TranscodeAttemptId:
                return {"Success": False, "Message": "Job has no TranscodeAttemptId"}

            # Delete existing quality test records and re-queue
            DeleteSuccess = self.DatabaseManager.DeleteQualityTestRecordsByAttemptId(TranscodeAttemptId)
            if not DeleteSuccess:
                return {"Success": False, "Message": "Failed to clean up existing quality test records"}

            # Re-add to queue
            NewJobId = self.QualityTestQueueService.AddToQualityTestQueue(TranscodeAttemptId)
            if NewJobId:
                return {"Success": True, "Message": "Job re-queued for retry", "NewJobId": NewJobId}
            else:
                return {"Success": False, "Message": "Failed to re-queue job for retry"}

        except Exception as e:
            self.LoggingService.LogError(f"Error retrying quality test: {str(e)}")
            return {"Success": False, "Message": str(e)}

    def GetQualityTestHistory(self, Page: int = 1, Limit: int = 10) -> dict:
        """Get recent quality test results from QualityTestResults table with pagination"""
        try:
            # Calculate offset for pagination
            Offset = (Page - 1) * Limit

            # Get results with pagination
            Results = self.DatabaseManager.GetQualityTestResults(Limit, Offset)

            # Get total count for pagination info
            TotalCount = self.DatabaseManager.GetQualityTestResultsCount()

            # Calculate pagination info
            TotalPages = (TotalCount + Limit - 1) // Limit  # Ceiling division
            HasNextPage = Page < TotalPages
            HasPreviousPage = Page > 1

            return {
                "Success": True,
                "QualityTestingResults": Results,
                "Pagination": {
                    "CurrentPage": Page,
                    "PageSize": Limit,
                    "TotalCount": TotalCount,
                    "TotalPages": TotalPages,
                    "HasNextPage": HasNextPage,
                    "HasPreviousPage": HasPreviousPage
                }
            }
        except Exception as e:
            self.LoggingService.LogError(f"Error getting quality test history: {str(e)}")
            return {"Success": False, "Message": str(e)}

    def GetQualityTestProgress(self) -> dict:
        """Get running quality test progress from QualityTestProgress table"""
        try:
            Progress = self.DatabaseManager.GetRunningQualityTestProgress()
            if Progress:
                return {
                    "Success": True,
                    "IsRunning": True,
                    "CurrentJob": Progress,
                    "Progress": Progress
                }
            else:
                return {"Success": True, "IsRunning": False, "CurrentJob": None}
        except Exception as e:
            self.LoggingService.LogError(f"Error getting quality test progress: {str(e)}")
            return {"Success": False, "Message": str(e)}

    def AddToQueue(self, TranscodeAttemptId: int) -> dict:
        """Add a transcode attempt to the quality test queue."""
        try:
            self.LoggingService.LogInfo(f"Adding transcode attempt {TranscodeAttemptId} to quality test queue", "QualityTestController", "AddToQueue")

            # Delete existing quality test records for this attempt (allows re-queueing)
            DeleteSuccess = self.DatabaseManager.DeleteQualityTestRecordsByAttemptId(TranscodeAttemptId)
            if not DeleteSuccess:
                return {"Success": False, "Message": "Failed to clean up existing quality test records"}

            # Use QualityTestQueueService to add to queue (handles all validation and file path resolution)
            JobId = self.QualityTestQueueService.AddToQualityTestQueue(TranscodeAttemptId)

            if JobId:
                self.LoggingService.LogInfo(f"Successfully added quality test job {JobId} for transcode attempt {TranscodeAttemptId}",
                                          "QualityTestController", "AddToQueue")
                return {"Success": True, "Message": "Added to quality test queue successfully", "JobId": JobId}
            else:
                return {"Success": False, "Message": "Failed to create quality test queue entry"}

        except Exception as e:
            ErrorMsg = f"Exception adding transcode attempt {TranscodeAttemptId} to queue: {str(e)}"
            self.LoggingService.LogException(ErrorMsg, e, "QualityTestController", "AddToQueue")
            return {"Success": False, "Message": ErrorMsg}

# Flask routes
@QualityTestBlueprint.route('/QualityTest/Start', methods=['POST'])
def StartQualityTest():
    try:
        LoggingService.LogFunctionEntry("StartQualityTest", "QualityTestController")

        Controller = QualityTestController()
        Data = request.get_json()

        # Individual job start request
        JobId = Data.get('JobId') if Data else None

        if not JobId:
            return jsonify({"Success": False, "Message": "JobId required"}), 400

        Result = Controller.StartQualityTest(JobId)

        LoggingService.LogInfo(f"StartQualityTest completed: {Result.get('Success', False)}", "QualityTestController", "StartQualityTest")
        return jsonify(Result)

    except Exception as e:
        ErrorMsg = f"Exception in StartQualityTest endpoint: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "StartQualityTest")
        return jsonify({
            "Success": False,
            "Message": "Failed to start quality test",
            "Error": ErrorMsg
        }), 500

@QualityTestBlueprint.route('/QualityTest/Status/<int:JobId>', methods=['GET'])
def GetQualityTestStatus(JobId):
    try:
        Controller = QualityTestController()
        Result = Controller.GetQualityTestStatus(JobId)
        return jsonify(Result)
    except Exception as e:
        ErrorMsg = f"Exception in GetQualityTestStatus endpoint: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "GetQualityTestStatus")
        return jsonify({"Success": False, "Message": "Failed to get quality test status", "Error": ErrorMsg}), 500

@QualityTestBlueprint.route('/api/QualityTest/Status', methods=['GET'])
def GetQualityTestServiceStatus():
    try:
        Controller = QualityTestController()
        Result = Controller.GetQualityTestServiceStatus()
        return jsonify(Result)
    except Exception as e:
        ErrorMsg = f"Exception in GetQualityTestServiceStatus endpoint: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "GetQualityTestServiceStatus")
        return jsonify({"Success": False, "Message": "Failed to get service status", "Error": ErrorMsg}), 500

@QualityTestBlueprint.route('/api/QualityTest/Queue', methods=['GET'])
def GetQualityTestQueue():
    try:
        Controller = QualityTestController()
        Result = Controller.GetQualityTestQueue()
        return jsonify(Result)
    except Exception as e:
        ErrorMsg = f"Exception in GetQualityTestQueue endpoint: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "GetQualityTestQueue")
        return jsonify({"Success": False, "Message": "Failed to get quality test queue", "Error": ErrorMsg}), 500

@QualityTestBlueprint.route('/QualityTest/Stop', methods=['POST'])
def StopQualityTestService():
    try:
        LoggingService.LogFunctionEntry("StopQualityTestService", "QualityTestController")

        Controller = QualityTestController()
        Result = Controller.StopQualityTestService()

        LoggingService.LogInfo(f"StopQualityTestService completed: {Result.get('Success', False)}", "QualityTestController", "StopQualityTestService")
        return jsonify(Result)

    except Exception as e:
        ErrorMsg = f"Exception in StopQualityTestService endpoint: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "StopQualityTestService")
        return jsonify({
            "Success": False,
            "Message": "Failed to stop quality test service",
            "Error": ErrorMsg
        }), 500

@QualityTestBlueprint.route('/QualityTest/Retry', methods=['POST'])
def RetryQualityTest():
    try:
        LoggingService.LogFunctionEntry("RetryQualityTest", "QualityTestController")

        Controller = QualityTestController()
        Data = request.get_json()
        JobId = Data.get('JobId') if Data else None

        if not JobId:
            return jsonify({"Success": False, "Message": "JobId required"}), 400

        Result = Controller.RetryQualityTest(JobId)

        LoggingService.LogInfo(f"RetryQualityTest completed: {Result.get('Success', False)}", "QualityTestController", "RetryQualityTest")
        return jsonify(Result)

    except Exception as e:
        ErrorMsg = f"Exception in RetryQualityTest endpoint: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "RetryQualityTest")
        return jsonify({
            "Success": False,
            "Message": "Failed to retry quality test",
            "Error": ErrorMsg
        }), 500

@QualityTestBlueprint.route('/api/QualityTesting/History', methods=['GET'])
def GetQualityTestHistory():
    try:
        Controller = QualityTestController()
        Page = request.args.get('Page', 1, type=int)
        Limit = request.args.get('Limit', 10, type=int)

        if Page < 1:
            Page = 1
        if Limit < 1 or Limit > 50:
            Limit = 10

        Result = Controller.GetQualityTestHistory(Page, Limit)
        return jsonify(Result)
    except Exception as e:
        ErrorMsg = f"Exception in GetQualityTestHistory endpoint: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "GetQualityTestHistory")
        return jsonify({"Success": False, "Message": "Failed to get quality test history", "Error": ErrorMsg}), 500

@QualityTestBlueprint.route('/api/QualityTesting/Progress', methods=['GET'])
def GetQualityTestProgress():
    try:
        Controller = QualityTestController()
        Result = Controller.GetQualityTestProgress()
        return jsonify(Result)
    except Exception as e:
        ErrorMsg = f"Exception in GetQualityTestProgress endpoint: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "GetQualityTestProgress")
        return jsonify({"Success": False, "Message": "Failed to get quality test progress", "Error": ErrorMsg}), 500

@QualityTestBlueprint.route('/api/QualityTest/CompareStills', methods=['GET'])
def CompareStills():
    try:
        Timestamp = float(request.args.get('ts') or 60.0)
        SourcePath = request.args.get('source_path')
        TranscodedPath = request.args.get('transcoded_path')
        AttemptId = int(request.args.get('attempt') or 0)
        ViewMode = (request.args.get('view') or 'tv_fair').strip().lower()
        if ViewMode not in ('tv_fair', 'native'):
            ViewMode = 'tv_fair'
        from Features.QualityTesting.QualityTestingBusinessService import QualityTestingBusinessService
        Svc = QualityTestingBusinessService(DatabaseManagerInstance=DatabaseManager())

        if SourcePath and TranscodedPath:
            Result = Svc.GenerateComparisonStillsFromPaths(SourcePath, TranscodedPath, Timestamp, ViewMode)
        elif AttemptId > 0:
            Result = Svc.GenerateComparisonStills(AttemptId, Timestamp, ViewMode)
        else:
            return jsonify({'Success': False, 'ErrorMessage': 'either `attempt` or (`source_path` AND `transcoded_path`) required'}), 400

        if not Result.get('Success'):
            return jsonify(Result), 200
        Result['SourceUrl'] = f"/api/QualityTest/CompareStill/{Result['SourceFilename']}"
        Result['TranscodedUrl'] = f"/api/QualityTest/CompareStill/{Result['TranscodedFilename']}"
        return jsonify(Result)
    except Exception as e:
        ErrorMsg = f"CompareStills failed: {e}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "CompareStills")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@QualityTestBlueprint.route('/api/QualityTest/CompareStillsBatch', methods=['GET'])
def CompareStillsBatch():
    """Multi-timestamp variant of CompareStills. Reads the configured timestamp
    set from SystemSettings (`VmafStillCaptureTimestamps`, default 60,300,600,900),
    extracts/caches one source+transcoded pair per timestamp, returns a list
    so the UI can render a thumbnail strip without N round-trips."""
    try:
        SourcePath = request.args.get('source_path')
        TranscodedPath = request.args.get('transcoded_path')
        AttemptId = int(request.args.get('attempt') or 0)
        ViewMode = (request.args.get('view') or 'tv_fair').strip().lower()
        if ViewMode not in ('tv_fair', 'native'):
            ViewMode = 'tv_fair'
        TsParam = request.args.get('timestamps') or ''

        from Features.QualityTesting.QualityTestingBusinessService import QualityTestingBusinessService
        Svc = QualityTestingBusinessService(DatabaseManagerInstance=DatabaseManager())

        if TsParam.strip():
            TsRaw = TsParam
        else:
            Rows = DatabaseManager().DatabaseService.ExecuteQuery(
                "SELECT SettingValue FROM SystemSettings WHERE SettingKey = %s",
                ('VmafStillCaptureTimestamps',),
            )
            TsRaw = (Rows[0]['SettingValue'] if Rows else '60,300,600,900') or '60,300,600,900'
        try:
            Timestamps = [float(X.strip()) for X in TsRaw.split(',') if X.strip()]
        except ValueError:
            Timestamps = [60.0, 300.0, 600.0, 900.0]
        if not Timestamps:
            return jsonify({'Success': False, 'ErrorMessage': 'no timestamps configured'}), 400

        Items = []
        FirstError = None
        for Ts in Timestamps:
            if SourcePath and TranscodedPath:
                Result = Svc.GenerateComparisonStillsFromPaths(SourcePath, TranscodedPath, Ts, ViewMode)
            elif AttemptId > 0:
                Result = Svc.GenerateComparisonStills(AttemptId, Ts, ViewMode)
            else:
                return jsonify({'Success': False, 'ErrorMessage': 'either `attempt` or (`source_path` AND `transcoded_path`) required'}), 400

            if Result.get('Success'):
                Items.append({
                    'Ts': Ts,
                    'SourceUrl': f"/api/QualityTest/CompareStill/{Result['SourceFilename']}",
                    'TranscodedUrl': f"/api/QualityTest/CompareStill/{Result['TranscodedFilename']}",
                    'ViewMode': Result.get('ViewMode', ViewMode),
                })
            else:
                if FirstError is None:
                    FirstError = Result.get('ErrorMessage', 'extraction failed')
                LoggingService.LogWarning(
                    f"CompareStillsBatch: ts={Ts} failed -- {Result.get('ErrorMessage')}",
                    "QualityTestController", "CompareStillsBatch",
                )

        if not Items:
            return jsonify({'Success': False, 'ErrorMessage': FirstError or 'all timestamps failed'}), 200

        return jsonify({
            'Success': True,
            'ViewMode': ViewMode,
            'Items': Items,
            'PartialFailureCount': len(Timestamps) - len(Items),
        })
    except Exception as e:
        ErrorMsg = f"CompareStillsBatch failed: {e}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "CompareStillsBatch")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@QualityTestBlueprint.route('/api/QualityTest/CompareStill/<Filename>', methods=['GET'])
def ServeCompareStill(Filename):
    from flask import send_from_directory, abort
    if '..' in Filename or '/' in Filename or '\\' in Filename:
        abort(400)
    from Features.QualityTesting.QualityTestingBusinessService import QualityTestingBusinessService
    Svc = QualityTestingBusinessService()
    CacheDir = Svc._GetComparisonCacheDir()
    if not os.path.exists(os.path.join(CacheDir, Filename)):
        abort(404)
    return send_from_directory(CacheDir, Filename)


@QualityTestBlueprint.route('/VmafCompare', methods=['GET'])
def VmafComparePage():
    from flask import render_template
    AttemptId = request.args.get('attempt')
    Timestamp = request.args.get('ts', '60')
    return render_template('VmafCompare.html', AttemptId=AttemptId, Timestamp=Timestamp)


@QualityTestBlueprint.route('/api/QualityTest/RecentAttempts', methods=['GET'])
def RecentAttempts():
    """Paginated list of recent TranscodeAttempts to populate the comparison
    page's browseable picker. Returns most-recent first, with the data the
    operator needs to choose what to inspect."""
    try:
        Page = max(1, int(request.args.get('page', 1)))
        PageSize = max(1, min(50, int(request.args.get('pageSize', 10))))
        Offset = (Page - 1) * PageSize
        Db = DatabaseManager().DatabaseService

        Total = Db.ExecuteQuery("SELECT COUNT(*) AS N FROM TranscodeAttempts")[0]['N']
        Rows = Db.ExecuteQuery(
            """
            SELECT ta.Id, ta.FilePath, ta.ProfileName, ta.AttemptDate,
                   ta.Success, ta.FileReplaced, ta.Disposition, ta.DispositionReason,
                   ta.VMAF, ta.OldSizeBytes, ta.NewSizeBytes,
                   ta.MediaFileId, ta.TestVariantSetId, ta.TestVariantName,
                   tvs.Name AS TestVariantSetName
            FROM TranscodeAttempts ta
            LEFT JOIN TestVariantSets tvs ON ta.TestVariantSetId = tvs.Id
            ORDER BY ta.AttemptDate DESC
            LIMIT %s OFFSET %s
            """,
            (PageSize, Offset),
        )
        return jsonify({
            'Success': True,
            'Page': Page,
            'PageSize': PageSize,
            'Total': Total,
            'TotalPages': (Total + PageSize - 1) // PageSize,
            'Rows': [
                {
                    'Id': R['Id'],
                    'FilePath': R['FilePath'],
                    'FileName': os.path.basename(R['FilePath'] or ''),
                    'ProfileName': R['ProfileName'],
                    'AttemptDate': R['AttemptDate'].isoformat() if R['AttemptDate'] else None,
                    'Success': R['Success'],
                    'FileReplaced': R['FileReplaced'],
                    'Disposition': R['Disposition'],
                    'DispositionReason': R['DispositionReason'],
                    'VMAF': float(R['VMAF']) if R['VMAF'] is not None else None,
                    'OldSizeMB': round((R['OldSizeBytes'] or 0) / (1024 * 1024), 1),
                    'NewSizeMB': round((R['NewSizeBytes'] or 0) / (1024 * 1024), 1),
                    'MediaFileId': R.get('MediaFileId'),
                    'TestVariantSetId': R.get('TestVariantSetId'),
                    'TestVariantName': R.get('TestVariantName'),
                    'TestVariantSetName': R.get('TestVariantSetName'),
                }
                for R in Rows
            ],
        })
    except Exception as e:
        ErrorMsg = f"RecentAttempts failed: {e}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "RecentAttempts")
        return jsonify({'Success': False, 'ErrorMessage': ErrorMsg}), 500


@QualityTestBlueprint.route('/api/QualityTest/VariantSets', methods=['GET'])
def VariantSetsList():
    """List all TestVariantSets for the queue admission UI dropdown."""
    try:
        Rows = DatabaseManager().DatabaseService.ExecuteQuery(
            "SELECT Id, Name, Description, jsonb_array_length(VariantsJson) AS VariantCount FROM TestVariantSets ORDER BY Id"
        )
        return jsonify({
            'Success': True,
            'Sets': [
                {
                    'Id': R['Id'],
                    'Name': R['Name'],
                    'Description': R.get('Description'),
                    'VariantCount': R.get('VariantCount') or 0,
                }
                for R in Rows
            ],
        })
    except Exception as e:
        ErrorMsg = f"VariantSetsList failed: {e}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "VariantSetsList")
        return jsonify({'Success': False, 'ErrorMessage': ErrorMsg}), 500


@QualityTestBlueprint.route('/api/QualityTest/QueueTestRun', methods=['POST'])
def QueueTestRun():
    """Admit one or more files into the transcode queue for multi-variant testing.
    Body: {"VariantSetId": <int>, "FilePaths": ["...", "..."]}.
    Each file must already exist as a MediaFiles row (so it has been scanned and
    has an AssignedProfile). Returns per-file accept/reject status."""
    try:
        Data = request.get_json() or {}
        VariantSetId = Data.get('VariantSetId')
        FilePaths = Data.get('FilePaths') or []
        if not isinstance(VariantSetId, int):
            return jsonify({'Success': False, 'ErrorMessage': 'VariantSetId (int) required'}), 400
        if not isinstance(FilePaths, list) or not FilePaths:
            return jsonify({'Success': False, 'ErrorMessage': 'FilePaths (non-empty list) required'}), 400

        Db = DatabaseManager().DatabaseService
        SetRows = Db.ExecuteQuery(
            "SELECT Id, Name FROM TestVariantSets WHERE Id = %s",
            (VariantSetId,),
        )
        if not SetRows:
            return jsonify({'Success': False, 'ErrorMessage': f'TestVariantSet {VariantSetId} not found'}), 400
        SetName = SetRows[0].get('Name')

        DefaultProfileRows = Db.ExecuteQuery(
            "SELECT SettingValue FROM SystemSettings WHERE SettingKey = 'DefaultProfileName'"
        )
        DefaultProfileName = DefaultProfileRows[0].get('SettingValue') if DefaultProfileRows else None

        Accepted = []
        Rejected = []
        for Raw in FilePaths:
            Path_ = (Raw or '').strip()
            if not Path_:
                continue
            MfRows = Db.ExecuteQuery(
                "SELECT Id, AssignedProfile, SizeMB, StorageRootId, RelativePath FROM MediaFiles WHERE FilePath = %s",
                (Path_,),
            )
            if not MfRows:
                Rejected.append({'FilePath': Path_, 'Reason': 'MediaFiles row not found (file may not be scanned)'})
                continue
            Mf = MfRows[0]
            Profile = Mf.get('AssignedProfile') or DefaultProfileName
            if not Profile:
                Rejected.append({'FilePath': Path_, 'Reason': 'No AssignedProfile on MediaFile and no DefaultProfileName set'})
                continue
            MfStorageRootId = Mf.get('StorageRootId')
            MfRelativePath = Mf.get('RelativePath') or ''
            if MfStorageRootId is None or not MfRelativePath:
                Rejected.append({'FilePath': Path_, 'Reason': 'MediaFile missing StorageRootId/RelativePath (re-scan required)'})
                continue
            ExistingRow = Db.ExecuteQuery(
                "SELECT Id FROM TranscodeQueue WHERE StorageRootId = %s AND RelativePath = %s AND Status = 'Pending' AND TestVariantSetId = %s",
                (MfStorageRootId, MfRelativePath, VariantSetId),
            )
            if ExistingRow:
                Rejected.append({'FilePath': Path_, 'Reason': f'already pending for this variant set (queue Id {ExistingRow[0]["Id"]})'})
                continue
            try:
                Db.ExecuteNonQuery(
                    """
                    INSERT INTO TranscodeQueue
                        (StorageRootId, RelativePath, FilePath, FileName, Directory, SizeBytes, SizeMB, Priority, Status,
                         MediaFileId, TestVariantSetId, DateAdded)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Pending', %s, %s, NOW())
                    RETURNING Id
                    """,
                    (
                        MfStorageRootId,
                        MfRelativePath,
                        Path_,
                        os.path.basename(Path_),
                        os.path.dirname(Path_),
                        int((Mf.get('SizeMB') or 0) * 1024 * 1024),
                        Mf.get('SizeMB') or 0,
                        50,
                        Mf.get('Id'),
                        VariantSetId,
                    ),
                )
                NewId = Db.LastInsertId
                Accepted.append({'FilePath': Path_, 'QueueId': NewId, 'Profile': Profile})
            except Exception as InsEx:
                LoggingService.LogException(
                    f"QueueTestRun insert failed for {Path_}",
                    InsEx, "QualityTestController", "QueueTestRun",
                )
                Rejected.append({'FilePath': Path_, 'Reason': f'insert failed: {InsEx}'})

        LoggingService.LogInfo(
            f"QueueTestRun: VariantSet={SetName!r} ({VariantSetId}); accepted={len(Accepted)}, rejected={len(Rejected)}",
            "QualityTestController", "QueueTestRun",
        )
        return jsonify({
            'Success': True,
            'VariantSetId': VariantSetId,
            'VariantSetName': SetName,
            'AcceptedCount': len(Accepted),
            'RejectedCount': len(Rejected),
            'Accepted': Accepted,
            'Rejected': Rejected,
        })
    except Exception as e:
        ErrorMsg = f"QueueTestRun failed: {e}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "QueueTestRun")
        return jsonify({'Success': False, 'ErrorMessage': ErrorMsg}), 500


@QualityTestBlueprint.route('/api/QualityTest/TestBench/List', methods=['GET'])
def TestBenchList():
    """Enumerate Scripts/Smoke/*.results.json sidecars for the operator's test-bench
    picker. Read-only file-system enumeration -- smoke tests live outside the DB
    on purpose (see vmaf-comparison-slider.feature.md). Most-recently-modified first."""
    try:
        from datetime import datetime
        RepoRoot = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        SmokeDir = os.path.join(RepoRoot, 'Scripts', 'Smoke')
        Rows = []
        if os.path.isdir(SmokeDir):
            Entries = [E for E in os.listdir(SmokeDir) if E.endswith('.results.json')]
            for FN in sorted(Entries, key=lambda N: os.path.getmtime(os.path.join(SmokeDir, N)), reverse=True):
                Full = os.path.join(SmokeDir, FN)
                try:
                    with open(Full, 'r', encoding='utf-8') as F:
                        Data = json.load(F)
                    Src = Data.get('source') or (Data.get('Source') or {}).get('Path') or ''
                    Variants = Data.get('variants') or Data.get('Variants') or []
                    Rows.append({
                        'Filename': FN,
                        'TestName': FN.replace('.results.json', ''),
                        'SourcePath': Src,
                        'SourceFileName': os.path.basename(Src) if Src else '(unknown)',
                        'VariantCount': len(Variants),
                        'ModifiedAt': datetime.fromtimestamp(os.path.getmtime(Full)).isoformat(timespec='seconds'),
                    })
                except Exception as Inner:
                    LoggingService.LogWarning(f"TestBench skip unparseable {FN}: {Inner}", "QualityTestController", "TestBenchList")
        return jsonify({'Success': True, 'Rows': Rows})
    except Exception as e:
        ErrorMsg = f"TestBenchList failed: {e}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "TestBenchList")
        return jsonify({'Success': False, 'ErrorMessage': ErrorMsg}), 500


@QualityTestBlueprint.route('/api/QualityTest/TestBench/Detail', methods=['GET'])
def TestBenchDetail():
    """Return one sidecar's parsed contents with variant fields normalized to
    PascalCase keys. The compare slider uses Source + each Variant.OutPath via
    the existing raw-paths CompareStills endpoint."""
    try:
        FN = request.args.get('file', '')
        if not FN or '..' in FN or '/' in FN or '\\' in FN or not FN.endswith('.results.json'):
            return jsonify({'Success': False, 'ErrorMessage': 'invalid file parameter'}), 400
        RepoRoot = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        Full = os.path.join(RepoRoot, 'Scripts', 'Smoke', FN)
        if not os.path.exists(Full):
            return jsonify({'Success': False, 'ErrorMessage': f'sidecar not found: {FN}'}), 404
        with open(Full, 'r', encoding='utf-8') as F:
            Data = json.load(F)
        Src = Data.get('source') or (Data.get('Source') or {}).get('Path') or ''
        SrcSize = Data.get('source_size_bytes') or Data.get('SourceSizeBytes')
        Variants = Data.get('variants') or Data.get('Variants') or []
        Normalized = []
        for V in Variants:
            Normalized.append({
                'Name': V.get('name') or V.get('Name') or '',
                'Label': V.get('label') or V.get('Label') or '',
                'OutPath': V.get('out_path') or V.get('OutPath') or '',
                'Scale': V.get('scale') or V.get('Scale') or '',
                'Crf': V.get('crf') if V.get('crf') is not None else V.get('Crf'),
                'BitrateKbps': V.get('bitrate_kbps') if V.get('bitrate_kbps') is not None else V.get('BitrateKbps'),
                'SizeBytes': V.get('size_bytes') if V.get('size_bytes') is not None else V.get('SizeBytes'),
                'DurationSeconds': V.get('duration_seconds') if V.get('duration_seconds') is not None else V.get('DurationSeconds'),
                'Vmaf': V.get('vmaf') if V.get('vmaf') is not None else V.get('Vmaf'),
            })
        return jsonify({
            'Success': True,
            'Filename': FN,
            'TestName': FN.replace('.results.json', ''),
            'Source': Src,
            'SourceFileName': os.path.basename(Src) if Src else '(unknown)',
            'SourceSizeBytes': SrcSize,
            'Variants': Normalized,
        })
    except Exception as e:
        ErrorMsg = f"TestBenchDetail failed: {e}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "TestBenchDetail")
        return jsonify({'Success': False, 'ErrorMessage': ErrorMsg}), 500


@QualityTestBlueprint.route('/api/QualityTesting/LogError', methods=['POST'])
def LogQualityTestError():
    try:
        Controller = QualityTestController()
        Data = request.get_json()

        if not Data:
            return jsonify({"Success": False, "Message": "No data provided"}), 400

        ErrorMessage = Data.get('ErrorMessage', '')
        ErrorContext = Data.get('ErrorContext', '')
        RequestUrl = Data.get('RequestUrl', '')

        Result = Controller.LogError(ErrorMessage, ErrorContext, RequestUrl)
        return jsonify(Result)
    except Exception as e:
        ErrorMsg = f"Exception in LogQualityTestError endpoint: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "LogQualityTestError")
        return jsonify({"Success": False, "Message": "Failed to log error", "Error": ErrorMsg}), 500

@QualityTestBlueprint.route('/api/QualityTest/AddToQueue', methods=['POST'])
def AddToQueue():
    try:
        Controller = QualityTestController()
        Data = request.get_json()

        if not Data:
            return jsonify({"Success": False, "Message": "No data provided"}), 400

        TranscodeAttemptId = Data.get('TranscodeAttemptId')
        if not TranscodeAttemptId:
            return jsonify({"Success": False, "Message": "TranscodeAttemptId required"}), 400

        Result = Controller.AddToQueue(TranscodeAttemptId)
        return jsonify(Result)
    except Exception as e:
        ErrorMsg = f"Exception in AddToQueue endpoint: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "AddToQueue")
        return jsonify({"Success": False, "Message": "Failed to add to queue", "Error": ErrorMsg}), 500

@QualityTestBlueprint.route('/api/QualityTest/Skip', methods=['POST'])
def SkipQualityTest():
    """Skip quality test for a transcode attempt"""
    try:
        Controller = QualityTestController()
        Data = request.get_json()

        if not Data:
            return jsonify({"Success": False, "Message": "No data provided"}), 400

        TranscodeAttemptId = Data.get('TranscodeAttemptId')
        if not TranscodeAttemptId:
            return jsonify({"Success": False, "Message": "TranscodeAttemptId required"}), 400

        from Features.QualityTesting.QualityTestingBusinessService import QualityTestingBusinessService
        business_service = QualityTestingBusinessService(Controller.DatabaseManager)
        Result = business_service.SkipQualityTest(TranscodeAttemptId)

        return jsonify(Result)
    except Exception as e:
        ErrorMsg = f"Exception in SkipQualityTest endpoint: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "SkipQualityTest")
        return jsonify({"Success": False, "Message": "Failed to skip quality test", "Error": ErrorMsg}), 500

@QualityTestBlueprint.route('/api/QualityTest/CancelActive', methods=['POST'])
def CancelActiveQualityTest():
    """Cancel the currently running quality test"""
    try:
        LoggingService.LogFunctionEntry("CancelActiveQualityTest", "QualityTestController")

        Controller = QualityTestController()

        # Use the business service to handle the cancel logic
        from Features.QualityTesting.QualityTestingBusinessService import QualityTestingBusinessService
        business_service = QualityTestingBusinessService(Controller.DatabaseManager)
        Result = business_service.CancelActiveQualityTest()

        LoggingService.LogInfo(f"CancelActiveQualityTest completed: {Result.get('Success', False)}", "QualityTestController", "CancelActiveQualityTest")
        return jsonify(Result)

    except Exception as e:
        ErrorMsg = f"Exception in CancelActiveQualityTest endpoint: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestController", "CancelActiveQualityTest")
        return jsonify({
            "Success": False,
            "Message": "Failed to cancel quality test",
            "Error": ErrorMsg
        }), 500

@QualityTestBlueprint.route('/api/QualityTest/StopAfterCurrent', methods=['POST'])
def StopQualityTestAfterCurrent():
    """Graceful stop - allow current quality test to complete before stopping."""
    try:
        LoggingService.LogFunctionEntry("StopQualityTestAfterCurrent", "QualityTestController")

        # Update ServiceStatus to GracefulStop
        from Repositories.DatabaseManager import DatabaseManager
        db_manager = DatabaseManager()

        success = db_manager.UpdateServiceStatus("QualityTestService", {
            'Status': 'GracefulStop',
            'IsProcessing': False
        })

        if success:
            LoggingService.LogInfo("Graceful stop requested - quality testing will complete current job before stopping",
                                 "QualityTestController", "StopQualityTestAfterCurrent")
            return jsonify({
                "Success": True,
                "Message": "Graceful stop requested - quality testing will complete current job before stopping",
                "Status": "GracefulStop"
            })
        else:
            LoggingService.LogError("Failed to request graceful stop", "QualityTestController", "StopQualityTestAfterCurrent")
            return jsonify({
                "Success": False,
                "ErrorMessage": "Failed to request graceful stop"
            }), 500

    except Exception as e:
        errorMsg = f"Exception requesting graceful stop: {str(e)}"
        LoggingService.LogException(errorMsg, e, "QualityTestController", "StopQualityTestAfterCurrent")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500

@QualityTestBlueprint.route('/api/QualityTest/Pause', methods=['POST'])
def PauseQualityTest():
    """Pause quality test queue and migrate running jobs to E-cores (Game Mode)."""
    try:
        LoggingService.LogFunctionEntry("PauseQualityTest", "QualityTestController")

        from Repositories.DatabaseManager import DatabaseManager
        db_manager = DatabaseManager()

        success = db_manager.UpdateServiceStatus("QualityTestService", {
            'Status': 'Paused',
            'IsProcessing': False
        })

        # Migrate active FFmpeg jobs to E-cores
        try:
            from Services.CpuAffinityService import GetCpuAffinityServiceInstance
            AffinityService = GetCpuAffinityServiceInstance()
            if AffinityService.CpuAffinityEnabled:
                AffinityService.MigrateActiveJobsToTier("efficiency")
        except Exception as MigrationError:
            LoggingService.LogWarning(f"Failed to migrate jobs to E-cores on pause: {MigrationError}",
                                     "QualityTestController", "PauseQualityTest")

        if success:
            LoggingService.LogInfo("Quality testing paused successfully",
                                 "QualityTestController", "PauseQualityTest")
            return jsonify({
                "Success": True,
                "Message": "Quality testing paused - running jobs moved to E-cores"
            })
        else:
            return jsonify({
                "Success": False,
                "ErrorMessage": "Failed to pause quality testing"
            }), 500

    except Exception as e:
        errorMsg = f"Exception pausing quality testing: {str(e)}"
        LoggingService.LogException(errorMsg, e, "QualityTestController", "PauseQualityTest")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500

@QualityTestBlueprint.route('/api/QualityTest/Resume', methods=['POST'])
def ResumeQualityTest():
    """Resume quality test queue and restore jobs to original cores."""
    try:
        LoggingService.LogFunctionEntry("ResumeQualityTest", "QualityTestController")

        from Repositories.DatabaseManager import DatabaseManager
        db_manager = DatabaseManager()

        # Restore active jobs to their original core tier
        try:
            from Services.CpuAffinityService import GetCpuAffinityServiceInstance
            AffinityService = GetCpuAffinityServiceInstance()
            if AffinityService.CpuAffinityEnabled:
                AffinityService.MigrateActiveJobsToTier("restore")
        except Exception as MigrationError:
            LoggingService.LogWarning(f"Failed to restore jobs on resume: {MigrationError}",
                                     "QualityTestController", "ResumeQualityTest")

        success = db_manager.UpdateServiceStatus("QualityTestService", {
            'Status': 'Running',
            'IsProcessing': True
        })

        if success:
            LoggingService.LogInfo("Quality testing resumed successfully",
                                 "QualityTestController", "ResumeQualityTest")
            return jsonify({
                "Success": True,
                "Message": "Quality testing resumed - queue processing will continue"
            })
        else:
            return jsonify({
                "Success": False,
                "ErrorMessage": "Failed to resume quality testing"
            }), 500

    except Exception as e:
        errorMsg = f"Exception resuming quality testing: {str(e)}"
        LoggingService.LogException(errorMsg, e, "QualityTestController", "ResumeQualityTest")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500
