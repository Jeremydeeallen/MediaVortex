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
        # directive: bug-0095-failure-classification | # see failure-accounting.C11 -- split rows into Terminal + Transient sections for /FailedJobs
        _Serialize = lambda R: {
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
            'Duration': R.Duration,
            'FailureClass': R.FailureClass,
            'Terminal': R.Terminal,
            'Remediation': R.Remediation,
        }
        Items = [_Serialize(R) for R in Rows]
        return _Envelope(True, Data={
            'Items': Items,
            'TerminalRows': [I for I in Items if I['Terminal']],
            'TransientRows': [I for I in Items if not I['Terminal']],
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


# directive: bug-0095-failure-classification | # see failure-accounting.C10 -- FailureClasses CRUD for /settings operator tuner
@FailedJobsBlueprint.route('/api/FailureClasses', methods=['GET'])
def ListFailureClasses():
    """List all classifier rules ordered by Priority ASC (first-match-wins)."""
    try:
        from Features.FailureAccounting.Repositories.FailureClassesRepository import FailureClassesRepository
        Rows = FailureClassesRepository().ListOrderedByPriority()
        return _Envelope(True, Data={
            'FailureClasses': [
                {
                    'ClassName': R.ClassName,
                    'Priority': R.Priority,
                    'ErrorPattern': R.ErrorPattern,
                    'Terminal': R.Terminal,
                    'Remediation': R.Remediation,
                }
                for R in Rows
            ],
        })
    except Exception as Ex:
        LoggingService.LogException("ListFailureClasses failed", Ex, "FailedJobsController", "ListFailureClasses")
        return _Envelope(False, Message=str(Ex), Status=500)


# directive: bug-0095-failure-classification | # see failure-accounting.C10 -- POSIX-regex validated upsert; refuses invalid pattern
@FailedJobsBlueprint.route('/api/FailureClasses', methods=['POST'])
def UpsertFailureClass():
    """Upsert a classifier rule. Body: {ClassName, Priority, ErrorPattern, Terminal, Remediation}. Refuses uncompilable regex."""
    try:
        import re
        Body = request.get_json(silent=True) or {}
        ClassName = str(Body.get('ClassName') or '').strip()
        if not ClassName:
            return _Envelope(False, Message='ClassName required', Status=400)
        try:
            Priority = int(Body.get('Priority', 9999))
        except (TypeError, ValueError):
            return _Envelope(False, Message='Priority must be integer', Status=400)
        ErrorPattern = str(Body.get('ErrorPattern') or '').strip()
        if not ErrorPattern:
            return _Envelope(False, Message='ErrorPattern required', Status=400)
        try:
            re.compile(ErrorPattern)
        except re.error as RegexEx:
            return _Envelope(False, Message=f'ErrorPattern is not a valid regex: {RegexEx}', Status=400)
        Terminal = bool(Body.get('Terminal', False))
        Remediation = str(Body.get('Remediation') or '').strip()
        if not Remediation:
            return _Envelope(False, Message='Remediation required', Status=400)
        from Features.FailureAccounting.Repositories.FailureClassesRepository import FailureClassesRepository
        FailureClassesRepository().Upsert(ClassName, Priority, ErrorPattern, Terminal, Remediation)
        return _Envelope(True, Message='Saved', Data={'ClassName': ClassName})
    except Exception as Ex:
        LoggingService.LogException("UpsertFailureClass failed", Ex, "FailedJobsController", "UpsertFailureClass")
        return _Envelope(False, Message=str(Ex), Status=500)


# directive: bug-0095-failure-classification | # see failure-accounting.C10 -- refuses delete of unclassified catch-all
@FailedJobsBlueprint.route('/api/FailureClasses/<string:ClassName>', methods=['DELETE'])
def DeleteFailureClass(ClassName: str):
    """Delete a classifier rule. Refuses 'unclassified' catch-all."""
    try:
        from Features.FailureAccounting.Repositories.FailureClassesRepository import FailureClassesRepository
        FailureClassesRepository().Delete(ClassName)
        return _Envelope(True, Message='Deleted', Data={'ClassName': ClassName})
    except ValueError as VE:
        return _Envelope(False, Message=str(VE), Status=400)
    except Exception as Ex:
        LoggingService.LogException("DeleteFailureClass failed", Ex, "FailedJobsController", "DeleteFailureClass")
        return _Envelope(False, Message=str(Ex), Status=500)
