from flask import Blueprint, render_template, jsonify

from Core.Logging.LoggingService import LoggingService
from Features.Failures.FailuresRepository import FailuresRepository
from Features.MediaFiles.MediaFilesRepository import MediaFilesRepository


FailuresBlueprint = Blueprint('Failures', __name__)


# directive: ingest-pipeline-kiss
@FailuresBlueprint.route('/Failures', methods=['GET'])
def FailuresPage():
    return render_template('Failures.html')


# directive: ingest-pipeline-kiss
@FailuresBlueprint.route('/api/Failures', methods=['GET'])
def GetFailures():
    Repo = FailuresRepository()
    Probe = Repo.GetProbeFailures()
    Scan = Repo.GetScanFailures()
    return jsonify({'Success': True, 'Probe': Probe, 'Scan': Scan}), 200


# directive: ingest-pipeline-kiss
@FailuresBlueprint.route('/api/Failures/<int:MediaFileId>/Retry', methods=['POST'])
def RetryProbeFailure(MediaFileId: int):
    Mfr = MediaFilesRepository()
    Affected = Mfr.DatabaseService.ExecuteNonQuery(
        "UPDATE MediaFiles SET FFprobeFailureCount = 0, LastFFprobeError = NULL, NeedsReprobe = TRUE "
        "WHERE Id = %s",
        (MediaFileId,),
    )
    if int(Affected or 0) == 0:
        return jsonify({'Success': False, 'Message': f'MediaFile Id={MediaFileId} not found'}), 404
    LoggingService.LogInfo(f"Retry probe failure MediaFileId={MediaFileId}", 'FailuresController', 'RetryProbeFailure')
    return jsonify({'Success': True, 'Message': f'Reset MediaFileId={MediaFileId}; ProbeWorker will re-probe next tick'}), 200


# directive: ingest-pipeline-kiss
@FailuresBlueprint.route('/api/Failures/Scan/<JobId>/Retry', methods=['POST'])
def RetryScanFailure(JobId: str):
    Repo = FailuresRepository()
    Canonical = Repo.GetCanonicalPathForScanJob(JobId)
    if not Canonical:
        return jsonify({'Success': False, 'Message': f'Scan JobId={JobId} not found'}), 404
    from Features.FileScanning.FileScanningBusinessService import FileScanningBusinessService
    Svc = FileScanningBusinessService()
    Result = Svc.StartScanning(Canonical, Recursive=True)
    if not Result or not Result.get('Success'):
        Msg = (Result or {}).get('Message', 'unknown')
        return jsonify({'Success': False, 'Message': Msg}), 409
    return jsonify({'Success': True, 'ScanJobId': Svc.CurrentJobId, 'Message': f'Retry enqueued for {Canonical}'}), 200
