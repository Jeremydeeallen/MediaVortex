from flask import Blueprint, request, jsonify

from Core.Logging.LoggingService import LoggingService
from Core.Path.Path import Path, PathError
from Core.Path.PathStorageRoots import GetStorageRoots


IngestWebhookBlueprint = Blueprint('IngestWebhook', __name__)


_TEST_EVENTS = {'Test'}


def _ExtractPath(Payload: dict) -> str:
    EventType = (Payload.get('eventType') or '').strip()
    if EventType in _TEST_EVENTS:
        return ''
    EpisodeFile = Payload.get('episodeFile') or {}
    P = EpisodeFile.get('path')
    if P:
        return str(P).strip()
    MovieFile = Payload.get('movieFile') or {}
    P = MovieFile.get('path')
    if P:
        return str(P).strip()
    Series = Payload.get('series') or {}
    P = Series.get('path')
    if P:
        return str(P).strip()
    Movie = Payload.get('movie') or {}
    P = Movie.get('folderPath') or Movie.get('path')
    if P:
        return str(P).strip()
    return ''


# directive: ingest-pipeline-kiss
@IngestWebhookBlueprint.route('/api/Ingest/Webhook', methods=['POST'])
def IngestWebhook():
    Payload = request.get_json(silent=True) or {}
    EventType = (Payload.get('eventType') or '').strip()
    if EventType in _TEST_EVENTS:
        LoggingService.LogInfo("IngestWebhook: Test event received", 'IngestWebhookController', 'IngestWebhook')
        return jsonify({'Success': True, 'Message': 'Test received'}), 200

    Target = _ExtractPath(Payload)
    if not Target:
        LoggingService.LogWarning(f"IngestWebhook: unrecognized payload shape eventType={EventType!r}", 'IngestWebhookController', 'IngestWebhook')
        return jsonify({'Success': False, 'Message': f'Unrecognized payload shape (eventType={EventType!r})'}), 400

    try:
        Parsed = Path.FromLegacyString(Target, GetStorageRoots())
    except PathError as Ex:
        return jsonify({'Success': False, 'Message': f'Unknown storage root: {Ex}'}), 400
    if Parsed.StorageRootId is None:
        return jsonify({'Success': False, 'Message': f'Unknown storage root prefix in: {Target}'}), 400

    ScanTarget = _ParentFolderCanonical(Target, Parsed)

    from Features.FileScanning.FileScanningBusinessService import FileScanningBusinessService
    Svc = FileScanningBusinessService()
    Result = Svc.StartScanning(ScanTarget, Recursive=True)
    if not Result or not Result.get('Success'):
        Msg = (Result or {}).get('Message', 'unknown')
        if 'ScanAlreadyRunning' in str(Msg):
            return jsonify({'Success': True, 'Message': 'ScanAlreadyRunning', 'ExistingJobId': Svc.CurrentJobId}), 200
        LoggingService.LogWarning(f"IngestWebhook: enqueue failed for {ScanTarget}: {Msg}", 'IngestWebhookController', 'IngestWebhook')
        return jsonify({'Success': False, 'Message': Msg}), 500
    LoggingService.LogInfo(f"IngestWebhook: enqueued scan for {ScanTarget} (eventType={EventType})", 'IngestWebhookController', 'IngestWebhook')
    return jsonify({'Success': True, 'ScanJobId': Svc.CurrentJobId, 'Message': 'Scan enqueued', 'ScanTarget': ScanTarget}), 200


def _ParentFolderCanonical(TargetPath: str, Parsed: Path) -> str:
    Rel = (Parsed.RelativePath or '').rstrip('/').rstrip('\\')
    if not Rel:
        return TargetPath
    LastSep = max(Rel.rfind('/'), Rel.rfind('\\'))
    if LastSep <= 0:
        return TargetPath
    if '.' not in Rel.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]:
        return TargetPath
    ParentRel = Rel[:LastSep]
    from Core.Path.PathStorageRoots import GetPrefixMap
    return Path(Parsed.StorageRootId, ParentRel).CanonicalDisplay(GetPrefixMap())
