from flask import Blueprint, jsonify, render_template

from Core.Logging.LoggingService import LoggingService
from Features.Admin.Workers.AdminWorkersRepository import AdminWorkersRepository


AdminWorkersBlueprint = Blueprint('AdminWorkers', __name__)


# directive: activity-admin-and-worker-telemetry
@AdminWorkersBlueprint.route('/Admin/Workers', methods=['GET'])
def render_admin_workers():
    return render_template('AdminWorkers.html')


# directive: activity-admin-and-worker-telemetry
@AdminWorkersBlueprint.route('/api/Admin/Workers/Snapshot', methods=['GET'])
def admin_workers_snapshot():
    try:
        Repo = AdminWorkersRepository()
        Tiles = Repo.GetTiles()
        StaleSec = Repo.GetStaleThresholdSec()
        return jsonify({
            'Success': True,
            'Data': {
                'Workers': Tiles,
                'HeartbeatStaleThresholdSec': StaleSec,
            },
        })
    except Exception as Ex:
        LoggingService.LogException("AdminWorkers snapshot failed", Ex, "AdminWorkersController", "admin_workers_snapshot")
        return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500
