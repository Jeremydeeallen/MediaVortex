from flask import Blueprint, jsonify, render_template, request

from Core.Logging.LoggingService import LoggingService
from Features.FileScanning.ScannersRepository import ScannersRepository


ScannersBlueprint = Blueprint('Scanners', __name__)
_Repo = ScannersRepository()


# directive: audio-vertical-phase-1-completion | # see directive.md P3
@ScannersBlueprint.route('/Admin/Scanners', methods=['GET'])
def render_page():
    """Render the Admin > Scanners control surface."""
    return render_template('Scanners.html')


# directive: audio-vertical-phase-1-completion | # see directive.md P3
@ScannersBlueprint.route('/api/Scanners', methods=['GET'])
def list_scanners():
    """Return every Scanner row."""
    try:
        Rows = _Repo.List()
        return jsonify({'Success': True, 'Message': 'OK', 'Data': {'Rows': Rows}})
    except Exception as Ex:
        LoggingService.LogException("Scanners list failed", Ex, "ScannersController", "list_scanners")
        return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500


# directive: audio-vertical-phase-1-completion | # see directive.md P3
@ScannersBlueprint.route('/api/Scanners/<scanner_name>', methods=['POST'])
def update_scanner(scanner_name):
    """Update one Scanner row. Body: {Enabled, IntervalSec, BatchSize, DryRun}."""
    try:
        Body = request.get_json(force=True, silent=True) or {}
        Ok = _Repo.Update(
            scanner_name,
            bool(Body.get('Enabled', False)),
            int(Body.get('IntervalSec', 300)),
            int(Body.get('BatchSize', 100)),
            bool(Body.get('DryRun', False)),
        )
        if not Ok:
            return jsonify({'Success': False, 'Message': f"Unknown scanner: {scanner_name}", 'Data': {}}), 404
        return jsonify({'Success': True, 'Message': 'Saved', 'Data': _Repo.Get(scanner_name)})
    except Exception as Ex:
        LoggingService.LogException(f"Scanner update failed for {scanner_name}", Ex, "ScannersController", "update_scanner")
        return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500


# directive: audio-vertical-phase-1-completion | # see directive.md P3
@ScannersBlueprint.route('/api/Scanners/PauseAll', methods=['POST'])
def pause_all():
    """Kill switch: flip Enabled=FALSE on every Scanner; returns count of rows that were Enabled."""
    try:
        Count = _Repo.PauseAll()
        return jsonify({'Success': True, 'Message': f"Paused {Count}", 'Data': {'Paused': Count}})
    except Exception as Ex:
        LoggingService.LogException("Scanners pause-all failed", Ex, "ScannersController", "pause_all")
        return jsonify({'Success': False, 'Message': str(Ex), 'Data': {}}), 500
