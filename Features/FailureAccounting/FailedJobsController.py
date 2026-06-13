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


@FailedJobsBlueprint.route('/api/FailedJobs/Count', methods=['GET'])
# directive: failure-accounting | # see failure-accounting.C7
def Count():
    """Used by the nav badge."""
    try:
        return _Envelope(True, Data={'Count': FailedJobsRepository().CountCapped()})
    except Exception as Ex:
        LoggingService.LogException("Count failed", Ex, "FailedJobsController", "Count")
        return _Envelope(False, Message=str(Ex), Status=500)
