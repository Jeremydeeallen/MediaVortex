#!/usr/bin/env python3
"""
WebService Entry Point
Main Flask web application for MediaVortex
"""

import sys
import signal
import os
import setproctitle
import time
import threading
from datetime import datetime
from flask import Flask, render_template
from flask_cors import CORS

# Set process title for better visibility in Task Manager
setproctitle.setproctitle("WebService")

# Add parent directory to path to import shared services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Services.LoggingService import LoggingService

class WebServiceApp:
    """Main Flask application for MediaVortex WebService."""
    
    def __init__(self):
        # Check if another instance is already running using ServiceStatusService
        if self.PrivateIsServiceAlreadyRunning():
            print("ERROR: WebService is already running. Preventing duplicate instance.")
            sys.exit(1)
            
        # Set template and static folders to parent directory
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        template_dir = os.path.join(project_root, 'Templates')
        static_dir = os.path.join(project_root, 'static')
        
        self.App = Flask(__name__, 
                        template_folder=template_dir,
                        static_folder=static_dir)
        self.App.config['SECRET_KEY'] = 'mediavortex-secret-key-2024'
        CORS(self.App)
        
        # Initialize service tracking
        self.StartTime = datetime.now()
        self.ServiceStatusThread = None
        self.StatusPollingThread = None
        self.ShutdownEvent = False
        self.CurrentStatus = "Stopped"  # Track current service status
        
        # Initialize controllers
        from Controllers.ProfileController import ProfileController
        from Controllers.FileScanningController import FileScanningController
        from Controllers.SystemSettingsController import SystemSettingsController
        from Controllers.FileReplacementController import FileReplacementController
        
        self.ProfileController = ProfileController()
        self.FileScanningController = FileScanningController()
        self.SystemSettingsController = SystemSettingsController(self.App)
        self.FileReplacementController = FileReplacementController(self.App)

        # Clean up any stale scans from previous sessions
        try:
            from Repositories.DatabaseManager import DatabaseManager
            db_manager = DatabaseManager()

            # Mark any running/pending scans as stopped (they're from a previous session)
            cleanup_query = """
                UPDATE ScanJobs
                SET Status = 'Stopped',
                    ErrorMessage = 'Application restarted',
                    EndTime = datetime('now', 'localtime')
                WHERE Status IN ('Running', 'Pending')
            """
            db_manager.DatabaseService.ExecuteNonQuery(cleanup_query)
            LoggingService.LogInfo("Cleaned up stale scan jobs from previous session", "WebService", "__init__")
        except Exception as e:
            LoggingService.LogWarning(f"Could not clean up stale scans: {e}", "WebService", "__init__")

        # Initialize ContinuousScanService (single shared instance)
        from Services.ContinuousScanService import ContinuousScanService
        self.ContinuousScanService = ContinuousScanService()
        LoggingService.LogInfo("ContinuousScanService initialized", "WebService", "__init__")

        # Share ContinuousScanService with the FileScanningController's ViewModel
        self.FileScanningController.ViewModel.ContinuousScanService = self.ContinuousScanService

        # Auto-start continuous scanning based on SystemSettings
        try:
            from Repositories.DatabaseManager import DatabaseManager
            db_manager = DatabaseManager()

            # Check if continuous scanning is enabled in database
            enabled_setting = db_manager.GetSystemSetting('ContinuousScanEnabled')
            interval_setting = db_manager.GetSystemSetting('ContinuousScanIntervalMinutes')

            # Create settings if they don't exist
            if enabled_setting is None:
                db_manager.AddOrUpdateSystemSetting('ContinuousScanEnabled', '0', 'Enable/disable continuous file scanning', 'boolean')
                enabled_setting = '0'
                LoggingService.LogInfo("Created ContinuousScanEnabled setting (default: disabled)", "WebService", "__init__")

            if interval_setting is None:
                db_manager.AddOrUpdateSystemSetting('ContinuousScanIntervalMinutes', '60', 'Interval in minutes for continuous scanning', 'integer')
                interval_setting = '60'
                LoggingService.LogInfo("Created ContinuousScanIntervalMinutes setting (default: 60)", "WebService", "__init__")

            # Auto-start if enabled
            if enabled_setting == '1':
                interval = int(interval_setting) if interval_setting else 60
                result = self.ContinuousScanService.StartContinuousScanning(interval)
                if result.get('Success'):
                    LoggingService.LogInfo(f"Auto-started continuous scanning with {interval} minute interval", "WebService", "__init__")
                else:
                    LoggingService.LogWarning(f"Could not auto-start continuous scanning: {result.get('ErrorMessage')}", "WebService", "__init__")
            else:
                LoggingService.LogInfo("Continuous scanning is disabled (not starting automatically)", "WebService", "__init__")

        except Exception as e:
            LoggingService.LogWarning(f"Could not check/start continuous scanning: {e}", "WebService", "__init__")

        self._register_routes()
        self._register_blueprints()
        
        # Start service status tracking
        self.PrivateStartServiceStatusTracking()
        
        # Start status polling for service control
        self.PrivateStartStatusPolling()
        
        # Update service status to Running immediately after startup
        self.PrivateUpdateServiceStatus()
    
    def PrivateIsServiceAlreadyRunning(self) -> bool:
        """Check if another WebService instance is already running using ServiceStatusService."""
        try:
            from Services.ServiceStatusService import ServiceStatusService
            status_service = ServiceStatusService()
            return status_service.RegisterServiceStartup("WebService", MaxConcurrentJobs=1)
        except Exception as e:
            print(f"ERROR: Exception checking for existing WebService instances: {e}")
            return True  # Prevent startup on error
    
    def _register_routes(self):
        """Register main website routes."""
        @self.App.route('/')
        def home():
            return render_template('Home.html')
        
        @self.App.route('/settings')
        def settings():
            return render_template('Settings.html')
        
        @self.App.route('/Scanning')
        def scanning():
            return render_template('FileScanning.html')
        
        @self.App.route('/TranscodeQueue')
        def transcode_queue():
            return render_template('Queue.html')
        
        @self.App.route('/Activity')
        def activity():
            return render_template('Activity.html')
        
        @self.App.route('/Status')
        def status():
            return render_template('Status.html')
        
        @self.App.route('/SQLQueries')
        def sql_queries():
            return render_template('SQLQueries.html')
        
        @self.App.route('/TranscodeProgress')
        def transcode_progress():
            return render_template('TranscodeProgress.html')
    
    def _register_blueprints(self):
        """Register Flask blueprints."""
        from Controllers.ServiceControlController import ServiceControlBlueprint
        from Controllers.QueueResetController import QueueResetBlueprint
        from Controllers.SQLQueriesController import SQLQueriesBlueprint
        from Controllers.TranscodeQueueController import TranscodeQueueBlueprint
        from Controllers.TranscodeJobController import TranscodeJobBlueprint
        from Controllers.FileScanningController import FileScanningController
        from Controllers.ProfileController import ProfileController
        from Controllers.QualityTestController import QualityTestBlueprint
        from Controllers.ServiceStatusController import ServiceStatusBlueprint
        
        # Register all blueprints
        self.App.register_blueprint(ServiceControlBlueprint)
        self.App.register_blueprint(QueueResetBlueprint)
        self.App.register_blueprint(SQLQueriesBlueprint)
        self.App.register_blueprint(TranscodeQueueBlueprint)
        self.App.register_blueprint(TranscodeJobBlueprint)
        self.App.register_blueprint(self.FileScanningController.Blueprint)
        self.App.register_blueprint(self.ProfileController.Blueprint)
        self.App.register_blueprint(self.FileReplacementController.Blueprint)
        self.App.register_blueprint(QualityTestBlueprint)
        self.App.register_blueprint(ServiceStatusBlueprint, url_prefix='/api')
    
    def PrivateStartServiceStatusTracking(self):
        """Start service status tracking thread."""
        try:
            self.ServiceStatusThread = threading.Thread(
                target=self.PrivateServiceStatusLoop,
                daemon=True,
                name="ServiceStatusTracker"
            )
            self.ServiceStatusThread.start()
            print("Service status tracking started")
        except Exception as e:
            print(f"Failed to start service status tracking: {e}")
    
    def PrivateStartStatusPolling(self):
        """Start status polling thread."""
        try:
            self.StatusPollingThread = threading.Thread(
                target=self.PrivateStatusPollingLoop,
                daemon=True,
                name="StatusPoller"
            )
            self.StatusPollingThread.start()
            print("Status polling started")
        except Exception as e:
            print(f"Failed to start status polling: {e}")
    
    def PrivateServiceStatusLoop(self):
        """Background thread to update service status."""
        while not self.ShutdownEvent:
            try:
                self.PrivateUpdateServiceStatus()
                time.sleep(30)  # Update every 30 seconds
            except Exception as e:
                print(f"Error updating service status: {e}")
                time.sleep(60)  # Wait longer on error
    
    def PrivateStatusPollingLoop(self):
        """Status polling loop - checks ServiceStatus table for service control commands."""
        while not self.ShutdownEvent:
            try:
                # Get current service status from ServiceStatus table
                from Repositories.DatabaseManager import DatabaseManager
                db_manager = DatabaseManager()
                service_status = db_manager.GetServiceStatus("WebService")
                
                if service_status:
                    new_status = service_status.get('Status', 'Stopped')
                    
                    # Check if status has changed
                    if new_status != self.CurrentStatus:
                        print(f"WebService service status changed from {self.CurrentStatus} to {new_status}")
                        
                        # Handle status change
                        self.PrivateHandleStatusChange(new_status)
                        self.CurrentStatus = new_status
                
                # Wait 5 seconds before next check
                time.sleep(5)
                
            except Exception as e:
                print(f"Error in status polling loop: {e}")
                time.sleep(10)
    
    def PrivateHandleStatusChange(self, new_status: str):
        """Handle service status changes."""
        try:
            print(f"Handling WebService status change to: {new_status}")
            
            if new_status == "Running":
                # Service should be running - ensure web server is active
                print("WebService service status set to Running")
                self.PrivateUpdateServiceStatus()
                
            elif new_status == "Stopped":
                # Service should be stopped
                print("WebService service status set to Stopped")
                self.PrivateUpdateServiceStatus()
                
            elif new_status == "GracefulStop":
                # Handle graceful stop request
                print("Graceful stop requested for WebService - will complete current requests before stopping")
                self.PrivateUpdateServiceStatus()
                
                # Start a monitoring thread to check when current requests complete
                threading.Thread(
                    target=self.PrivateMonitorGracefulStop,
                    daemon=True,
                    name="GracefulStopMonitor"
                ).start()
                    
        except Exception as e:
            print(f"Error handling status change: {e}")
    
    def PrivateMonitorGracefulStop(self):
        """Monitor graceful stop progress and complete shutdown when current requests finish."""
        try:
            print("Starting graceful stop monitoring for WebService")
            # For a web service, we can't easily track "current requests" like transcoding jobs
            # So we'll just wait a short time for any pending requests to complete
            time.sleep(5)  # Give 5 seconds for any pending requests
            print("Graceful stop completed for WebService")
            self.PrivateUpdateServiceStatus()
            self.ShutdownEvent = True
        except Exception as e:
            print(f"Error in graceful stop monitoring: {e}")
            self.ShutdownEvent = True
    
    def PrivateUpdateServiceStatus(self):
        """Update WebService service status in database."""
        try:
            from Repositories.DatabaseManager import DatabaseManager
            from Services.LoggingService import LoggingService
            
            db_manager = DatabaseManager()
            db_manager.UpdateServiceStatus("WebService", {
                'Status': 'Running',
                'HealthStatus': 'Healthy',
                'IsProcessing': False,
                'ActiveJobsCount': 0
            })
            LoggingService.LogInfo("WebService status updated", "WebService", "PrivateUpdateServiceStatus")
        except Exception as e:
            print(f"Error updating service status: {e}")
    
    def Run(self):
        """Run the Flask application."""
        try:
            print("Starting WebService Flask application...")
            self.App.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
        except Exception as e:
            print(f"Error running WebService: {e}")
    
    def Shutdown(self):
        """Gracefully shutdown the service."""
        try:
            print("Shutting down WebService...")
            self.ShutdownEvent = True
            print("WebService shutdown complete")
        except Exception as e:
            print(f"Error during shutdown: {e}")

