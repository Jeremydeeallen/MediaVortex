"""
WebService Application Logic
Main Flask web application for MediaVortex
"""

import sys
import os
import time
import threading
import psutil
from datetime import datetime

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from flask import Flask, render_template, jsonify
from flask_cors import CORS
from Controllers.ProfileController import ProfileController
from Controllers.FileScanningController import FileScanningController
from Controllers.SystemSettingsController import SystemSettingsController
from Controllers.TranscodeQueueController import TranscodeQueueBlueprint
from Controllers.TranscodeJobController import TranscodeJobBlueprint
from Controllers.QualityTestController import QualityTestBlueprint
from Controllers.FileReplacementController import FileReplacementController
from Controllers.ServiceStatusController import ServiceStatusBlueprint
from Controllers.ServiceControlController import ServiceControlBlueprint
from Controllers.FailureTrackingController import FailureTrackingBlueprint
from Controllers.QueueResetController import QueueResetBlueprint
from Controllers.SQLQueriesController import SQLQueriesBlueprint


class WebServiceApp:
    """Main Flask application for MediaVortex WebService."""
    
    def __init__(self):
        # Check if another instance is already running
        if self.PrivateIsServiceAlreadyRunning():
            print("ERROR: WebService is already running. Preventing duplicate instance.")
            sys.exit(1)
            
        # Set template and static folders to parent directory
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
        self.ProfileController = ProfileController()
        self.FileScanningController = FileScanningController()
        self.SystemSettingsController = SystemSettingsController(self.App)
        self.FileReplacementController = FileReplacementController(self.App)
        
        self._register_routes()
        self._register_blueprints()
        
        # Start service status tracking
        self.PrivateStartServiceStatusTracking()
        
        # Start status polling for service control
        self.PrivateStartStatusPolling()
    
    def PrivateRegisterWebService(self):
        """Register WebService in the ServiceStatus table."""
        try:
            print("Registering WebService in database...")
            
            # Create service status entry in database
            service_status = {
                'ServiceName': 'WebService',
                'Status': 'Starting',
                'HealthStatus': 'Unknown',
                'StartTime': self.StartTime.isoformat(),
                'LastHealthCheck': datetime.now().isoformat(),
                'UptimeSeconds': 0,
                'MemoryUsage': 0.0,
                'CPUUsage': 0.0,
                'DatabaseConnection': True,
                'DiskSpace': 0.0,
                'ErrorCount': 0,
                'MaxErrors': 10,
                'ActiveJobsCount': 0,
                'IsProcessing': False,
                'LastErrorMessage': None,
                'ProcessId': os.getpid(),
                'Version': '1.0.0',
                'ServiceType': 'WebApplication',
                'MaxConcurrentJobs': 1
            }
            
            print(f"Service status data: {service_status}")
            
            # Save to database using DatabaseManager
            from Repositories.DatabaseManager import DatabaseManager
            db_manager = DatabaseManager()
            print("DatabaseManager created, calling SaveServiceStatus...")
            success = db_manager.SaveServiceStatus(service_status)
            print(f"SaveServiceStatus returned: {success}")
            
            if success:
                print("WebService registered in database")
            else:
                print("Failed to register WebService in database")
                
        except Exception as e:
            print(f"Error registering WebService in database: {e}")
            import traceback
            traceback.print_exc()
    
    def PrivateIsServiceAlreadyRunning(self) -> bool:
        """Check if another WebService instance is already running."""
        try:
            current_pid = os.getpid()
            webservice_processes = []
            
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['name'] == 'WebService' and proc.info['pid'] != current_pid:
                        webservice_processes.append(proc.info['pid'])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if webservice_processes:
                print(f"ERROR: Found {len(webservice_processes)} existing WebService processes: {webservice_processes}")
                return True
            
            return False
            
        except Exception as e:
            print(f"ERROR: Exception checking for existing WebService instances: {e}")
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
        
        @self.App.route('/SQLQueries')
        def sqlqueries():
            """SQL Queries page for database troubleshooting."""
            return render_template('SQLQueries.html')
        
        
        @self.App.route('/api/health')
        def health_check():
            """Health check endpoint."""
            return jsonify({
                'status': 'healthy',
                'message': 'WebService is running'
            })
    
    def _register_blueprints(self):
        """Register controller blueprints."""
        self.App.register_blueprint(self.ProfileController.Blueprint, url_prefix='/api')
        self.App.register_blueprint(self.FileScanningController.Blueprint, url_prefix='/api')
        self.App.register_blueprint(self.FileReplacementController.Blueprint)
        self.App.register_blueprint(TranscodeQueueBlueprint)
        self.App.register_blueprint(TranscodeJobBlueprint)
        self.App.register_blueprint(QualityTestBlueprint, url_prefix='/api')
        self.App.register_blueprint(ServiceStatusBlueprint, url_prefix='/api')
        self.App.register_blueprint(ServiceControlBlueprint)
        self.App.register_blueprint(FailureTrackingBlueprint, url_prefix='/api/FailureTracking')
        self.App.register_blueprint(QueueResetBlueprint)
        self.App.register_blueprint(SQLQueriesBlueprint, url_prefix='/api/SQLQueries')
    
    def PrivateStartServiceStatusTracking(self):
        """Start the service status tracking thread."""
        try:
            self.ServiceStatusThread = threading.Thread(target=self.PrivateServiceStatusLoop, daemon=True)
            self.ServiceStatusThread.start()
            print("WebService service status tracking started")
        except Exception as e:
            print(f"Failed to start service status tracking: {e}")
    
    def PrivateStartStatusPolling(self):
        """Start status polling thread for service control."""
        try:
            self.StatusPollingThread = threading.Thread(
                target=self.PrivateStatusPollingLoop,
                daemon=True,
                name="StatusPoller"
            )
            self.StatusPollingThread.start()
            print("WebService status polling started")
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
                'ServiceName': 'WebService',
                'Status': 'Running',  # WebService is always running when this method is called
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
                'ActiveJobsCount': 0,  # WebService doesn't process jobs directly
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
                LoggingService.LogDebug("WebService service status updated", "WebServiceApp", "PrivateUpdateServiceStatus")
            else:
                LoggingService.LogWarning("Failed to update WebService service status", "WebServiceApp", "PrivateUpdateServiceStatus")
                
        except Exception as e:
            print(f"Exception updating WebService service status: {e}")
    
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
        print(f"Starting WebService on http://{host}:{port}")
        print(f"Settings page: http://{host}:{port}/settings")
        print(f"File Scanning page: http://{host}:{port}/Scanning")
        print(f"Transcoding Queue page: http://{host}:{port}/TranscodeQueue")
        print(f"Activity page: http://{host}:{port}/Activity")
        print(f"Service Status page: http://{host}:{port}/Status")
        print(f"SQL Queries page: http://{host}:{port}/SQLQueries")
        
        # Register WebService in database before starting
        self.PrivateRegisterWebService()
        
        # Set initial status to Running and update database
        self.CurrentStatus = "Running"
        self.PrivateUpdateServiceStatus()
        
        try:
            self.App.run(host=host, port=port, debug=debug)
        except KeyboardInterrupt:
            print("\nWebService shutdown requested")
            self.Shutdown()
        except Exception as e:
            print(f"Error running WebService: {e}")
            self.Shutdown()
        finally:
            # Cleanup on shutdown
            self.ShutdownEvent = True
            if self.ServiceStatusThread and self.ServiceStatusThread.is_alive():
                self.ServiceStatusThread.join(timeout=5)
            if self.StatusPollingThread and self.StatusPollingThread.is_alive():
                self.StatusPollingThread.join(timeout=5)
    
    def Shutdown(self):
        """Shutdown the WebService gracefully."""
        try:
            print("Initiating WebService shutdown...")
            self.CurrentStatus = "Stopped"
            self.PrivateUpdateServiceStatus()
            self.ShutdownEvent = True
            print("WebService shutdown complete")
        except Exception as e:
            print(f"Error during WebService shutdown: {e}")
