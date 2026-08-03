from flask import Blueprint, request, jsonify

from Core.Logging.LoggingService import LoggingService
from Core.Path.Path import Path, PathError
from Core.Path.PathStorageRoots import GetStorageRoots


SyncPathBlueprint = Blueprint('SyncPath', __name__)


# directive: ingest-pipeline-kiss
@SyncPathBlueprint.route('/api/Sync/Path', methods=['POST'])
def SyncPath():
    Body = request.get_json(silent=True) or {}
    CanonicalPath = (Body.get('CanonicalPath') or '').strip()
    if not CanonicalPath:
        return jsonify({'Success': False, 'Message': 'CanonicalPath is required'}), 400

    try:
        Parsed = Path.FromLegacyString(CanonicalPath, GetStorageRoots())
    except PathError as Ex:
        return jsonify({'Success': False, 'Message': f'Unknown storage root or invalid path: {Ex}'}), 400
    if Parsed.StorageRootId is None:
        return jsonify({'Success': False, 'Message': f'Unknown storage root prefix in: {CanonicalPath}'}), 400

    from Features.FileScanning.FileScanningBusinessService import FileScanningBusinessService
    Svc = FileScanningBusinessService()
    Result = Svc.StartScanning(CanonicalPath, Recursive=True)
    if not Result or not Result.get('Success'):
        Msg = (Result or {}).get('Message', 'unknown')
        LoggingService.LogWarning(f"SyncPath: StartScanning refused for {CanonicalPath}: {Msg}", 'SyncPathController', 'SyncPath')
        return jsonify({'Success': False, 'Message': Msg}), 409
    LoggingService.LogInfo(f"SyncPath: enqueued scan for {CanonicalPath}", 'SyncPathController', 'SyncPath')
    return jsonify({'Success': True, 'ScanJobId': Result.get('JobId') or Svc.CurrentJobId, 'Message': 'Scan enqueued'}), 200