def SignalHandler(signum, frame):
    """Handle shutdown signals gracefully."""
    LoggingService.LogInfo(f"Received signal {signum}, shutting down gracefully...", "WebService", "SignalHandler")
    if hasattr(Main, 'app') and Main.app:
        Main.app.Shutdown()
    sys.exit(0)

def Main():
    """Main entry point for WebService."""
    try:
        LoggingService.LogInfo("Starting WebService...", "WebService", "main")
        
        # Initialize the application
        app = WebServiceApp()
        Main.app = app  # Store reference for signal handler
        
        # Register signal handlers
        signal.signal(signal.SIGINT, SignalHandler)
        signal.signal(signal.SIGTERM, SignalHandler)
        
        # Start the service (this will run indefinitely)
        LoggingService.LogInfo("WebService is now running. Press Ctrl+C to stop.", "WebService", "main")
        app.Run()
        
    except KeyboardInterrupt:
        LoggingService.LogInfo("Received keyboard interrupt, shutting down...", "WebService", "main")
        if hasattr(Main, 'app') and Main.app:
            Main.app.Shutdown()
    except Exception as e:
        LoggingService.LogException("Fatal error in WebService", e, "WebService", "main")
        sys.exit(1)
    finally:
        LoggingService.LogInfo("WebService stopped.", "WebService", "main")

if __name__ == "__main__":
    Main()
