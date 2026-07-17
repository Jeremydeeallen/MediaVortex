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
from datetime import datetime, timezone
from flask import Flask, render_template, request, jsonify, redirect
from flask_cors import CORS

# Set process title for better visibility in Task Manager
setproctitle.setproctitle("WebService")

# Add parent directory to path to import shared services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Services.LoggingService import LoggingService

class WebServiceApp:
    """Main Flask application for MediaVortex WebService."""
    
    def __init__(self):
        # Single-instance startup: kill any prior WebService process before
        # claiming port 5000. See WebService/single-instance-startup.feature.md
        # and WebService/startup.flow.md.
        self._SupersedeExistingInstance()

        # Final safety net -- after the supersede, the prior PID record (if any)
        # should be stale and RegisterServiceStartup will clean it up. If a new
        # process somehow appeared in the small window between kill and here,
        # refuse to start.
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

        self._StaticDir = static_dir
        self.App.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000

        from flask_compress import Compress
        self.App.config['COMPRESS_MIMETYPES'] = ['text/html', 'text/css', 'text/xml', 'application/json', 'application/javascript', 'application/xml']
        Compress(self.App)

        from flask import request, url_for as _flask_url_for

        @self.App.after_request
        def _RegisterResponseHeaders(response):
            Path = request.path or ''
            if Path.startswith('/static/'):
                response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
            elif Path.startswith('/api/'):
                response.headers['Cache-Control'] = 'no-store'
            else:
                response.headers['Cache-Control'] = 'no-cache, private'
            return response

        @self.App.context_processor
        def _OverrideUrlFor():
            def _DatedUrlFor(endpoint, **values):
                if endpoint == 'static':
                    Filename = values.get('filename')
                    if Filename:
                        FilePath = os.path.join(self._StaticDir, Filename)
                        try:
                            values['v'] = int(os.stat(FilePath).st_mtime)
                        except OSError:
                            pass
                return _flask_url_for(endpoint, **values)
            return dict(url_for=_DatedUrlFor)

        # Serialize every datetime in JSON responses as UTC ISO-8601 with the
        # explicit `Z` suffix. Templates/JS can then parse and convert to the
        # configured display timezone via formatTime() -- see Static/js/timezone.js.
        from Core.Web.UtcJsonProvider import UtcJsonProvider
        self.App.json = UtcJsonProvider(self.App)

        # Inject the configured display timezone into every template render so
        # Base.html can emit `window.MV_TIMEZONE`. Cached per-process; updated
        # only on Flask reload or process restart. Operators changing the value
        # via /Admin/SystemSettings should refresh their browser to pick up the
        # new value (the DB write is immediate; this avoids a per-request DB hit).
        self._CachedDisplayTimezone = None

        @self.App.context_processor
        def InjectDisplayTimezone():
            if self._CachedDisplayTimezone is None:
                try:
                    from Features.SystemSettings.SystemSettingsRepository import SystemSettingsRepository
                    Repo = SystemSettingsRepository()
                    self._CachedDisplayTimezone = Repo.GetSystemSetting('DisplayTimezone') or 'UTC'
                except Exception as Ex:
                    LoggingService.LogException(
                        "Failed to read DisplayTimezone setting -- defaulting to UTC",
                        Ex, "InjectDisplayTimezone", "WebService"
                    )
                    self._CachedDisplayTimezone = 'UTC'
            return {'display_timezone': self._CachedDisplayTimezone}

        CORS(self.App)
        
        # Initialize service tracking
        self.StartTime = datetime.now(timezone.utc)
        self.ServiceStatusThread = None
        self.StatusPollingThread = None
        self.ShutdownEvent = False
        self.CurrentStatus = "Stopped"  # Track current service status

        # Load worker config and initialize WorkerContext singleton
        import socket
        import platform as platform_mod
        try:
            from Repositories.DatabaseManager import DatabaseManager
            from Core.WorkerContext import WorkerContext
            # directive: transcode-flow-canonical -- fail-loud on schema drift before we start serving
            from Core.Database.SchemaChecker import SchemaChecker
            SchemaChecker().AssertMatches()
            WorkerName = socket.gethostname()
            WorkerPlatform = platform_mod.system().lower()
            db_init = DatabaseManager()
            WorkerConfig = db_init.GetWorkerConfig(WorkerName) or {}
            # see startup.ST4
            WorkerContext.Initialize(
                WorkerName=WorkerName,
                Platform=WorkerPlatform,
                FFmpegPath=WorkerConfig.get('FFmpegPath') or WorkerConfig.get('ffmpegpath'),
                FFprobePath=WorkerConfig.get('FFprobePath') or WorkerConfig.get('ffprobepath'),
            )
            LoggingService.LogInfo(f"WorkerContext initialized for {WorkerName}", "WebService", "__init__")
        except Exception as e:
            LoggingService.LogWarning(f"Could not initialize WorkerContext: {e}", "WebService", "__init__")

        # Initialize controllers
        from Features.Profiles.ProfileController import ProfileController
        from Features.FileScanning.FileScanningController import FileScanningController
        from Features.SystemSettings.SystemSettingsController import SystemSettingsController
        from Features.FileReplacement.FileReplacementController import FileReplacementController
        
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
                    EndTime = NOW()
                WHERE Status IN ('Running', 'Pending')
            """
            db_manager.DatabaseService.ExecuteNonQuery(cleanup_query)
            LoggingService.LogInfo("Cleaned up stale scan jobs from previous session", "WebService", "__init__")

            # Run database migrations
            db_manager.RunMigrations()
        except Exception as e:
            LoggingService.LogWarning(f"Could not clean up stale scans: {e}", "WebService", "__init__")

        # ContinuousScanService is now managed by WorkerService (ScanEnabled capability).
        # FileScanningController creates its own instance lazily for on-demand API scans.

        # Auto-sync Jellyfin FFmpeg logs on startup (background thread)
        self._start_jellyfin_sync()

        self._register_routes()
        self._register_blueprints()
        self._register_error_handlers()
        self._register_path_scope_middleware()
        
        # Start service status tracking
        self.PrivateStartServiceStatusTracking()
        
        # Start status polling for service control
        self.PrivateStartStatusPolling()
        self.PrivateStartAudioVerticalHealth()
        self.PrivateStartFileReplacementSelfHeal()
        self.PrivateStartAudioRemeasurementRunner()
        
        # Update service status to Running immediately after startup
        self.PrivateUpdateServiceStatus()
    
    def _start_jellyfin_sync(self):
        """Auto-sync Jellyfin FFmpeg logs on startup in a background thread."""
        def sync_worker():
            try:
                from ViewModels.OptimizationViewModel import OptimizationViewModel
                vm = OptimizationViewModel()
                service = vm._GetJellyfinService()
                if not service:
                    LoggingService.LogInfo("Jellyfin not configured, skipping auto-sync", "WebService", "_start_jellyfin_sync")
                    return
                result = vm.RefreshJellyfinData()
                if result.get("Success"):
                    LoggingService.LogInfo(f"Jellyfin auto-sync complete: {result.get('NewCount', 0)} new logs imported ({result.get('TotalInDB', 0)} total)", "WebService", "_start_jellyfin_sync")
                else:
                    LoggingService.LogWarning(f"Jellyfin auto-sync failed: {result.get('ErrorMessage')}", "WebService", "_start_jellyfin_sync")
            except Exception as e:
                LoggingService.LogWarning(f"Jellyfin auto-sync error: {e}", "WebService", "_start_jellyfin_sync")

        thread = threading.Thread(target=sync_worker, daemon=True, name="JellyfinSync")
        thread.start()
        LoggingService.LogInfo("Started Jellyfin auto-sync background thread", "WebService", "_start_jellyfin_sync")

    def _SupersedeExistingInstance(self) -> None:
        """Kill any prior WebService process recorded in ServiceStatus, then wait
        for port 5000 to release. No-op if no prior PID or the PID is stale.

        Validates the target process before killing -- if PID was recycled to a
        non-WebService process, skips the kill (no false positives).
        """
        try:
            import socket as _socket
            import psutil
            from Repositories.DatabaseManager import DatabaseManager

            current_pid = os.getpid()
            db = DatabaseManager()
            status = db.GetServiceStatus("WebService")
            prior_pid = status.get('ProcessId') if status else None
            if not prior_pid or prior_pid == current_pid:
                return

            try:
                proc = psutil.Process(prior_pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                print(f"Supersede: prior WebService PID {prior_pid} not running. Proceeding.")
                return

            # Confirm this PID is actually a WebService -- guard against PID recycle.
            try:
                cmdline = " ".join(proc.cmdline() or [])
                proc_name = (proc.name() or "").lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                cmdline, proc_name = "", ""
            looks_like_webservice = (
                "webservice" in cmdline.lower()
                or "main.py" in cmdline.lower() and "webservice" in cmdline.lower()
                or proc_name == "webservice"
            )
            if not looks_like_webservice:
                print(f"Supersede: PID {prior_pid} is not WebService ('{proc_name}' / '{cmdline[:80]}'). Skipping kill.")
                return

            print(f"Supersede: terminating prior WebService PID {prior_pid} ('{proc_name}')...")
            try:
                proc.terminate()
                proc.wait(timeout=5)
                print(f"Supersede: PID {prior_pid} exited cleanly.")
            except psutil.TimeoutExpired:
                print(f"Supersede: PID {prior_pid} did not exit in 5s; force killing.")
                proc.kill()
                try:
                    proc.wait(timeout=3)
                except psutil.TimeoutExpired:
                    pass

            # Wait up to 10s for port 5000 to release.
            deadline = time.time() + 10
            while time.time() < deadline:
                s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
                s.settimeout(0.5)
                try:
                    rc = s.connect_ex(("127.0.0.1", 5000))
                finally:
                    s.close()
                if rc != 0:
                    print(f"Supersede: port 5000 released. Proceeding.")
                    return
                time.sleep(0.5)
            print("ERROR: port 5000 still bound after 10s; another process holds it. Exiting.")
            sys.exit(1)
        except Exception as e:
            # Don't let supersede errors block startup. The downstream
            # RegisterServiceStartup check will still gate on real duplicates.
            print(f"Supersede: non-fatal error -- {e}. Continuing with normal duplicate check.")

    def PrivateIsServiceAlreadyRunning(self) -> bool:
        """Check if another WebService instance is already running using ServiceStatusService."""
        try:
            from Services.ServiceStatusService import ServiceStatusService
            status_service = ServiceStatusService()
            return status_service.RegisterServiceStartup("WebService", MaxConcurrentJobs=1)
        except Exception as e:
            LoggingService.LogException("Exception checking for existing WebService instances", e, "WebService", "PrivateIsServiceAlreadyRunning")
            return True  # Prevent startup on error
    
    def _register_path_scope_middleware(self):
        """Pin a StorageRoots snapshot per request -- str(path)/CanonicalDisplay/GetPrefixMap reuse one DB read."""
        # directive: path-class-perfection | # see path.C25
        from Core.Path.PathStorageRoots import PrefixMapScope, _ScopeStorageRoots, _ScopePrefixMap, _LoadFresh

        @self.App.before_request
        def _OpenPathScope():
            from flask import g
            Roots = _LoadFresh()
            Pm = {R["Id"]: R["CanonicalPrefix"] for R in Roots}
            g._PathScopeRootsToken = _ScopeStorageRoots.set(Roots)
            g._PathScopeMapToken = _ScopePrefixMap.set(Pm)

        @self.App.teardown_request
        def _ClosePathScope(_Exc):
            from flask import g
            Token = getattr(g, '_PathScopeRootsToken', None)
            if Token is not None:
                _ScopeStorageRoots.reset(Token)
            MapToken = getattr(g, '_PathScopeMapToken', None)
            if MapToken is not None:
                _ScopePrefixMap.reset(MapToken)

    def _register_error_handlers(self):
        """Register global error handlers for the Flask app."""
        @self.App.errorhandler(404)
        def HandleNotFound(e):
            if request.path.startswith('/api/'):
                return jsonify({"Success": False, "Message": "Resource not found", "Error": str(e)}), 404
            return render_template('Error.html', ErrorCode=404, ErrorMessage="Page not found"), 404

        @self.App.errorhandler(500)
        def HandleInternalError(e):
            LoggingService.LogError(f"Internal server error: {e}", "WebService", "HandleInternalError")
            if request.path.startswith('/api/'):
                return jsonify({"Success": False, "Message": "Internal server error", "Error": str(e)}), 500
            return render_template('Error.html', ErrorCode=500, ErrorMessage="Internal server error"), 500

        @self.App.errorhandler(Exception)
        def HandleException(e):
            LoggingService.LogException(f"Unhandled exception on {request.path}", e, "WebService", "HandleException")
            if request.path.startswith('/api/'):
                return jsonify({"Success": False, "Message": "An unexpected error occurred", "Error": str(e)}), 500
            return render_template('Error.html', ErrorCode=500, ErrorMessage="An unexpected error occurred"), 500

    def _register_routes(self):
        """Register main website routes."""
        @self.App.route('/')
        def home():
            return redirect('/settings')

        @self.App.route('/settings')
        def settings():
            try:
                return render_template('Settings.html')
            except Exception as e:
                LoggingService.LogException("Error rendering Settings page", e, "WebService", "settings")
                return render_template('Error.html', ErrorCode=500, ErrorMessage="Failed to load page"), 500

        @self.App.route('/Queue')
        def queue_page():
            try:
                return render_template('Queue.html')
            except Exception as e:
                LoggingService.LogException("Error rendering Queue page", e, "WebService", "queue_page")
                return render_template('Error.html', ErrorCode=500, ErrorMessage="Failed to load page"), 500

        @self.App.route('/TranscodeQueue')
        def transcode_queue():
            from flask import redirect
            return redirect('/Queue', code=301)

        @self.App.route('/Activity')
        def activity():
            try:
                return render_template('Activity.html')
            except Exception as e:
                LoggingService.LogException("Error rendering Activity page", e, "WebService", "activity")
                return render_template('Error.html', ErrorCode=500, ErrorMessage="Failed to load page"), 500

        @self.App.route('/Stats')
        def status():
            try:
                return render_template('Status.html')
            except Exception as e:
                LoggingService.LogException("Error rendering Status page", e, "WebService", "status")
                return render_template('Error.html', ErrorCode=500, ErrorMessage="Failed to load page"), 500

        @self.App.route('/Operations')
        def operations():
            try:
                return render_template('Operations.html')
            except Exception as e:
                LoggingService.LogException("Error rendering Operations page", e, "WebService", "operations")
                return render_template('Error.html', ErrorCode=500, ErrorMessage="Failed to load page"), 500

        @self.App.route('/SQLQueries')
        def sql_queries():
            return redirect('/Operations')

        @self.App.route('/TranscodeProgress')
        def transcode_progress():
            try:
                return render_template('TranscodeProgress.html')
            except Exception as e:
                LoggingService.LogException("Error rendering TranscodeProgress page", e, "WebService", "transcode_progress")
                return render_template('Error.html', ErrorCode=500, ErrorMessage="Failed to load page"), 500

        @self.App.route('/Optimization')
        def optimization():
            try:
                return render_template('Optimization.html')
            except Exception as e:
                LoggingService.LogException("Error rendering Optimization page", e, "WebService", "optimization")
                return render_template('Error.html', ErrorCode=500, ErrorMessage="Failed to load page"), 500

        @self.App.route('/ClipBuilder')
        def clip_builder():
            try:
                return render_template('ClipBuilder.html')
            except Exception as e:
                LoggingService.LogException("Error rendering ClipBuilder page", e, "WebService", "clip_builder")
                return render_template('Error.html', ErrorCode=500, ErrorMessage="Failed to load page"), 500

        @self.App.route('/api/ClientLog', methods=['POST'])
        def ClientLog():
            """Receive client-side JavaScript errors and log them to the database."""
            try:
                Data = request.get_json()
                if not Data:
                    return jsonify({'Success': False, 'Message': 'No data provided'}), 400

                Message = Data.get('Message', 'Unknown client error')
                Source = Data.get('Source', '')
                LineNo = Data.get('LineNo', '')
                ColNo = Data.get('ColNo', '')
                Stack = Data.get('Stack', '')
                Page = Data.get('Page', '')
                ErrorType = Data.get('ErrorType', 'JavaScriptError')

                LogMessage = f"[{Page}] {Message}"
                if Source:
                    LogMessage += f" (at {Source}:{LineNo}:{ColNo})"

                LoggingService.LogToDatabase(
                    'ERROR',
                    LogMessage,
                    FunctionName='ClientLog',
                    Component='WebUI',
                    ExceptionType=ErrorType,
                    ExceptionMessage=Message,
                    StackTrace=Stack
                )
                return jsonify({'Success': True}), 200
            except Exception as e:
                return jsonify({'Success': False, 'Message': str(e)}), 500

    def _register_blueprints(self):
        """Register Flask blueprints."""
        from Features.ServiceControl.ServiceControlController import ServiceControlBlueprint
        from Features.TranscodeQueue.QueueResetController import QueueResetBlueprint
        from Features.SQLQueries.SQLQueriesController import SQLQueriesBlueprint
        from Features.TranscodeQueue.TranscodeQueueController import TranscodeQueueBlueprint
        from Features.TranscodeJob.TranscodeJobController import TranscodeJobBlueprint
        from Features.FileScanning.FileScanningController import FileScanningController
        from Features.Profiles.ProfileController import ProfileController
        from Features.QualityTesting.QualityTestController import QualityTestBlueprint
        from Features.ServiceControl.ServiceStatusController import ServiceStatusBlueprint
        from Features.Optimization.OptimizationController import OptimizationBlueprint
        from Features.ClipBuilder.ClipBuilderController import ClipBuilderBlueprint
        from Features.TeamStatus.TeamStatusController import TeamStatusBlueprint
        from Features.MediaProbe.MediaProbeController import MediaProbeBlueprint
        from Features.FailureTracking.FailureTrackingController import FailureTrackingBlueprint
        from Features.AudioNormalization.Controllers.AudioCompletionController import AudioCompletionBlueprint
        from Features.AudioNormalization.AudioNormalizationController import BuildBlueprint as BuildAudioNormalizationBlueprint
        from Features.Activity.ActivityController import ActivityBlueprint
        from Features.TranscodeQueue.AudioFixPriorityHintsController import AudioFixPriorityHintsBlueprint
        # directive: failure-accounting | # see failure-accounting.C8
        from Features.FailureAccounting.FailedJobsController import FailedJobsBlueprint
        # directive: work-bucket-landing-pages | # see directive.md C1
        from Features.WorkBucket.WorkBucketController import WorkBucketController
        # directive: audio-vertical-phase-1-completion | # see directive.md P3
        from Features.FileScanning.ScannersController import ScannersBlueprint

        # Register all blueprints
        self.App.register_blueprint(AudioCompletionBlueprint)
        self.App.register_blueprint(BuildAudioNormalizationBlueprint())
        self.App.register_blueprint(ActivityBlueprint)
        self.App.register_blueprint(AudioFixPriorityHintsBlueprint)
        self.App.register_blueprint(ServiceControlBlueprint)
        self.App.register_blueprint(QueueResetBlueprint)
        self.App.register_blueprint(SQLQueriesBlueprint, url_prefix='/api/SQLQueries')
        self.App.register_blueprint(TranscodeQueueBlueprint)
        self.App.register_blueprint(TranscodeJobBlueprint)
        self.App.register_blueprint(self.FileScanningController.Blueprint)
        self.App.register_blueprint(self.ProfileController.Blueprint)
        self.App.register_blueprint(self.FileReplacementController.Blueprint)
        self.App.register_blueprint(QualityTestBlueprint)
        self.App.register_blueprint(ServiceStatusBlueprint, url_prefix='/api')
        self.App.register_blueprint(OptimizationBlueprint)
        self.App.register_blueprint(ClipBuilderBlueprint)
        self.App.register_blueprint(TeamStatusBlueprint)
        self.App.register_blueprint(MediaProbeBlueprint)
        self.App.register_blueprint(FailureTrackingBlueprint, url_prefix='/api/FailureTracking')
        # directive: failure-accounting | # see failure-accounting.C8
        self.App.register_blueprint(FailedJobsBlueprint)
        # directive: work-bucket-landing-pages | # see directive.md C1
        self.App.register_blueprint(WorkBucketController().Blueprint)
        # directive: audio-vertical-phase-1-completion | # see directive.md P3
        self.App.register_blueprint(ScannersBlueprint)
        # directive: compliance-tabbed-ui | # see startup.ST5
        from Features.VideoEncoding.VideoEncodingController import VideoEncodingBlueprint
        from Features.ContainerFormat.ContainerFormatController import ContainerFormatBlueprint
        self.App.register_blueprint(VideoEncodingBlueprint)
        self.App.register_blueprint(ContainerFormatBlueprint)

        # directive: compliance-symmetry | # see startup.ST5
        from Features.MediaFile.ComplianceSummaryController import ComplianceSummaryBlueprint
        self.App.register_blueprint(ComplianceSummaryBlueprint)

        # directive: compliance-recompute-tools | # see startup.ST5
        from Features.MediaFile.ComplianceRecomputeController import ComplianceRecomputeBlueprint
        self.App.register_blueprint(ComplianceRecomputeBlueprint)

        # directive: activity-admin-and-worker-telemetry | # see startup.ST5
        @self.App.route('/Compliance')
        def redirect_compliance_legacy():
            from flask import redirect
            return redirect('/Admin/Compliance', code=301)

        # directive: activity-admin-and-worker-telemetry | # see startup.ST5
        from Features.Admin.Workers.AdminWorkersController import AdminWorkersBlueprint
        from Features.Admin.Compliance.AdminComplianceController import AdminComplianceBlueprint
        self.App.register_blueprint(AdminWorkersBlueprint)
        self.App.register_blueprint(AdminComplianceBlueprint)

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
            LoggingService.LogException("Failed to start service status tracking", e, "WebService", "PrivateStartServiceStatusTracking")
    
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
            LoggingService.LogException("Failed to start status polling", e, "WebService", "PrivateStartStatusPolling")

    # directive: filereplacement-drain-bug | # see filereplacement.C11
    def PrivateStartFileReplacementSelfHeal(self):
        try:
            self.FileReplacementSelfHealThread = threading.Thread(
                target=self.PrivateFileReplacementSelfHealLoop,
                daemon=True,
                name="FileReplacementSelfHeal",
            )
            self.FileReplacementSelfHealThread.start()
            print("FileReplacementSelfHealService started")
        except Exception as Ex:
            LoggingService.LogException("Failed to start FileReplacementSelfHealService", Ex, "WebService", "PrivateStartFileReplacementSelfHeal")

    # directive: filereplacement-drain-bug | # see filereplacement.C11
    def PrivateFileReplacementSelfHealLoop(self):
        from Features.FileReplacement.FileReplacementSelfHealService import FileReplacementSelfHealService
        Svc = FileReplacementSelfHealService()
        Interval = 120
        while True:
            try:
                Svc.Run()
            except Exception as Ex:
                LoggingService.LogException("FileReplacementSelfHealService cycle raised", Ex,
                                            "WebService", "PrivateFileReplacementSelfHealLoop")
            time.sleep(Interval)

    # directive: transcode-flow-canonical -- drain AdmissionDeferReason='invalid_loudness_measurement' backlog by calling AudioRemeasurementService.Process; runs on WebService which owns worker mounts + ffmpeg
    def PrivateStartAudioRemeasurementRunner(self):
        try:
            self.AudioRemeasurementRunnerThread = threading.Thread(
                target=self.PrivateAudioRemeasurementRunnerLoop,
                daemon=True,
                name="AudioRemeasurementRunner",
            )
            self.AudioRemeasurementRunnerThread.start()
            print("AudioRemeasurementRunner started")
        except Exception as Ex:
            LoggingService.LogException("Failed to start AudioRemeasurementRunner", Ex, "WebService", "PrivateStartAudioRemeasurementRunner")

    def PrivateAudioRemeasurementRunnerLoop(self):
        from Features.AudioNormalization.Services.AudioRemeasurementRunner import AudioRemeasurementRunner
        AudioRemeasurementRunner(BatchSize=20, PollSec=30).RunForever()

    # directive: audio-vertical-perfection-and-self-healing | # see audio-normalization.H1
    def PrivateStartAudioVerticalHealth(self):
        """Start the AudioVerticalHealthService recurring loop in a background daemon thread."""
        try:
            self.AudioVerticalHealthThread = threading.Thread(
                target=self.PrivateAudioVerticalHealthLoop,
                daemon=True,
                name="AudioVerticalHealth",
            )
            self.AudioVerticalHealthThread.start()
            print("AudioVerticalHealthService started")
        except Exception as Ex:
            LoggingService.LogException("Failed to start AudioVerticalHealthService", Ex, "WebService", "PrivateStartAudioVerticalHealth")

    # directive: audio-vertical-phase-1-completion | # see directive.md P3
    def PrivateAudioVerticalHealthLoop(self):
        """Background loop. Reads the `AudioVerticalHealth` row of the Scanners config table fresh per cycle (db-is-authority). When Enabled=TRUE, runs the cycle; when DryRun=TRUE, Detect runs but Remediation.Apply does not. Operator toggles via /Admin/Scanners without restart. Stamps LastRunAt on every successful cycle."""
        from Features.AudioNormalization.SelfHealing.AudioVerticalHealthComposition import BuildAudioVerticalHealthService
        from Features.FileScanning.ScannersRepository import ScannersRepository
        Repo = ScannersRepository()
        Name = 'AudioVerticalHealth'
        while True:
            try:
                Row = Repo.Get(Name) or {}
                Enabled = bool(Row.get('enabled'))
                DryRun = bool(Row.get('dryrun'))
                Interval = max(60, int(Row.get('intervalsec') or 300))
                Batch = max(1, int(Row.get('batchsize') or 100))
            except Exception:
                Enabled = False
                DryRun = False
                Interval = 300
                Batch = 100
            if Enabled:
                try:
                    Svc = BuildAudioVerticalHealthService(RemediationBatch=Batch, DryRun=DryRun)
                    Svc.RunCycle()
                    Repo.RecordRun(Name)
                except Exception as Ex:
                    LoggingService.LogException("AudioVerticalHealthService cycle raised", Ex, "WebService", "PrivateAudioVerticalHealthLoop")
            time.sleep(Interval)
    
    def PrivateServiceStatusLoop(self):
        """Background thread to update service status."""
        while not self.ShutdownEvent:
            try:
                self.PrivateUpdateServiceStatus()
                time.sleep(30)  # Update every 30 seconds
            except Exception as e:
                LoggingService.LogException("Error updating service status in PrivateServiceStatusLoop", e, "WebService", "PrivateServiceStatusLoop")
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
                LoggingService.LogException("Error in status polling loop", e, "WebService", "PrivateStatusPollingLoop")
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
            LoggingService.LogException(f"Error handling status change to '{new_status}'", e, "WebService", "PrivateHandleStatusChange")
    
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
            LoggingService.LogException("Error in graceful stop monitoring", e, "WebService", "PrivateMonitorGracefulStop")
            self.ShutdownEvent = True
    
    def PrivateUpdateServiceStatus(self):
        """Update WebService health heartbeat without overwriting operational status."""
        try:
            from Repositories.DatabaseManager import DatabaseManager
            
            db_manager = DatabaseManager()
            db_manager.UpdateServiceStatus("WebService", {
                'HealthStatus': 'Healthy'
            })
        except Exception as e:
            LoggingService.LogException("Error updating service status (heartbeat)", e, "WebService", "PrivateUpdateServiceStatus")
    
    # see startup.ST8
    def Run(self):
        try:
            from waitress import serve
            print("Starting WebService via waitress (production WSGI, 32 threads)...")
            serve(self.App, host='0.0.0.0', port=5000, threads=32, ident='MediaVortex-WebService')
        except Exception as e:
            LoggingService.LogException("Error running WebService", e, "WebService", "Run")
    
    def Shutdown(self):
        """Gracefully shutdown the service."""
        try:
            print("Shutting down WebService...")
            self.ShutdownEvent = True
            print("WebService shutdown complete")
        except Exception as e:
            LoggingService.LogException("Error during WebService shutdown", e, "WebService", "Shutdown")

def SignalHandler(signum, frame):
    """Handle shutdown signals immediately."""
    print("\nWebService shutting down...")
    try:
        from Core.Database.DatabaseService import DatabaseService
        if DatabaseService._pool is not None and not DatabaseService._pool.closed:
            DatabaseService._pool.closeall()
    except Exception:
        pass
    os._exit(0)

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
