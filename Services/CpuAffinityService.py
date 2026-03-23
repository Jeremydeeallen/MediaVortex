"""
CPU Affinity Service
Handles intelligent CPU core selection based on temperature, with continuous monitoring and dynamic core migration.
Implements MVVM pattern using MVVM architecture
"""

import psutil
import threading
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from Services.LoggingService import LoggingService
from Services.SystemMonitoringService import SystemMonitoringService
from Repositories.DatabaseManager import DatabaseManager


class CpuAffinityService:
    """Service for managing CPU affinity selection based on core temperatures."""
    
    # Singleton instance
    _Instance = None
    _Lock = threading.Lock()
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None, SystemMonitoringServiceInstance: SystemMonitoringService = None):
        """Initialize the CPU Affinity Service."""
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.SystemMonitoringService = SystemMonitoringServiceInstance or SystemMonitoringService()
        
        # Core state tracking: {CoreNumber: {"Status": "available|cooling|active", "LastUsed": datetime, "Temperature": float}}
        self.CoreStates = {}
        # Job tracking: {JobId: {"ProcessPID": int, "CoreList": List[int], "StartTime": datetime, "JobType": str}}
        self.ActiveJobs = {}
        
        # Threading
        self.CoreStatesLock = threading.Lock()
        self.ActiveJobsLock = threading.Lock()
        self.MonitoringThread = None
        self.MonitoringActive = False
        self.StopMonitoringEvent = threading.Event()
        
        # Configuration (loaded from SystemSettings)
        self.CpuAffinityEnabled = True
        self.TemperatureThreshold = 98.0
        self.MonitoringInterval = 45
        self.CoolingPeriodSeconds = 60
        self.CoolingWaitEnabled = True
        self.CoolingWaitTargetTemp = 60.0  # Wait for cores to drop below this temp (idle range is 55-60°C)
        self.CoolingWaitMaxSeconds = 300  # Maximum wait time (5 minutes)
        self.CoolingWaitCheckInterval = 5  # Check temperature every N seconds

        # Thermal gate configuration (pre-start temperature gate)
        self.ThermalGateEnabled = True
        self.ThermalGateMaxTemp = 80.0  # Per-core temp threshold for "cool enough"
        self.ThermalGateMinCoolCores = 8  # Min cool cores before starting new job
        self.ThermalPauseCriticalTemp = 90.0  # Average temp that pauses all new starts
        self.ThermalGateMaxWaitSeconds = 600  # Max wait for thermal clearance (10 min)
        self.ThermalGateCheckInterval = 10  # Seconds between temp checks while waiting
        
        # Temperature cache
        self.TemperatureCache = None
        self.TemperatureCacheTime = None
        self.TemperatureCacheValidSeconds = 5
        
        # Load configuration from database
        self._LoadConfiguration()
        
        # Initialize core states
        self._InitializeCoreStates()
        
        LoggingService.LogInfo("CpuAffinityService initialized", "CpuAffinityService", "__init__")
    
    @classmethod
    def GetInstance(cls, DatabaseManagerInstance: DatabaseManager = None, SystemMonitoringServiceInstance: SystemMonitoringService = None):
        """Get singleton instance of CpuAffinityService."""
        if cls._Instance is None:
            with cls._Lock:
                if cls._Instance is None:
                    cls._Instance = cls(DatabaseManagerInstance, SystemMonitoringServiceInstance)
        return cls._Instance
    
    def _LoadConfiguration(self):
        """Load configuration from SystemSettings table."""
        try:
            # Load CpuAffinityEnabled
            EnabledStr = self.DatabaseManager.GetSystemSetting('CpuAffinityEnabled')
            if EnabledStr:
                self.CpuAffinityEnabled = EnabledStr.lower() in ('true', '1', 'yes')
            
            # Load TemperatureThreshold
            ThresholdStr = self.DatabaseManager.GetSystemSetting('CpuAffinityTemperatureThreshold')
            if ThresholdStr:
                try:
                    self.TemperatureThreshold = float(ThresholdStr)
                except ValueError:
                    pass
            
            # Load MonitoringInterval
            IntervalStr = self.DatabaseManager.GetSystemSetting('CpuAffinityMonitoringInterval')
            if IntervalStr:
                try:
                    self.MonitoringInterval = int(IntervalStr)
                    # Ensure reasonable bounds (15-120 seconds)
                    if self.MonitoringInterval < 15:
                        self.MonitoringInterval = 15
                    elif self.MonitoringInterval > 120:
                        self.MonitoringInterval = 120
                except ValueError:
                    pass
            
            # Load CoolingWaitEnabled
            CoolingWaitEnabledStr = self.DatabaseManager.GetSystemSetting('CpuAffinityCoolingWaitEnabled')
            if CoolingWaitEnabledStr:
                self.CoolingWaitEnabled = CoolingWaitEnabledStr.lower() in ('true', '1', 'yes')
            
            # Load CoolingWaitTargetTemp
            CoolingWaitTargetTempStr = self.DatabaseManager.GetSystemSetting('CpuAffinityCoolingWaitTargetTemp')
            if CoolingWaitTargetTempStr:
                try:
                    self.CoolingWaitTargetTemp = float(CoolingWaitTargetTempStr)
                    # Ensure reasonable bounds (50-85°C)
                    if self.CoolingWaitTargetTemp < 50:
                        self.CoolingWaitTargetTemp = 50
                    elif self.CoolingWaitTargetTemp > 85:
                        self.CoolingWaitTargetTemp = 85
                except ValueError:
                    pass
            
            # Load CoolingWaitMaxSeconds
            CoolingWaitMaxSecondsStr = self.DatabaseManager.GetSystemSetting('CpuAffinityCoolingWaitMaxSeconds')
            if CoolingWaitMaxSecondsStr:
                try:
                    self.CoolingWaitMaxSeconds = int(CoolingWaitMaxSecondsStr)
                    # Ensure reasonable bounds (30-300 seconds)
                    if self.CoolingWaitMaxSeconds < 30:
                        self.CoolingWaitMaxSeconds = 30
                    elif self.CoolingWaitMaxSeconds > 300:
                        self.CoolingWaitMaxSeconds = 300
                except ValueError:
                    pass
            
            # Load ThermalGateEnabled
            ThermalGateEnabledStr = self.DatabaseManager.GetSystemSetting('ThermalGateEnabled')
            if ThermalGateEnabledStr:
                self.ThermalGateEnabled = ThermalGateEnabledStr.lower() in ('true', '1', 'yes')

            # Load ThermalGateMaxTemp
            ThermalGateMaxTempStr = self.DatabaseManager.GetSystemSetting('ThermalGateMaxTemp')
            if ThermalGateMaxTempStr:
                try:
                    self.ThermalGateMaxTemp = float(ThermalGateMaxTempStr)
                except ValueError:
                    pass

            # Load ThermalGateMinCoolCores
            ThermalGateMinCoolCoresStr = self.DatabaseManager.GetSystemSetting('ThermalGateMinCoolCores')
            if ThermalGateMinCoolCoresStr:
                try:
                    self.ThermalGateMinCoolCores = int(ThermalGateMinCoolCoresStr)
                except ValueError:
                    pass

            # Load ThermalPauseCriticalTemp
            ThermalPauseCriticalTempStr = self.DatabaseManager.GetSystemSetting('ThermalPauseCriticalTemp')
            if ThermalPauseCriticalTempStr:
                try:
                    self.ThermalPauseCriticalTemp = float(ThermalPauseCriticalTempStr)
                except ValueError:
                    pass

            # Load ThermalGateMaxWaitSeconds
            ThermalGateMaxWaitSecondsStr = self.DatabaseManager.GetSystemSetting('ThermalGateMaxWaitSeconds')
            if ThermalGateMaxWaitSecondsStr:
                try:
                    self.ThermalGateMaxWaitSeconds = int(ThermalGateMaxWaitSecondsStr)
                except ValueError:
                    pass

            # Load ThermalGateCheckInterval
            ThermalGateCheckIntervalStr = self.DatabaseManager.GetSystemSetting('ThermalGateCheckInterval')
            if ThermalGateCheckIntervalStr:
                try:
                    self.ThermalGateCheckInterval = int(ThermalGateCheckIntervalStr)
                    if self.ThermalGateCheckInterval < 5:
                        self.ThermalGateCheckInterval = 5
                except ValueError:
                    pass

            LoggingService.LogInfo(f"Loaded configuration: Enabled={self.CpuAffinityEnabled}, Threshold={self.TemperatureThreshold}°C, Interval={self.MonitoringInterval}s, CoolingWait={self.CoolingWaitEnabled}, CoolingWaitTarget={self.CoolingWaitTargetTemp}°C, ThermalGate={self.ThermalGateEnabled}, ThermalGateMaxTemp={self.ThermalGateMaxTemp}°C, ThermalPauseCriticalTemp={self.ThermalPauseCriticalTemp}°C",
                                 "CpuAffinityService", "_LoadConfiguration")
        except Exception as e:
            LoggingService.LogException("Error loading configuration", e, "CpuAffinityService", "_LoadConfiguration")
    
    def _InitializeCoreStates(self):
        """Initialize core states dictionary for all available cores."""
        try:
            TotalCores = psutil.cpu_count(logical=False) or psutil.cpu_count()
            with self.CoreStatesLock:
                for CoreNum in range(TotalCores):
                    if CoreNum not in self.CoreStates:
                        self.CoreStates[CoreNum] = {
                            "Status": "available",
                            "LastUsed": None,
                            "Temperature": None
                        }
            LoggingService.LogInfo(f"Initialized {TotalCores} core states", "CpuAffinityService", "_InitializeCoreStates")
        except Exception as e:
            LoggingService.LogException("Error initializing core states", e, "CpuAffinityService", "_InitializeCoreStates")
    
    def _GetCurrentTemperatures(self) -> Optional[Dict[str, Any]]:
        """Get current CPU temperatures, using cache if available."""
        try:
            # Check cache
            CurrentTime = datetime.now()
            if (self.TemperatureCache is not None and 
                self.TemperatureCacheTime is not None and
                (CurrentTime - self.TemperatureCacheTime).total_seconds() < self.TemperatureCacheValidSeconds):
                return self.TemperatureCache
            
            # Query SystemMonitoringService
            TempData = self.SystemMonitoringService.GetCpuTemperature()
            if TempData:
                self.TemperatureCache = TempData
                self.TemperatureCacheTime = CurrentTime
                LoggingService.LogDebug(f"Retrieved temperature data for {len(TempData.get('Cores', []))} cores", 
                                       "CpuAffinityService", "_GetCurrentTemperatures")
                return TempData
            
            return None
        except Exception as e:
            LoggingService.LogException("Error getting current temperatures", e, "CpuAffinityService", "_GetCurrentTemperatures")
            return None
    
    def _UpdateCoreTemperatures(self):
        """Update core state temperatures from SystemMonitoringService."""
        try:
            TempData = self._GetCurrentTemperatures()
            if not TempData or not TempData.get('Cores'):
                return
            
            with self.CoreStatesLock:
                for CoreInfo in TempData['Cores']:
                    CoreNum = CoreInfo.get('Core')
                    Temp = CoreInfo.get('Temperature')
                    if CoreNum is not None and CoreNum in self.CoreStates:
                        self.CoreStates[CoreNum]["Temperature"] = Temp
        except Exception as e:
            LoggingService.LogException("Error updating core temperatures", e, "CpuAffinityService", "_UpdateCoreTemperatures")
    
    def _SelectOptimalCores(self, CoreCount: int, ExcludeCores: List[int] = None) -> List[int]:
        """Select optimal cores based on temperature and spacing.
        
        Args:
            CoreCount: Number of cores to select
            ExcludeCores: List of core numbers to exclude from selection
            
        Returns:
            List of optimal core numbers
        """
        try:
            ExcludeCores = ExcludeCores or []
            
            # Update temperatures first
            self._UpdateCoreTemperatures()
            
            with self.CoreStatesLock:
                # Get available cores (not active, not cooling, not excluded)
                AvailableCores = []
                CurrentTime = datetime.now()
                
                for CoreNum, State in self.CoreStates.items():
                    if CoreNum in ExcludeCores:
                        continue
                    
                    Status = State.get("Status", "available")
                    LastUsed = State.get("LastUsed")
                    
                    # Check if core is in cooling period
                    if Status == "cooling" and LastUsed:
                        SecondsSinceRelease = (CurrentTime - LastUsed).total_seconds()
                        if SecondsSinceRelease < self.CoolingPeriodSeconds:
                            continue  # Still cooling
                        else:
                            # Cooling period expired, mark as available
                            State["Status"] = "available"
                    
                    if Status == "available":
                        Temp = State.get("Temperature")
                        AvailableCores.append({
                            "Core": CoreNum,
                            "Temperature": Temp if Temp is not None else 999.0  # Prefer cores with known temps
                        })
                
                # Sort by temperature (coolest first), then by core number
                AvailableCores.sort(key=lambda x: (x["Temperature"], x["Core"]))
                
                if len(AvailableCores) < CoreCount:
                    LoggingService.LogWarning(f"Only {len(AvailableCores)} available cores, requested {CoreCount}", 
                                            "CpuAffinityService", "_SelectOptimalCores")
                    # Return what we have
                    return [c["Core"] for c in AvailableCores]
                
                # Select cores with spacing (prefer spaced cores, but allow some temperature trade-off)
                SelectedCores = []
                UsedIndices = []
                
                # Start with the coolest cores
                for Candidate in AvailableCores:
                    if len(SelectedCores) >= CoreCount:
                        break
                    
                    CandidateCore = Candidate["Core"]
                    CandidateTemp = Candidate["Temperature"]
                    
                    # Check spacing: prefer cores that are at least 2-3 cores apart from already selected
                    TooClose = False
                    for SelectedCore in SelectedCores:
                        Distance = abs(CandidateCore - SelectedCore)
                        if Distance < 2:  # Too close (adjacent cores)
                            TooClose = True
                            break
                    
                    if not TooClose:
                        SelectedCores.append(CandidateCore)
                        UsedIndices.append(Candidate)
                    else:
                        # Check if this core is significantly cooler (more than 3°C difference)
                        # If so, prefer it even if closer
                        BestSelectedTemp = min([c["Temperature"] for c in UsedIndices] + [999.0])
                        if CandidateTemp < (BestSelectedTemp - 3.0):
                            # Significant temp difference, use it
                            SelectedCores.append(CandidateCore)
                            UsedIndices.append(Candidate)
                
                # If we still don't have enough cores, fill with remaining coolest (even if close)
                if len(SelectedCores) < CoreCount:
                    Remaining = [c for c in AvailableCores if c["Core"] not in SelectedCores]
                    Remaining.sort(key=lambda x: (x["Temperature"], x["Core"]))
                    for Candidate in Remaining:
                        if len(SelectedCores) >= CoreCount:
                            break
                        SelectedCores.append(Candidate["Core"])
                
                SelectedCores.sort()  # Sort for readability
                LoggingService.LogInfo(f"Selected {len(SelectedCores)} optimal cores: {SelectedCores}", 
                                     "CpuAffinityService", "_SelectOptimalCores")
                return SelectedCores
                
        except Exception as e:
            LoggingService.LogException("Error selecting optimal cores", e, "CpuAffinityService", "_SelectOptimalCores")
            # Fallback to sequential cores
            TotalCores = psutil.cpu_count(logical=False) or psutil.cpu_count()
            FallbackCores = list(range(min(CoreCount, TotalCores)))
            LoggingService.LogWarning(f"Falling back to sequential cores: {FallbackCores}", 
                                    "CpuAffinityService", "_SelectOptimalCores")
            return FallbackCores
    
    def GetOptimalCoresForTranscode(self, CoreCount: int) -> List[int]:
        """Get optimal cores for transcoding job.
        
        Args:
            CoreCount: Number of cores to allocate
            
        Returns:
            List of optimal core numbers
        """
        try:
            if not self.CpuAffinityEnabled:
                # Return sequential cores as fallback
                TotalCores = psutil.cpu_count(logical=False) or psutil.cpu_count()
                return list(range(min(CoreCount, TotalCores)))
            
            return self._SelectOptimalCores(CoreCount)
        except Exception as e:
            LoggingService.LogException("Error getting optimal cores for transcode", e, "CpuAffinityService", "GetOptimalCoresForTranscode")
            # Fallback
            TotalCores = psutil.cpu_count(logical=False) or psutil.cpu_count()
            return list(range(min(CoreCount, TotalCores)))
    
    def GetOptimalCoresForQualityTest(self, CoreCount: int) -> List[int]:
        """Get optimal cores for quality testing job.
        
        Args:
            CoreCount: Number of cores to allocate
            
        Returns:
            List of optimal core numbers
        """
        try:
            if not self.CpuAffinityEnabled:
                # Return sequential cores starting from 12 as fallback (original behavior)
                TotalCores = psutil.cpu_count(logical=False) or psutil.cpu_count()
                StartCore = min(12, TotalCores - CoreCount)
                return list(range(StartCore, min(StartCore + CoreCount, TotalCores)))
            
            # Exclude cores that might be used by transcoding (cores 0-9 typically)
            # But let the selection algorithm choose based on temp
            return self._SelectOptimalCores(CoreCount)
        except Exception as e:
            LoggingService.LogException("Error getting optimal cores for quality test", e, "CpuAffinityService", "GetOptimalCoresForQualityTest")
            # Fallback
            TotalCores = psutil.cpu_count(logical=False) or psutil.cpu_count()
            StartCore = min(12, TotalCores - CoreCount)
            return list(range(StartCore, min(StartCore + CoreCount, TotalCores)))
    
    def RegisterJob(self, JobId: int, ProcessPID: int, CoreList: List[int], JobType: str):
        """Register an active job with assigned cores.
        
        Args:
            JobId: Job identifier
            ProcessPID: Process ID
            CoreList: List of core numbers assigned to this job
            JobType: Type of job ("Transcode" or "QualityTest")
        """
        try:
            with self.ActiveJobsLock:
                self.ActiveJobs[JobId] = {
                    "ProcessPID": ProcessPID,
                    "CoreList": CoreList,
                    "StartTime": datetime.now(),
                    "JobType": JobType
                }
            
            with self.CoreStatesLock:
                CurrentTime = datetime.now()
                for CoreNum in CoreList:
                    if CoreNum in self.CoreStates:
                        self.CoreStates[CoreNum]["Status"] = "active"
                        self.CoreStates[CoreNum]["LastUsed"] = CurrentTime
            
            LoggingService.LogInfo(f"Registered {JobType} job {JobId} with PID {ProcessPID} on cores {CoreList}", 
                                 "CpuAffinityService", "RegisterJob")
        except Exception as e:
            LoggingService.LogException(f"Error registering job {JobId}", e, "CpuAffinityService", "RegisterJob")
    
    def IsSystemTooHotForNewJob(self, CoreCount: int) -> Dict[str, Any]:
        """Check if the system is too hot to start a new job.

        Args:
            CoreCount: Number of cores the job would use (0 = general check)

        Returns:
            Dictionary with Ready (bool), Reason (str), and diagnostic info
        """
        try:
            if not self.ThermalGateEnabled:
                return {"Ready": True}

            TempData = self._GetCurrentTemperatures()
            if not TempData:
                # Can't read temps — don't block
                return {"Ready": True, "Reason": "no_temp_data"}

            Cores = TempData.get('Cores', [])
            if not Cores:
                return {"Ready": True, "Reason": "no_core_data"}

            # Calculate average temperature across all cores
            CoreTemps = [c.get('Temperature') for c in Cores if c.get('Temperature') is not None]
            if not CoreTemps:
                return {"Ready": True, "Reason": "no_temp_readings"}

            AverageTemp = sum(CoreTemps) / len(CoreTemps)

            # Check critical temperature (queue-level pause)
            if AverageTemp >= self.ThermalPauseCriticalTemp:
                return {
                    "Ready": False,
                    "Reason": "critical_temp",
                    "AverageTemp": round(AverageTemp, 1),
                    "CriticalThreshold": self.ThermalPauseCriticalTemp
                }

            # Count cores below ThermalGateMaxTemp
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

        except Exception as e:
            LoggingService.LogException("Error checking thermal readiness", e, "CpuAffinityService", "IsSystemTooHotForNewJob")
            return {"Ready": True, "Reason": "error"}

    def WaitForThermalClearance(self, CoreCount: int) -> bool:
        """Wait for the system to cool enough before starting a new job.

        Loops calling IsSystemTooHotForNewJob, sleeping ThermalGateCheckInterval between checks.

        Args:
            CoreCount: Number of cores the job would use (0 = general check)

        Returns:
            True when clearance granted, False if ThermalGateMaxWaitSeconds exceeded
        """
        if not self.ThermalGateEnabled:
            return True

        try:
            # Initial check — fast path if already cool
            Result = self.IsSystemTooHotForNewJob(CoreCount)
            if Result.get("Ready", True):
                return True

            Reason = Result.get("Reason", "unknown")
            LoggingService.LogInfo(
                f"Waiting for thermal clearance (reason: {Reason}, avg temp: {Result.get('AverageTemp', 'N/A')}°C, "
                f"cool cores: {Result.get('CoolCores', 'N/A')}/{self.ThermalGateMinCoolCores})",
                "CpuAffinityService", "WaitForThermalClearance")

            StartTime = datetime.now()
            LastLogTime = StartTime

            while True:
                time.sleep(self.ThermalGateCheckInterval)

                ElapsedSeconds = (datetime.now() - StartTime).total_seconds()
                if ElapsedSeconds >= self.ThermalGateMaxWaitSeconds:
                    LoggingService.LogWarning(
                        f"Thermal clearance timeout after {ElapsedSeconds:.0f}s — allowing job to proceed anyway",
                        "CpuAffinityService", "WaitForThermalClearance")
                    return False

                Result = self.IsSystemTooHotForNewJob(CoreCount)
                if Result.get("Ready", True):
                    LoggingService.LogInfo(
                        f"Thermal clearance granted after {ElapsedSeconds:.0f}s (avg temp: {Result.get('AverageTemp', 'N/A')}°C, "
                        f"cool cores: {Result.get('CoolCores', 'N/A')})",
                        "CpuAffinityService", "WaitForThermalClearance")
                    return True

                # Log status every 30 seconds
                SecondsSinceLastLog = (datetime.now() - LastLogTime).total_seconds()
                if SecondsSinceLastLog >= 30:
                    LastLogTime = datetime.now()
                    LoggingService.LogInfo(
                        f"Still waiting for thermal clearance ({ElapsedSeconds:.0f}s elapsed, reason: {Result.get('Reason', 'unknown')}, "
                        f"avg temp: {Result.get('AverageTemp', 'N/A')}°C, cool cores: {Result.get('CoolCores', 'N/A')}/{self.ThermalGateMinCoolCores})",
                        "CpuAffinityService", "WaitForThermalClearance")

        except Exception as e:
            LoggingService.LogException("Error waiting for thermal clearance", e, "CpuAffinityService", "WaitForThermalClearance")
            return True  # On error, don't block — allow job to proceed

    def WaitForCoresToCool(self, CoreList: List[int]) -> bool:
        """Wait for cores to cool down below target temperature before proceeding.
        
        Args:
            CoreList: List of core numbers to wait for
            
        Returns:
            True if cores cooled down, False if timeout reached
        """
        if not self.CoolingWaitEnabled or not CoreList:
            return True  # Cooling wait disabled or no cores to wait for
        
        try:
            LoggingService.LogInfo(f"Waiting for cores {CoreList} to cool below {self.CoolingWaitTargetTemp}°C (max wait: {self.CoolingWaitMaxSeconds}s)", 
                                 "CpuAffinityService", "WaitForCoresToCool")
            
            StartTime = datetime.now()
            CheckCount = 0
            
            while True:
                # Update temperatures
                self._UpdateCoreTemperatures()
                
                # Check if max wait time exceeded
                ElapsedSeconds = (datetime.now() - StartTime).total_seconds()
                if ElapsedSeconds >= self.CoolingWaitMaxSeconds:
                    # Get current temps for logging
                    with self.CoreStatesLock:
                        CoreTemps = []
                        for CoreNum in CoreList:
                            if CoreNum in self.CoreStates:
                                Temp = self.CoreStates[CoreNum].get("Temperature")
                                if Temp is not None:
                                    CoreTemps.append(f"Core{CoreNum}={Temp}°C")
                    
                    LoggingService.LogWarning(f"Cooling wait timeout after {ElapsedSeconds:.1f}s. Cores may still be warm: {', '.join(CoreTemps) if CoreTemps else 'N/A'}", 
                                            "CpuAffinityService", "WaitForCoresToCool")
                    return False
                
                # Check if all cores are below target temperature
                AllCoresCool = True
                MaxTemp = None
                with self.CoreStatesLock:
                    for CoreNum in CoreList:
                        if CoreNum in self.CoreStates:
                            Temp = self.CoreStates[CoreNum].get("Temperature")
                            if Temp is not None:
                                if MaxTemp is None or Temp > MaxTemp:
                                    MaxTemp = Temp
                                if Temp >= self.CoolingWaitTargetTemp:
                                    AllCoresCool = False
                                    break
                
                if AllCoresCool:
                    ElapsedSeconds = (datetime.now() - StartTime).total_seconds()
                    LoggingService.LogInfo(f"Cores {CoreList} cooled below {self.CoolingWaitTargetTemp}°C after {ElapsedSeconds:.1f}s (max temp was {MaxTemp}°C)", 
                                         "CpuAffinityService", "WaitForCoresToCool")
                    return True
                
                # Wait before next check
                CheckCount += 1
                if CheckCount % 6 == 0:  # Log every 6 checks (~30 seconds at 5s intervals)
                    ElapsedSeconds = (datetime.now() - StartTime).total_seconds()
                    LoggingService.LogDebug(f"Cooling wait: {ElapsedSeconds:.1f}s elapsed, max temp: {MaxTemp}°C (target: <{self.CoolingWaitTargetTemp}°C)", 
                                          "CpuAffinityService", "WaitForCoresToCool")
                
                time.sleep(self.CoolingWaitCheckInterval)
                
        except Exception as e:
            LoggingService.LogException("Error waiting for cores to cool", e, "CpuAffinityService", "WaitForCoresToCool")
            return False  # On error, don't block - allow job to proceed
    
    def ReleaseJob(self, JobId: int, WaitForCooling: bool = True):
        """Release cores from a completed job (start cooling period).
        
        Args:
            JobId: Job identifier
            WaitForCooling: If True, wait for cores to cool before returning
        """
        try:
            with self.ActiveJobsLock:
                if JobId not in self.ActiveJobs:
                    LoggingService.LogWarning(f"Job {JobId} not found in active jobs", 
                                            "CpuAffinityService", "ReleaseJob")
                    return
                
                JobInfo = self.ActiveJobs[JobId]
                CoreList = JobInfo.get("CoreList", [])
                JobType = JobInfo.get("JobType", "Unknown")
                
                # Wait for cores to cool if enabled
                if WaitForCooling and self.CoolingWaitEnabled and CoreList:
                    CoresCooled = self.WaitForCoresToCool(CoreList)
                    if not CoresCooled:
                        LoggingService.LogWarning(f"Cooling wait completed with timeout for {JobType} job {JobId}", 
                                                "CpuAffinityService", "ReleaseJob")
                
                del self.ActiveJobs[JobId]
            
            CurrentTime = datetime.now()
            with self.CoreStatesLock:
                for CoreNum in CoreList:
                    if CoreNum in self.CoreStates:
                        self.CoreStates[CoreNum]["Status"] = "cooling"
                        self.CoreStates[CoreNum]["LastUsed"] = CurrentTime
            
            LoggingService.LogInfo(f"Released {JobType} job {JobId} from cores {CoreList} (started {self.CoolingPeriodSeconds}s cooling period)", 
                                 "CpuAffinityService", "ReleaseJob")
        except Exception as e:
            LoggingService.LogException(f"Error releasing job {JobId}", e, "CpuAffinityService", "ReleaseJob")
    
    def SetFFmpegProcessAffinity(self, ShellProcessPID: int, CoreCount: int, JobId: int, 
                                 JobType: str, ServiceName: str) -> Dict[str, Any]:
        """Set CPU affinity on FFmpeg child process using temperature-based core selection.
        
        This method centralizes all CPU affinity logic following MVVM and Single Responsibility:
        - Waits for child process to spawn
        - Finds FFmpeg child process from shell PID
        - Gets optimal cores based on temperature (coolest cores first)
        - Sets CPU affinity on FFmpeg process (not shell)
        - Registers job for monitoring
        
        Args:
            ShellProcessPID: Process ID of shell process that spawned FFmpeg
            CoreCount: Number of cores to allocate
            JobId: Job identifier for registration
            JobType: Type of job ("Transcode" or "QualityTest")
            ServiceName: Name of calling service for logging
            
        Returns:
            Dictionary with Success, FFmpegPID, AffinityCores, ErrorMessage
        """
        try:
            import time
            
            # Wait briefly for child process to spawn
            time.sleep(0.1)
            
            ShellProcess = psutil.Process(ShellProcessPID)
            
            # Get optimal cores based on job type (temperature-based selection)
            if JobType == "Transcode":
                AffinityCores = self.GetOptimalCoresForTranscode(CoreCount)
            elif JobType == "QualityTest":
                AffinityCores = self.GetOptimalCoresForQualityTest(CoreCount)
            else:
                ErrorMessage = f"Unknown JobType '{JobType}'. Must be 'Transcode' or 'QualityTest'."
                LoggingService.LogError(ErrorMessage, "CpuAffinityService", "SetFFmpegProcessAffinity")
                raise ValueError(ErrorMessage)
            
            LoggingService.LogInfo(f"Using CpuAffinityService to select {CoreCount} optimal cores for {JobType}: {AffinityCores}", 
                                 "CpuAffinityService", "SetFFmpegProcessAffinity")
            
            # Find the child FFmpeg process (recursive search)
            FFmpegProcess = None
            for child in ShellProcess.children(recursive=True):
                if 'ffmpeg' in child.name().lower():
                    FFmpegProcess = child
                    break
            
            if FFmpegProcess:
                # Set affinity on FFmpeg process (not shell)
                FFmpegProcess.cpu_affinity(AffinityCores)
                LoggingService.LogInfo(f"Set {JobType} FFmpeg CPU affinity to cores: {AffinityCores} (CoreCount: {CoreCount}, Shell PID: {ShellProcessPID}, FFmpeg PID: {FFmpegProcess.pid})", 
                                     "CpuAffinityService", "SetFFmpegProcessAffinity")
                
                # Register job with CpuAffinityService for monitoring
                try:
                    self.RegisterJob(JobId, FFmpegProcess.pid, AffinityCores, JobType)
                    
                    # Start monitoring if not already started
                    if not self.MonitoringActive:
                        self.StartMonitoring()
                    
                    return {
                        "Success": True,
                        "FFmpegPID": FFmpegProcess.pid,
                        "AffinityCores": AffinityCores,
                        "ErrorMessage": None
                    }
                except Exception as RegisterError:
                    LoggingService.LogWarning(f"Failed to register {JobType} job {JobId} with CpuAffinityService: {RegisterError}", 
                                            "CpuAffinityService", "SetFFmpegProcessAffinity")
                    return {
                        "Success": True,  # Affinity was set, even if registration failed
                        "FFmpegPID": FFmpegProcess.pid,
                        "AffinityCores": AffinityCores,
                        "ErrorMessage": f"Affinity set but registration failed: {str(RegisterError)}"
                    }
            else:
                ErrorMessage = f"Could not find child FFmpeg process for shell PID {ShellProcessPID}. CPU affinity not set."
                LoggingService.LogWarning(ErrorMessage, "CpuAffinityService", "SetFFmpegProcessAffinity")
                return {
                    "Success": False,
                    "FFmpegPID": None,
                    "AffinityCores": [],
                    "ErrorMessage": ErrorMessage
                }
                
        except psutil.NoSuchProcess:
            ErrorMessage = f"Shell process PID {ShellProcessPID} not found"
            LoggingService.LogWarning(ErrorMessage, "CpuAffinityService", "SetFFmpegProcessAffinity")
            return {
                "Success": False,
                "FFmpegPID": None,
                "AffinityCores": [],
                "ErrorMessage": ErrorMessage
            }
        except Exception as e:
            ErrorMessage = f"Error setting CPU affinity: {str(e)}"
            LoggingService.LogException(f"Failed to set CPU affinity for {JobType} job {JobId}", e, 
                                      "CpuAffinityService", "SetFFmpegProcessAffinity")
            return {
                "Success": False,
                "FFmpegPID": None,
                "AffinityCores": [],
                "ErrorMessage": ErrorMessage
            }
    
    def UpdateCoreAffinity(self, ProcessPID: int, NewCoreList: List[int]) -> bool:
        """Update CPU affinity for a running process (migration).
        
        Args:
            ProcessPID: Process ID
            NewCoreList: New list of core numbers
            
        Returns:
            True if successful, False otherwise
        """
        try:
            Process = psutil.Process(ProcessPID)
            Process.cpu_affinity(NewCoreList)
            
            # Update job tracking
            with self.ActiveJobsLock:
                for JobId, JobInfo in self.ActiveJobs.items():
                    if JobInfo.get("ProcessPID") == ProcessPID:
                        OldCoreList = JobInfo.get("CoreList", [])
                        JobInfo["CoreList"] = NewCoreList
                        JobType = JobInfo.get("JobType", "Unknown")
                        
                        # Update core states
                        CurrentTime = datetime.now()
                        with self.CoreStatesLock:
                            # Release old cores to cooling
                            for CoreNum in OldCoreList:
                                if CoreNum in self.CoreStates:
                                    self.CoreStates[CoreNum]["Status"] = "cooling"
                                    self.CoreStates[CoreNum]["LastUsed"] = CurrentTime
                            
                            # Mark new cores as active
                            for CoreNum in NewCoreList:
                                if CoreNum in self.CoreStates:
                                    self.CoreStates[CoreNum]["Status"] = "active"
                                    self.CoreStates[CoreNum]["LastUsed"] = CurrentTime
                        
                        LoggingService.LogInfo(f"Migrated {JobType} job {JobId} (PID {ProcessPID}) from cores {OldCoreList} to {NewCoreList}", 
                                             "CpuAffinityService", "UpdateCoreAffinity")
                        return True
            
            LoggingService.LogWarning(f"Process PID {ProcessPID} not found in active jobs for migration", 
                                    "CpuAffinityService", "UpdateCoreAffinity")
            return False
        except psutil.NoSuchProcess:
            LoggingService.LogWarning(f"Process PID {ProcessPID} not found for affinity update", 
                                    "CpuAffinityService", "UpdateCoreAffinity")
            return False
        except Exception as e:
            LoggingService.LogException(f"Error updating core affinity for PID {ProcessPID}", e, "CpuAffinityService", "UpdateCoreAffinity")
            return False
    
    def _MonitoringLoop(self):
        """Background monitoring loop for active jobs."""
        LoggingService.LogInfo("CPU affinity monitoring thread started", "CpuAffinityService", "_MonitoringLoop")
        
        while not self.StopMonitoringEvent.is_set():
            try:
                # Check if monitoring should be active
                if not self.CpuAffinityEnabled:
                    time.sleep(self.MonitoringInterval)
                    continue
                
                # Get active jobs
                JobsToCheck = []
                with self.ActiveJobsLock:
                    JobsToCheck = list(self.ActiveJobs.items())
                
                if not JobsToCheck:
                    # No active jobs, sleep and continue
                    time.sleep(self.MonitoringInterval)
                    continue
                
                # Update core temperatures
                self._UpdateCoreTemperatures()
                
                # Check each active job for overheating cores
                for JobId, JobInfo in JobsToCheck:
                    ProcessPID = JobInfo.get("ProcessPID")
                    CoreList = JobInfo.get("CoreList", [])
                    JobType = JobInfo.get("JobType", "Unknown")
                    
                    # Check if process still exists
                    try:
                        Process = psutil.Process(ProcessPID)
                        if not Process.is_running():
                            # Process died, release cores
                            LoggingService.LogWarning(f"Process PID {ProcessPID} for job {JobId} is not running, releasing cores", 
                                                    "CpuAffinityService", "_MonitoringLoop")
                            self.ReleaseJob(JobId)
                            continue
                    except psutil.NoSuchProcess:
                        # Process doesn't exist, release cores
                        LoggingService.LogWarning(f"Process PID {ProcessPID} for job {JobId} not found, releasing cores", 
                                                "CpuAffinityService", "_MonitoringLoop")
                        self.ReleaseJob(JobId)
                        continue
                    
                    # Log temperatures for all cores (for crash diagnosis)
                    with self.CoreStatesLock:
                        CoreTemps = []
                        MaxTemp = None
                        OverheatedCores = []
                        for CoreNum in CoreList:
                            State = self.CoreStates.get(CoreNum)
                            if State:
                                Temp = State.get("Temperature")
                                if Temp is not None:
                                    CoreTemps.append(f"Core{CoreNum}={Temp}°C")
                                    if MaxTemp is None or Temp > MaxTemp:
                                        MaxTemp = Temp
                                    if Temp >= self.TemperatureThreshold:
                                        OverheatedCores.append(CoreNum)
                        
                        if CoreTemps:
                            LoggingService.LogDebug(f"{JobType} job {JobId} (PID {ProcessPID}) core temps: {', '.join(CoreTemps)}, Max={MaxTemp}°C", 
                                                   "CpuAffinityService", "_MonitoringLoop")
                    
                    # Check for overheating (migration threshold)
                    if OverheatedCores:
                        LoggingService.LogWarning(f"{JobType} job {JobId} (PID {ProcessPID}) has overheated cores {OverheatedCores} (≥{self.TemperatureThreshold}°C), attempting migration", 
                                                "CpuAffinityService", "_MonitoringLoop")
                        
                        # Find cooler available cores
                        NewCoreList = self._SelectOptimalCores(len(CoreList), ExcludeCores=CoreList)
                        
                        if NewCoreList and len(NewCoreList) == len(CoreList):
                            # Migrate to new cores
                            if self.UpdateCoreAffinity(ProcessPID, NewCoreList):
                                LoggingService.LogInfo(f"Successfully migrated {JobType} job {JobId} from {CoreList} to {NewCoreList}", 
                                                     "CpuAffinityService", "_MonitoringLoop")
                            else:
                                LoggingService.LogWarning(f"Failed to migrate {JobType} job {JobId} to cores {NewCoreList}", 
                                                        "CpuAffinityService", "_MonitoringLoop")
                        else:
                            LoggingService.LogWarning(f"Cannot migrate {JobType} job {JobId}: insufficient available cores (needed {len(CoreList)}, found {len(NewCoreList)})", 
                                                    "CpuAffinityService", "_MonitoringLoop")
                
                # Sleep until next check
                self.StopMonitoringEvent.wait(self.MonitoringInterval)
                
            except Exception as e:
                LoggingService.LogException("Error in monitoring loop", e, "CpuAffinityService", "_MonitoringLoop")
                time.sleep(self.MonitoringInterval)  # Sleep on error to prevent tight loop
        
        LoggingService.LogInfo("CPU affinity monitoring thread stopped", "CpuAffinityService", "_MonitoringLoop")
    
    def StartMonitoring(self):
        """Start background monitoring thread."""
        try:
            if self.MonitoringActive:
                LoggingService.LogWarning("Monitoring thread already active", "CpuAffinityService", "StartMonitoring")
                return
            
            if not self.CpuAffinityEnabled:
                LoggingService.LogInfo("CPU affinity monitoring disabled, not starting thread", "CpuAffinityService", "StartMonitoring")
                return
            
            self.StopMonitoringEvent.clear()
            self.MonitoringActive = True
            self.MonitoringThread = threading.Thread(target=self._MonitoringLoop, daemon=True)
            self.MonitoringThread.start()
            LoggingService.LogInfo(f"Started CPU affinity monitoring thread (interval: {self.MonitoringInterval}s)", 
                                 "CpuAffinityService", "StartMonitoring")
        except Exception as e:
            LoggingService.LogException("Error starting monitoring thread", e, "CpuAffinityService", "StartMonitoring")
            self.MonitoringActive = False
    
    def StopMonitoring(self):
        """Stop background monitoring thread."""
        try:
            if not self.MonitoringActive:
                return
            
            self.MonitoringActive = False
            self.StopMonitoringEvent.set()
            
            if self.MonitoringThread and self.MonitoringThread.is_alive():
                self.MonitoringThread.join(timeout=5.0)
            
            LoggingService.LogInfo("Stopped CPU affinity monitoring thread", "CpuAffinityService", "StopMonitoring")
        except Exception as e:
            LoggingService.LogException("Error stopping monitoring thread", e, "CpuAffinityService", "StopMonitoring")
    
    def GetCoreStatus(self, CoreNumber: int) -> Dict[str, Any]:
        """Get current status of a specific core.
        
        Args:
            CoreNumber: Core number
            
        Returns:
            Dictionary with core status information
        """
        try:
            with self.CoreStatesLock:
                if CoreNumber not in self.CoreStates:
                    return {"Core": CoreNumber, "Status": "unknown", "Temperature": None, "LastUsed": None}
                
                State = self.CoreStates[CoreNumber]
                return {
                    "Core": CoreNumber,
                    "Status": State.get("Status", "unknown"),
                    "Temperature": State.get("Temperature"),
                    "LastUsed": State.get("LastUsed")
                }
        except Exception as e:
            LoggingService.LogException(f"Error getting core status for core {CoreNumber}", e, "CpuAffinityService", "GetCoreStatus")
            return {"Core": CoreNumber, "Status": "error", "Temperature": None, "LastUsed": None}
    
    def GetAllCoreStatuses(self) -> Dict[int, Dict[str, Any]]:
        """Get status of all cores.
        
        Returns:
            Dictionary mapping core numbers to their status
        """
        try:
            TotalCores = psutil.cpu_count(logical=False) or psutil.cpu_count()
            AllStatuses = {}
            with self.CoreStatesLock:
                for CoreNum in range(TotalCores):
                    AllStatuses[CoreNum] = self.GetCoreStatus(CoreNum)
            return AllStatuses
        except Exception as e:
            LoggingService.LogException("Error getting all core statuses", e, "CpuAffinityService", "GetAllCoreStatuses")
            return {}


# Global instance for easy access
CpuAffinityServiceInstance = None

def GetCpuAffinityServiceInstance() -> CpuAffinityService:
    """Get the global CpuAffinityService instance."""
    global CpuAffinityServiceInstance
    if CpuAffinityServiceInstance is None:
        CpuAffinityServiceInstance = CpuAffinityService.GetInstance()
    return CpuAffinityServiceInstance

