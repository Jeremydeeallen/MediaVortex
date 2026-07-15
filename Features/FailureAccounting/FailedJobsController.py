from flask import Blueprint, jsonify, request, render_template
from Core.Logging.LoggingService import LoggingService
from Features.FailureAccounting.Repositories.FailedJobsRepository import FailedJobsRepository


FailedJobsBlueprint = Blueprint('FailedJobs', __name__)


# directive: failure-accounting | # see failure-accounting.C8
def _Envelope(Success, Data=None, Message=None, Status=200):
    """Standard MediaVortex envelope so the page JS can render uniform error toasts."""
    Resp = {'Success': bool(Success)}
    if Message is not None:
        Resp['Message'] = str(Message)
    if Data is not None:
        Resp['Data'] = Data
    return jsonify(Resp), Status


@FailedJobsBlueprint.route('/FailedJobs', methods=['GET'])
# directive: failure-accounting | # see failure-accounting.C8
def RenderPage():
    """Render the operator surface."""
    return render_template('FailedJobs.html')


@FailedJobsBlueprint.route('/api/FailedJobs', methods=['GET'])
# directive: failure-accounting | # see failure-accounting.C8
def ListCappedJobs():
    """Paginated list of capped MediaFiles. Query: limit, offset, search, sortBy, sortDir."""
    try:
        Limit = max(1, min(500, int(request.args.get('limit', 100))))
        Offset = max(0, int(request.args.get('offset', 0)))
        Search = request.args.get('search') or None
        SortBy = request.args.get('sortBy', 'LastAttemptDate')
        SortDir = request.args.get('sortDir', 'DESC')
        Repo = FailedJobsRepository()
        Rows = Repo.GetCappedJobs(Limit=Limit, Offset=Offset, Search=Search, SortBy=SortBy, SortDir=SortDir)
        Total = Repo.CountCapped()
        return _Envelope(True, Data={
            'Items': [
                {
                    'MediaFileId': R.MediaFileId,
                    'FileName': R.FileName,
                    'FilePath': R.FilePath,
                    'FailureCount': R.FailureCount,
                    'LastErrorMessage': R.LastErrorMessage,
                    'LastAttemptDate': R.LastAttemptDate.isoformat() if R.LastAttemptDate else None,
                    'AssignedProfile': R.AssignedProfile,
                    'LastWorkerName': R.LastWorkerName,
                    'SizeMB': R.SizeMB,
                    'LastFailureResetAt': R.LastFailureResetAt.isoformat() if R.LastFailureResetAt else None,
                }
                for R in Rows
            ],
            'TotalCount': Total,
            'Limit': Limit,
            'Offset': Offset,
        })
    except Exception as Ex:
        LoggingService.LogException("ListCappedJobs failed", Ex, "FailedJobsController", "ListCappedJobs")
        return _Envelope(False, Message=str(Ex), Status=500)


@FailedJobsBlueprint.route('/api/FailedJobs/<int:MediaFileId>/Attempts', methods=['GET'])
# directive: failure-accounting | # see failure-accounting.C8
def GetAttemptHistory(MediaFileId):
    """Return TranscodeAttempts history for a single MediaFile."""
    try:
        Rows = FailedJobsRepository().GetAttemptHistory(MediaFileId)
        return _Envelope(True, Data={'Attempts': [dict(R) for R in Rows]})
    except Exception as Ex:
        LoggingService.LogException("GetAttemptHistory failed", Ex, "FailedJobsController", "GetAttemptHistory")
        return _Envelope(False, Message=str(Ex), Status=500)


@FailedJobsBlueprint.route('/api/FailedJobs/<int:MediaFileId>/Reset', methods=['POST'])
# directive: failure-accounting | # see failure-accounting.C7
def ResetFailureBudget(MediaFileId):
    """Operator-Reset: writes FailureBudgetResets audit row + bumps MediaFiles.LastFailureResetAt."""
    try:
        Body = request.get_json(silent=True) or {}
        OperatorName = str(Body.get('OperatorName') or request.remote_addr or 'operator').strip() or 'operator'
        FailedJobsRepository().ResetFailureBudget(MediaFileId, OperatorName)
        return _Envelope(True, Message="Reset OK", Data={'MediaFileId': MediaFileId})
    except Exception as Ex:
        LoggingService.LogException("ResetFailureBudget failed", Ex, "FailedJobsController", "ResetFailureBudget")
        return _Envelope(False, Message=str(Ex), Status=500)


@FailedJobsBlueprint.route('/api/FailedJobs/ResetBulk', methods=['POST'])
# directive: transcode-flow-canonical -- bulk reset endpoint; body {MediaFileIds: [...], OperatorName}
def ResetFailureBudgetBulk():
    """Reset a caller-supplied list of MediaFileIds in a single call."""
    try:
        Body = request.get_json(silent=True) or {}
        Ids = Body.get('MediaFileIds') or []
        if not isinstance(Ids, list) or not all(isinstance(I, int) for I in Ids):
            return _Envelope(False, Message="MediaFileIds must be a list of integers", Status=400)
        if not Ids:
            return _Envelope(True, Message="No MediaFileIds provided; nothing to reset", Data={'ResetCount': 0})
        OperatorName = str(Body.get('OperatorName') or request.remote_addr or 'operator').strip() or 'operator'
        Count = FailedJobsRepository().ResetFailureBudgetBulk(Ids, OperatorName)
        return _Envelope(True, Message=f"Reset {Count} MediaFile(s)", Data={'ResetCount': Count})
    except Exception as Ex:
        LoggingService.LogException("ResetFailureBudgetBulk failed", Ex, "FailedJobsController", "ResetFailureBudgetBulk")
        return _Envelope(False, Message=str(Ex), Status=500)


@FailedJobsBlueprint.route('/api/FailedJobs/Groups', methods=['GET'])
# directive: transcode-flow-canonical -- series-level grouping for the /FailedJobs page
def ListGroups():
    """Return capped jobs grouped by top-level folder (series or movie title)."""
    try:
        Groups = FailedJobsRepository().GetCappedJobsGrouped()
        return _Envelope(True, Data={'Groups': Groups})
    except Exception as Ex:
        LoggingService.LogException("ListGroups failed", Ex, "FailedJobsController", "ListGroups")
        return _Envelope(False, Message=str(Ex), Status=500)


@FailedJobsBlueprint.route('/api/FailedJobs/Count', methods=['GET'])
# directive: failure-accounting | # see failure-accounting.C7
def Count():
    """Used by the nav badge."""
    try:
        return _Envelope(True, Data={'Count': FailedJobsRepository().CountCapped()})
    except Exception as Ex:
        LoggingService.LogException("Count failed", Ex, "FailedJobsController", "Count")
        return _Envelope(False, Message=str(Ex), Status=500)
