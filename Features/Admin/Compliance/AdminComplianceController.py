from flask import Blueprint, jsonify, render_template

from Core.Logging.LoggingService import LoggingService
from Features.Admin.Compliance.AdminComplianceRepository import AdminComplianceRepository


AdminComplianceBlueprint = Blueprint('AdminCompliance', __name__)


# directive: activity-admin-and-worker-telemetry
@AdminComplianceBlueprint.route('/Admin/Compliance', methods=['GET'])
def render_admin_compliance():
    return render_template('AdminCompliance.html')


# directive: activity-admin-and-worker-telemetry
@AdminComplianceBlueprint.route('/api/Admin/Compliance/Snapshot', methods=['GET'])
def admin_compliance_snapshot():
    try:
        Repo = AdminComplianceRepository()
        return jsonify({'Success': True, 'Data': Repo.GetCard()})
    except Exception as Ex:
        LoggingService.LogException("AdminCompliance snapshot failed", Ex, "AdminComplianceController", "admin_compliance_snapshot")
        return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500
