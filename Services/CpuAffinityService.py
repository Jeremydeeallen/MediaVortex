"""
CPU Affinity Service
Manages CPU core assignment for FFmpeg processes using topology-aware static affinity.
Pins transcode jobs to P-cores and quality test jobs to E-cores on hybrid CPUs.
Includes thermal gating to prevent starting new jobs when the system is too hot.
Supports Game Mode: migrate running jobs to E-cores on pause, restore on resume.
"""

import psutil
import threading
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from Core.Logging.LoggingService import LoggingService
from Services.SystemMonitoringService import SystemMonitoringService
from Services.CoreTopologyService import CoreTopologyService
from Repositories.DatabaseManager import DatabaseManager


class CpuAffinityService:
    """Service for managing CPU affinity using topology-aware core assignment."""

    _Instance = None
    _Lock = threading.Lock()

    def __init__(self, DatabaseManagerInstance: DatabaseManager = None,
                 SystemMonitoringServiceInstance: SystemMonitoringService = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.SystemMonitoringService = SystemMonitoringServiceInstance or SystemMonitoringService()
        self.Topology = CoreTopologyService.GetInstance()

        # Job tracking: {JobId: {"ProcessPID", "CoreList", "PrePauseCoreList", "StartTime", "JobType"}}
        self.ActiveJobs = {}
        self.ActiveJobsLock = threading.Lock()

        # Configuration (loaded from SystemSettings)
        self.CpuAffinityEnabled = True
        self.TranscodeCoreTier = "performance"   # "performance", "efficiency", "all"
        self.QualityTestCoreTier = "efficiency"   # "performance", "efficiency", "all"

        # Thermal gate configuration
        self.ThermalGateEnabled = True
        self.ThermalGateMaxTemp = 80.0
        self.ThermalGateMinCoolCores = 8
        self.ThermalPauseCriticalTemp = 90.0
        self.ThermalGateMaxWaitSeconds = 600
        self.ThermalGateCheckInterval = 10

        # Temperature cache
        self.TemperatureCache = None
        self.TemperatureCacheTime = None
        self.TemperatureCacheValidSeconds = 5

        self._LoadConfiguration()

        LoggingService.LogInfo(
            f"CpuAffinityService initialized. Hybrid={self.Topology.IsHybrid}, "
            f"Detection={self.Topology.DetectionMethod}, "
            f"P-cores={self.Topology.PCoreLogicalIds}, E-cores={self.Topology.ECoreLogicalIds}",
            "CpuAffinityService", "__init__")
    
    @classmethod
    def GetInstance(cls, DatabaseManagerInstance: DatabaseManager = None,
                    SystemMonitoringServiceInstance: SystemMonitoringService = None):
        """Get singleton instance of CpuAffinityService."""
        if cls._Instance is None:
            with cls._Lock:
                if cls._Instance is None:
                    cls._Instance = cls(DatabaseManagerInstance, SystemMonitoringServiceInstance)
        return cls._Instance

    def _LoadConfiguration(self):
        """Load configuration from SystemSettings table."""
        try:
            EnabledStr = self.DatabaseManager.GetSystemSetting('CpuAffinityEnabled')
            if EnabledStr:
                self.CpuAffinityEnabled = EnabledStr.lower() in ('true', '1', 'yes')

            TranscodeCoreTierStr = self.DatabaseManager.GetSystemSetting('TranscodeCoreTier')
            if TranscodeCoreTierStr and TranscodeCoreTierStr.lower() in ('performance', 'efficiency', 'all'):
                self.TranscodeCoreTier = TranscodeCoreTierStr.lower()

            QualityTestCoreTierStr = self.DatabaseManager.GetSystemSetting('QualityTestCoreTier')
            if QualityTestCoreTierStr and QualityTestCoreTierStr.lower() in ('performance', 'efficiency', 'all'):
                self.QualityTestCoreTier = QualityTestCoreTierStr.lower()

            ThermalGateEnabledStr = self.DatabaseManager.GetSystemSetting('ThermalGateEnabled')
            if ThermalGateEnabledStr:
                self.ThermalGateEnabled = ThermalGateEnabledStr.lower() in ('true', '1', 'yes')

            ThermalGateMaxTempStr = self.DatabaseManager.GetSystemSetting('ThermalGateMaxTemp')
            if ThermalGateMaxTempStr:
                try:
                    self.ThermalGateMaxTemp = float(ThermalGateMaxTempStr)
                except ValueError:
                    pass

            ThermalGateMinCoolCoresStr = self.DatabaseManager.GetSystemSetting('ThermalGateMinCoolCores')
            if ThermalGateMinCoolCoresStr:
                try:
                    self.ThermalGateMinCoolCores = int(ThermalGateMinCoolCoresStr)
                except ValueError:
                    pass

            ThermalPauseCriticalTempStr = self.DatabaseManager.GetSystemSetting('ThermalPauseCriticalTemp')
            if ThermalPauseCriticalTempStr:
                try:
                    self.ThermalPauseCriticalTemp = float(ThermalPauseCriticalTempStr)
                except ValueError:
                    pass

            ThermalGateMaxWaitSecondsStr = self.DatabaseManager.GetSystemSetting('ThermalGateMaxWaitSeconds')
            if ThermalGateMaxWaitSecondsStr:
                try:
                    self.ThermalGateMaxWaitSeconds = int(ThermalGateMaxWaitSecondsStr)
                except ValueError:
                    pass

            ThermalGateCheckIntervalStr = self.DatabaseManager.GetSystemSetting('ThermalGateCheckInterval')
            if ThermalGateCheckIntervalStr:
                try:
                    self.ThermalGateCheckInterval = max(5, int(ThermalGateCheckIntervalStr))
                except ValueError:
                    pass

            LoggingService.LogInfo(
                f"Configuration loaded: Enabled={self.CpuAffinityEnabled}, "
                f"TranscodeTier={self.TranscodeCoreTier}, QualityTestTier={self.QualityTestCoreTier}, "
                f"ThermalGate={self.ThermalGateEnabled}, CriticalTemp={self.ThermalPauseCriticalTemp}°C",
                "CpuAffinityService", "_LoadConfiguration")
        except Exception as Ex:
            LoggingService.LogException("Error loading configuration", Ex, "CpuAffinityService", "_LoadConfiguration")

    # ─── Core Selection ──────────────────────────────────────────────────

    def GetCoresForJob(self, JobType: str, CoreCount: int) -> List[int]:
        """Get the core list for a job based on topology and configuration.

        Args:
            JobType: "Transcode" or "QualityTest"
            CoreCount: Maximum number of cores to use

        Returns:
            List of logical processor IDs
        """
        if not self.CpuAffinityEnabled:
            TotalLogical = psutil.cpu_count(logical=True) or 1
            return list(range(min(CoreCount, TotalLogical)))

        if JobType == "Transcode":
            Tier = self.TranscodeCoreTier
        elif JobType == "QualityTest":
            Tier = self.QualityTestCoreTier
        else:
            Tier = "all"

        Cores = self.Topology.GetCoresForTier(Tier, MaxCount=CoreCount)

        if not Cores:
            Cores = self.Topology.GetCoresForTier("all", MaxCount=CoreCount)

        LoggingService.LogInfo(
            f"Selected {len(Cores)} cores for {JobType} (tier={Tier}): {Cores}",
            "CpuAffinityService", "GetCoresForJob")
        return Cores

    # ─── Job Registration & Affinity Setting ─────────────────────────────

    def SetFFmpegProcessAffinity(self, ShellProcessPID: int, CoreCount: int, JobId: int,
                                 JobType: str, ServiceName: str) -> Dict[str, Any]:
        """Set CPU affinity on FFmpeg child process using topology-based core selection.

        Args:
            ShellProcessPID: PID of shell process that spawned FFmpeg
            CoreCount: Number of cores to allocate
            JobId: Job identifier for tracking
            JobType: "Transcode" or "QualityTest"
            ServiceName: Name of calling service for logging

        Returns:
            Dictionary with Success, FFmpegPID, AffinityCores, ErrorMessage
        """
        try:
            time.sleep(0.1)  # Brief wait for child process to spawn

            ShellProcess = psutil.Process(ShellProcessPID)
            AffinityCores = self.GetCoresForJob(JobType, CoreCount)

            # Find the child FFmpeg process
            FFmpegProcess = None
            for Child in ShellProcess.children(recursive=True):
                if 'ffmpeg' in Child.name().lower():
                    FFmpegProcess = Child
                    break

            if FFmpegProcess:
                FFmpegProcess.cpu_affinity(AffinityCores)
                LoggingService.LogInfo(
                    f"Set {JobType} FFmpeg CPU affinity to cores: {AffinityCores} "
                    f"(Shell PID: {ShellProcessPID}, FFmpeg PID: {FFmpegProcess.pid})",
                    "CpuAffinityService", "SetFFmpegProcessAffinity")

                self._RegisterJob(JobId, FFmpegProcess.pid, AffinityCores, JobType)

                return {
                    "Success": True,
                    "FFmpegPID": FFmpegProcess.pid,
                    "AffinityCores": AffinityCores,
                    "ErrorMessage": None
                }
            else:
                ErrorMessage = f"Could not find child FFmpeg process for shell PID {ShellProcessPID}"
                LoggingService.LogWarning(ErrorMessage, "CpuAffinityService", "SetFFmpegProcessAffinity")
                return {"Success": False, "FFmpegPID": None, "AffinityCores": [], "ErrorMessage": ErrorMessage}

        except psutil.NoSuchProcess:
            ErrorMessage = f"Shell process PID {ShellProcessPID} not found"
            LoggingService.LogWarning(ErrorMessage, "CpuAffinityService", "SetFFmpegProcessAffinity")
            return {"Success": False, "FFmpegPID": None, "AffinityCores": [], "ErrorMessage": ErrorMessage}
        except Exception as Ex:
            ErrorMessage = f"Error setting CPU affinity: {str(Ex)}"
            LoggingService.LogException(f"Failed to set CPU affinity for {JobType} job {JobId}", Ex,
                                       "CpuAffinityService", "SetFFmpegProcessAffinity")
            return {"Success": False, "FFmpegPID": None, "AffinityCores": [], "ErrorMessage": ErrorMessage}

    def _RegisterJob(self, JobId: int, ProcessPID: int, CoreList: List[int], JobType: str):
        """Register an active job for tracking."""
        with self.ActiveJobsLock:
            self.ActiveJobs[JobId] = {
                "ProcessPID": ProcessPID,
                "CoreList": CoreList,
                "PrePauseCoreList": None,
                "StartTime": datetime.now(timezone.utc),
                "JobType": JobType
            }
        LoggingService.LogInfo(f"Registered {JobType} job {JobId} (PID {ProcessPID}) on cores {CoreList}",
                               "CpuAffinityService", "_RegisterJob")

    def ReleaseJob(self, JobId: int, WaitForCooling: bool = False):
        """Release a completed job from tracking.

        Args:
            JobId: Job identifier
            WaitForCooling: Ignored (kept for API compatibility). Cooling waits are removed.
        """
        with self.ActiveJobsLock:
            if JobId in self.ActiveJobs:
                JobInfo = self.ActiveJobs.pop(JobId)
                LoggingService.LogInfo(
                    f"Released {JobInfo.get('JobType', 'Unknown')} job {JobId} from cores {JobInfo.get('CoreList', [])}",
                    "CpuAffinityService", "ReleaseJob")
            else:
                LoggingService.LogWarning(f"Job {JobId} not found in active jobs", "CpuAffinityService", "ReleaseJob")

    # ─── Game Mode: Pause/Resume Migration ───────────────────────────────

    def MigrateActiveJobsToTier(self, Tier: str) -> Dict[str, Any]:
        """Migrate all active FFmpeg jobs to a different core tier.

        Used for Game Mode: pause -> migrate to E-cores, resume -> migrate back to P-cores.

        Args:
            Tier: "efficiency" (E-cores) or "performance" (P-cores) or "restore" (pre-pause assignment)

        Returns:
            Dictionary with Success, MigratedCount, Details
        """
        MigratedCount = 0
        Details = []

        with self.ActiveJobsLock:
            for JobId, JobInfo in self.ActiveJobs.items():
                ProcessPID = JobInfo.get("ProcessPID")
                CurrentCores = JobInfo.get("CoreList", [])
                JobType = JobInfo.get("JobType", "Unknown")

                try:
                    Process = psutil.Process(ProcessPID)
                    if not Process.is_running():
                        Details.append({"JobId": JobId, "Success": False, "Reason": "process_not_running"})
                        continue

                    if Tier == "restore":
                        NewCores = JobInfo.get("PrePauseCoreList")
                        if not NewCores:
                            CoreCount = len(CurrentCores)
                            NewCores = self.GetCoresForJob(JobType, CoreCount)
                    else:
                        CoreCount = len(CurrentCores)
                        NewCores = self.Topology.GetCoresForTier(Tier, MaxCount=CoreCount)
                        if not NewCores:
                            NewCores = self.Topology.GetCoresForTier("all", MaxCount=CoreCount)

                    # Save current assignment before migrating (for restore)
                    if Tier != "restore" and JobInfo.get("PrePauseCoreList") is None:
                        JobInfo["PrePauseCoreList"] = list(CurrentCores)

                    Process.cpu_affinity(NewCores)
                    JobInfo["CoreList"] = NewCores

                    if Tier == "restore":
                        JobInfo["PrePauseCoreList"] = None

                    MigratedCount += 1
                    Details.append({"JobId": JobId, "Success": True, "From": CurrentCores, "To": NewCores})

                    LoggingService.LogInfo(
                        f"Migrated {JobType} job {JobId} (PID {ProcessPID}) from {CurrentCores} to {NewCores} (tier={Tier})",
                        "CpuAffinityService", "MigrateActiveJobsToTier")

                except psutil.NoSuchProcess:
                    Details.append({"JobId": JobId, "Success": False, "Reason": "process_not_found"})
                except Exception as Ex:
                    Details.append({"JobId": JobId, "Success": False, "Reason": str(Ex)})
                    LoggingService.LogException(f"Failed to migrate job {JobId}", Ex,
                                               "CpuAffinityService", "MigrateActiveJobsToTier")

        LoggingService.LogInfo(f"Migration to tier '{Tier}' complete: {MigratedCount} jobs migrated",
                               "CpuAffinityService", "MigrateActiveJobsToTier")

        return {"Success": True, "MigratedCount": MigratedCount, "Details": Details}

    # ─── Thermal Gating ──────────────────────────────────────────────────

    def _GetCurrentTemperatures(self) -> Optional[Dict[str, Any]]:
        """Get current CPU temperatures, using cache if available."""
        try:
            CurrentTime = datetime.now(timezone.utc)
            if (self.TemperatureCache is not None and
                self.TemperatureCacheTime is not None and
                (CurrentTime - self.TemperatureCacheTime).total_seconds() < self.TemperatureCacheValidSeconds):
                return self.TemperatureCache

            TempData = self.SystemMonitoringService.GetCpuTemperature()
            if TempData:
                self.TemperatureCache = TempData
                self.TemperatureCacheTime = CurrentTime
                return TempData

            return None
        except Exception as Ex:
            LoggingService.LogException("Error getting temperatures", Ex,
                                       "CpuAffinityService", "_GetCurrentTemperatures")
            return None

    def IsSystemTooHotForNewJob(self, CoreCount: int) -> Dict[str, Any]:
        """Check if the system is too hot to start a new job.

        Args:
            CoreCount: Number of cores the job would use (0 = general check)

        Returns:
            Dictionary with Ready (bool), Reason (str), and diagnostic info
        """
        if not self.ThermalGateEnabled:
            return {"Ready": True}

        TempData = self._GetCurrentTemperatures()
        if not TempData:
            return {"Ready": True, "Reason": "no_temp_data"}

        Cores = TempData.get('Cores', [])
        if not Cores:
            return {"Ready": True, "Reason": "no_core_data"}

        CoreTemps = [C.get('Temperature') for C in Cores if C.get('Temperature') is not None]
        if not CoreTemps:
            return {"Ready": True, "Reason": "no_temp_readings"}

        AverageTemp = sum(CoreTemps) / len(CoreTemps)

        if AverageTemp >= self.ThermalPauseCriticalTemp:
            return {
                "Ready": False,
                "Reason": "critical_temp",
                "AverageTemp": round(AverageTemp, 1),
                "CriticalThreshold": self.ThermalPauseCriticalTemp
            }

        CoolCoreCount = sum(1 for Temp in CoreTemps if Temp < self.ThermalGateMaxTemp)

        if CoolCoreCount < self.ThermalGateMinCoolCores:
            return {
                "Ready": False,
                "Reason": "insufficient_cool_cores",
                "CoolCores": CoolCoreCount,
                "RequiredCoolCores": self.ThermalGateMinCoolCores,
                "ThermalGateMaxTemp": self.ThermalGateMaxTemp,
                "AverageTemp": round(AverageTemp, 1)
            }

        return {"Ready": True, "AverageTemp": round(AverageTemp, 1), "CoolCores": CoolCoreCount}

    def WaitForThermalClearance(self, CoreCount: int) -> bool:
        """Wait for the system to cool enough before starting a new job.

        Args:
            CoreCount: Number of cores the job would use (0 = general check)

        Returns:
            True when clearance granted, False if timeout exceeded
        """
        if not self.ThermalGateEnabled:
            return True

        try:
            Result = self.IsSystemTooHotForNewJob(CoreCount)
            if Result.get("Ready", True):
                return True

            LoggingService.LogInfo(
                f"Waiting for thermal clearance (reason: {Result.get('Reason', 'unknown')}, "
                f"avg temp: {Result.get('AverageTemp', 'N/A')}°C)",
                "CpuAffinityService", "WaitForThermalClearance")

            StartTime = datetime.now(timezone.utc)
            LastLogTime = StartTime

            while True:
                time.sleep(self.ThermalGateCheckInterval)

                ElapsedSeconds = (datetime.now(timezone.utc) - StartTime).total_seconds()
                if ElapsedSeconds >= self.ThermalGateMaxWaitSeconds:
                    LoggingService.LogWarning(
                        f"Thermal clearance timeout after {ElapsedSeconds:.0f}s — allowing job to proceed",
                        "CpuAffinityService", "WaitForThermalClearance")
                    return False

                Result = self.IsSystemTooHotForNewJob(CoreCount)
                if Result.get("Ready", True):
                    LoggingService.LogInfo(
                        f"Thermal clearance granted after {ElapsedSeconds:.0f}s",
                        "CpuAffinityService", "WaitForThermalClearance")
                    return True

                SecondsSinceLastLog = (datetime.now(timezone.utc) - LastLogTime).total_seconds()
                if SecondsSinceLastLog >= 30:
                    LastLogTime = datetime.now(timezone.utc)
                    LoggingService.LogInfo(
                        f"Still waiting for thermal clearance ({ElapsedSeconds:.0f}s, "
                        f"avg temp: {Result.get('AverageTemp', 'N/A')}°C)",
                        "CpuAffinityService", "WaitForThermalClearance")

        except Exception as Ex:
            LoggingService.LogException("Error waiting for thermal clearance", Ex,
                                       "CpuAffinityService", "WaitForThermalClearance")
            return True  # Don't block on error

    # ─── Diagnostics ─────────────────────────────────────────────────────

    def GetActiveJobs(self) -> Dict[int, Dict[str, Any]]:
        """Get dictionary of active jobs for diagnostics."""
        with self.ActiveJobsLock:
            return dict(self.ActiveJobs)

    def GetStatus(self) -> Dict[str, Any]:
        """Get full service status for diagnostics/UI."""
        with self.ActiveJobsLock:
            ActiveJobCount = len(self.ActiveJobs)
            JobSummaries = []
            for JobId, Info in self.ActiveJobs.items():
                JobSummaries.append({
                    "JobId": JobId,
                    "JobType": Info.get("JobType"),
                    "CoreList": Info.get("CoreList"),
                    "PrePauseCoreList": Info.get("PrePauseCoreList"),
                    "IsInGameMode": Info.get("PrePauseCoreList") is not None
                })

        return {
            "Enabled": self.CpuAffinityEnabled,
            "Topology": self.Topology.GetTopologySummary(),
            "TranscodeCoreTier": self.TranscodeCoreTier,
            "QualityTestCoreTier": self.QualityTestCoreTier,
            "ThermalGateEnabled": self.ThermalGateEnabled,
            "ActiveJobCount": ActiveJobCount,
            "ActiveJobs": JobSummaries
        }


# Global instance for easy access
CpuAffinityServiceInstance = None

def GetCpuAffinityServiceInstance() -> CpuAffinityService:
    """Get the global CpuAffinityService instance."""
    global CpuAffinityServiceInstance
    if CpuAffinityServiceInstance is None:
        CpuAffinityServiceInstance = CpuAffinityService.GetInstance()
    return CpuAffinityServiceInstance

