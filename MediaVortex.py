# Disable Python bytecode caching completely to prevent stale code issues
import sys
import os
import shutil

# Disable bytecode generation completely
sys.dont_write_bytecode = True
sys.dont_write_bytecode = True

# Clear ALL existing cache directories to ensure fresh code execution
CacheDirsToClear = [
    '__pycache__',
    'Repositories/__pycache__',
    'Models/__pycache__', 
    'Services/__pycache__',
    'Controllers/__pycache__',
    'ViewModels/__pycache__',
    'Scripts/__pycache__',
    'Tests/__pycache__',
    'Tests/Contract/__pycache__',
    'Tests/CursorTests/__pycache__',
    'Tests/Integration/__pycache__'
]

print("=== DISABLING PYTHON CACHING ===")
for CacheDir in CacheDirsToClear:
    if os.path.exists(CacheDir):
        try:
            shutil.rmtree(CacheDir)
            print(f"✅ Cleared cache: {CacheDir}")
        except Exception as e:
            print(f"⚠️  Warning: Could not clear cache for {CacheDir}: {e}")

# Force reload of critical modules by clearing from sys.modules
CriticalModules = [
    'Repositories.DatabaseManager',
    'Models.QualityTestingQueueModel', 
    'Models.QualityTestProgressModel',
    'Models.QualityTestResultModel',
    'ViewModels.QualityTestingViewModel',
    'Controllers.QualityTestingController',
    'Services.QualityTestingOrchestratorService'
]

for Module in CriticalModules:
    if Module in sys.modules:
        del sys.modules[Module]
        print(f"✅ Cleared module from cache: {Module}")

print("=== CACHING DISABLED - FRESH CODE WILL BE LOADED ===")

# Set development mode to disable all caching
os.environ['FLASK_ENV'] = 'development'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

from flask import Flask, render_template, jsonify
from flask_cors import CORS
from Controllers.ProfileController import ProfileController
from Controllers.FileScanningController import FileScanningController
from Controllers.SystemSettingsController import SystemSettingsController
from Controllers.TranscodeQueueController import TranscodeQueueBlueprint
from Controllers.TranscodeJobController import TranscodeJobBlueprint
from Controllers.QualityTestingController import QualityTestingBlueprint
from Controllers.FileReplacementController import FileReplacementController
from Controllers.ServiceStatusController import ServiceStatusBlueprint
from Controllers.QueueResetController import QueueResetBlueprint


class MediaVortexApp:
    """Main Flask application for MediaVortex."""
    
    def __init__(self):
        self.App = Flask(__name__)
        self.App.config['SECRET_KEY'] = 'mediavortex-secret-key-2024'
        CORS(self.App)
        
        # Initialize controllers
        self.ProfileController = ProfileController()
        self.FileScanningController = FileScanningController()
        self.SystemSettingsController = SystemSettingsController(self.App)
        self.FileReplacementController = FileReplacementController(self.App)
        
        self._register_routes()
        self._register_blueprints()
    
    def _register_routes(self):
        """Register main application routes."""
        
        @self.App.route('/')
        def home():
            """Home page - blank for now."""
            return render_template('Home.html')
        
        @self.App.route('/settings')
        def settings():
            """Settings page with profile management."""
            return render_template('Settings.html')
        
        @self.App.route('/Scanning')
        def scanning():
            """File scanning page."""
            return render_template('FileScanning.html')
        
        @self.App.route('/TranscodeQueue')
        def transcode_queue():
            """Transcoding queue management page."""
            return render_template('TranscodeQueue.html')
        
        @self.App.route('/Activity')
        def activity():
            """Activity monitoring page for transcoding and VMAF quality analysis."""
            return render_template('Activity.html')
        
        @self.App.route('/api/health')
        def health_check():
            """Health check endpoint."""
            return jsonify({
                'status': 'healthy',
                'message': 'MediaVortex is running'
            })
    
    def _register_blueprints(self):
        """Register controller blueprints."""
        self.App.register_blueprint(self.ProfileController.Blueprint, url_prefix='/api')
        self.App.register_blueprint(self.FileScanningController.Blueprint, url_prefix='/api')
        self.App.register_blueprint(self.FileReplacementController.Blueprint)
        self.App.register_blueprint(TranscodeQueueBlueprint)
        self.App.register_blueprint(TranscodeJobBlueprint)
        self.App.register_blueprint(QualityTestingBlueprint)
        self.App.register_blueprint(ServiceStatusBlueprint, url_prefix='/api')
        self.App.register_blueprint(QueueResetBlueprint)
    
    def Run(self, host='0.0.0.0', port=5000, debug=False):
        """Run the Flask application."""
        print(f"Starting MediaVortex on http://{host}:{port}")
        print(f"Settings page: http://{host}:{port}/settings")
        print(f"File Scanning page: http://{host}:{port}/Scanning")
        print(f"Transcoding Queue page: http://{host}:{port}/TranscodeQueue")
        print(f"Transcoding Progress page: http://{host}:{port}/TranscodeProgress")
        self.App.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    app = MediaVortexApp()
    app.Run()
