from flask import Blueprint, jsonify, render_template

from Core.Logging.LoggingService import LoggingService
from Features.Admin.Workers.AdminWorkersRepository import AdminWorkersRepository


AdminWorkersBlueprint = Blueprint('AdminWorkers', __name__)


# directive: worker-runtime-state | # see admin-workers.C1
@AdminWorkersBlueprint.route('/Admin/Workers', methods=['GET'])
def render_admin_workers():
    return render_template('AdminWorkers.html')


# directive: worker-runtime-state | # see admin-workers.C2
@AdminWorkersBlueprint.route('/api/Admin/Workers/Snapshot', methods=['GET'])
def admin_workers_snapshot():
    try:
        Repo = AdminWorkersRepository()
        Tiles = Repo.GetTiles()
        StaleSec = Repo.GetStaleThresholdSec()
        DivergenceSec = Repo.GetDivergenceThresholdSec()
        HungSec = Repo.GetHungEncodeThresholdSec()
        return jsonify({
            'Success': True,
            'Data': {
                'Workers': Tiles,
                'HeartbeatStaleThresholdSec': StaleSec,
                'WorkerIntentDivergenceSec': DivergenceSec,
                'HungEncodeThresholdSec': HungSec,
            },
        })
    except Exception as Ex:
        LoggingService.LogException("AdminWorkers snapshot failed", Ex, "AdminWorkersController", "admin_workers_snapshot")
        return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500
