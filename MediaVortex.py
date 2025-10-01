# Disable Python bytecode caching completely to prevent stale code issues
import sys
import os
import shutil
import setproctitle
import psutil
import time
import threading
from datetime import datetime

# Set process title for better visibility in Task Manager
setproctitle.setproctitle("MediaVortex")

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
from Controllers.FailureTrackingController import FailureTrackingBlueprint
from Controllers.QueueResetController import QueueResetBlueprint


class MediaVortexApp:
    """Main Flask application for MediaVortex."""
    
    def __init__(self):
        # Check if another instance is already running
        if self.PrivateIsServiceAlreadyRunning():
            print("ERROR: MediaVortex is already running. Preventing duplicate instance.")
            sys.exit(1)
            
        self.App = Flask(__name__)
        self.App.config['SECRET_KEY'] = 'mediavortex-secret-key-2024'
        CORS(self.App)
        
        # Initialize service tracking
        self.StartTime = datetime.now()
        self.ServiceStatusThread = None
        self.ShutdownEvent = False
        
        # Initialize controllers
        self.ProfileController = ProfileController()
        self.FileScanningController = FileScanningController()
        self.SystemSettingsController = SystemSettingsController(self.App)
        self.FileReplacementController = FileReplacementController(self.App)
        
        self._register_routes()
        self._register_blueprints()
        
        # Start service status tracking
        self.PrivateStartServiceStatusTracking()
    
    def PrivateIsServiceAlreadyRunning(self) -> bool:
        """Check if another MediaVortex instance is already running."""
        try:
            current_pid = os.getpid()
            mediavortex_processes = []
            
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['name'] == 'MediaVortex' and proc.info['pid'] != current_pid:
                        mediavortex_processes.append(proc.info['pid'])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if mediavortex_processes:
                print(f"ERROR: Found {len(mediavortex_processes)} existing MediaVortex processes: {mediavortex_processes}")
                return True
            
            return False
            
        except Exception as e:
            print(f"ERROR: Exception checking for existing MediaVortex instances: {e}")
            return False
    
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
            return render_template('Queue.html')
        
        @self.App.route('/Activity')
        def activity():
            """Activity monitoring page for transcoding and VMAF quality analysis."""
            return render_template('Activity.html')
        
        @self.App.route('/Status')
        def status():
            """Service status page for monitoring microservices."""
            return render_template('Status.html')
        
        
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
        self.App.register_blueprint(FailureTrackingBlueprint, url_prefix='/api/FailureTracking')
        self.App.register_blueprint(QueueResetBlueprint)
    
    def PrivateStartServiceStatusTracking(self):
        """Start the service status tracking thread."""
        try:
            self.ServiceStatusThread = threading.Thread(target=self.PrivateServiceStatusLoop, daemon=True)
            self.ServiceStatusThread.start()
            print("✅ MediaVortex service status tracking started")
        except Exception as e:
            print(f"❌ Failed to start service status tracking: {e}")
    
    def PrivateServiceStatusLoop(self):
        """Background thread to update service status."""
        while not self.ShutdownEvent:
            try:
                self.PrivateUpdateServiceStatus()
                time.sleep(30)  # Update every 30 seconds
            except Exception as e:
                print(f"Error updating service status: {e}")
                time.sleep(60)  # Wait longer on error
    
    def PrivateUpdateServiceStatus(self):
        """Update MediaVortex service status in database."""
        try:
            from Repositories.DatabaseManager import DatabaseManager
            from Services.LoggingService import LoggingService
            
            # Calculate uptime
            uptime_seconds = int((datetime.now() - self.StartTime).total_seconds())
            
            # Get system metrics
            memory_usage = self.PrivateGetMemoryUsage()
            cpu_usage = self.PrivateGetCPUUsage()
            disk_space = self.PrivateGetDiskSpace()
            
            # Check database connection
            database_connection = self.PrivateCheckDatabaseConnection()
            
            # Prepare service status data
            service_status = {
                'ServiceName': 'MediaVortex',
                'Status': 'Running',
                'HealthStatus': 'Healthy',
                'StartTime': self.StartTime.isoformat(),
                'LastHealthCheck': datetime.now().isoformat(),
                'UptimeSeconds': uptime_seconds,
                'MemoryUsage': memory_usage,
                'CPUUsage': cpu_usage,
                'DatabaseConnection': database_connection,
                'DiskSpace': disk_space,
                'ErrorCount': 0,
                'MaxErrors': 10,
                'ActiveJobsCount': 0,  # MediaVortex doesn't process jobs directly
                'IsProcessing': False,
                'LastErrorMessage': None,
                'ProcessId': os.getpid(),
                'Version': '1.0.0',
                'ServiceType': 'WebApplication'
            }
            
            # Save to database
            db_manager = DatabaseManager()
            success = db_manager.SaveServiceStatus(service_status)
            
            if success:
                LoggingService.LogInfo("MediaVortex service status updated", "MediaVortexApp", "PrivateUpdateServiceStatus")
            else:
                LoggingService.LogWarning("Failed to update MediaVortex service status", "MediaVortexApp", "PrivateUpdateServiceStatus")
                
        except Exception as e:
            print(f"Exception updating MediaVortex service status: {e}")
    
    def PrivateGetMemoryUsage(self) -> float:
        """Get current memory usage in MB."""
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            return memory_info.rss / 1024 / 1024  # Convert to MB
        except Exception:
            return 0.0
    
    def PrivateGetCPUUsage(self) -> float:
        """Get current CPU usage percentage."""
        try:
            process = psutil.Process(os.getpid())
            return process.cpu_percent()
        except Exception:
            return 0.0
    
    def PrivateGetDiskSpace(self) -> float:
        """Get available disk space in GB."""
        try:
            disk_usage = psutil.disk_usage('.')
            return disk_usage.free / 1024 / 1024 / 1024  # Convert to GB
        except Exception:
            return 0.0
    
    def PrivateCheckDatabaseConnection(self) -> bool:
        """Check if database connection is working."""
        try:
            from Repositories.DatabaseManager import DatabaseManager
            db_manager = DatabaseManager()
            return db_manager.DatabaseService.CheckConnection()
        except Exception:
            return False
    
    def Run(self, host='0.0.0.0', port=5000, debug=False):
        """Run the Flask application."""
        print(f"Starting MediaVortex on http://{host}:{port}")
        print(f"Settings page: http://{host}:{port}/settings")
        print(f"File Scanning page: http://{host}:{port}/Scanning")
        print(f"Transcoding Queue page: http://{host}:{port}/TranscodeQueue")
        print(f"Activity page: http://{host}:{port}/Activity")
        print(f"Service Status page: http://{host}:{port}/Status")
        
        try:
            self.App.run(host=host, port=port, debug=debug)
        finally:
            # Cleanup on shutdown
            self.ShutdownEvent = True
            if self.ServiceStatusThread and self.ServiceStatusThread.is_alive():
                self.ServiceStatusThread.join(timeout=5)


if __name__ == '__main__':
    app = MediaVortexApp()
    app.Run(debug=True)
