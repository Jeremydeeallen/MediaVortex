# directive: probe-worker-decoupled -- POST scan/probe + GET recent lists for the /Settings sub-tabs.
from flask import Blueprint, request, jsonify
from Core.Logging.LoggingService import LoggingService
from Features.OnDemandIngest.OnDemandIngestBusinessService import OnDemandIngestBusinessService


OnDemandIngestBlueprint = Blueprint('OnDemandIngest', __name__, url_prefix='/api')


@OnDemandIngestBlueprint.route('/OnDemandScan', methods=['POST'])
def OnDemandScan():
    try:
        Body = request.get_json(silent=True) or {}
        CanonicalPath = (Body.get('CanonicalPath') or '').strip()
        Result = OnDemandIngestBusinessService().SubmitScan(CanonicalPath)
        Status = 200 if Result.get('Success') else 400
        return jsonify(Result), Status
    except Exception as Ex:
        LoggingService.LogException('OnDemandScan endpoint failed', Ex, 'OnDemandIngestController', 'OnDemandScan')
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@OnDemandIngestBlueprint.route('/OnDemandProbe', methods=['POST'])
def OnDemandProbe():
    try:
        Body = request.get_json(silent=True) or {}
        CanonicalPath = (Body.get('CanonicalPath') or '').strip()
        Result = OnDemandIngestBusinessService().SubmitProbe(CanonicalPath)
        Status = 200 if Result.get('Success') else 400
        return jsonify(Result), Status
    except Exception as Ex:
        LoggingService.LogException('OnDemandProbe endpoint failed', Ex, 'OnDemandIngestController', 'OnDemandProbe')
        return jsonify({'Success': False, 'Message': str(Ex)}), 500


@OnDemandIngestBlueprint.route('/OnDemandScan/Recent', methods=['GET'])
def OnDemandScanRecent():
    try:
        Limit = int(request.args.get('limit', 20))
        Limit = max(1, min(100, Limit))
        return jsonify(OnDemandIngestBusinessService().RecentScans(Limit))
    except Exception as Ex:
        LoggingService.LogException('OnDemandScanRecent endpoint failed', Ex, 'OnDemandIngestController', 'OnDemandScanRecent')
        return jsonify({'Success': False, 'Message': str(Ex), 'Rows': []}), 500


@OnDemandIngestBlueprint.route('/OnDemandProbe/Recent', methods=['GET'])
def OnDemandProbeRecent():
    try:
        Limit = int(request.args.get('limit', 20))
        Limit = max(1, min(100, Limit))
        return jsonify(OnDemandIngestBusinessService().RecentProbes(Limit))
    except Exception as Ex:
        LoggingService.LogException('OnDemandProbeRecent endpoint failed', Ex, 'OnDemandIngestController', 'OnDemandProbeRecent')
        return jsonify({'Success': False, 'Message': str(Ex), 'Rows': []}), 500
