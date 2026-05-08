"""
QualityTestService Configuration
"""

import os
from typing import Dict, Any

class QualityTestServiceConfig:
    """Configuration for QualityTestService."""
    
    def __init__(self):
        """Initialize configuration with default values."""
        self.DatabasePath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Data', 'MediaVortex.db')
        self.LogLevel = os.getenv('MEDIAVORTEX_LOG_LEVEL', 'INFO')
        self.HealthCheckInterval = int(os.getenv('MEDIAVORTEX_HEALTH_CHECK_INTERVAL', '30'))
        self.ServiceStartupTimeout = int(os.getenv('MEDIAVORTEX_SERVICE_STARTUP_TIMEOUT', '60'))
        self.MaxServiceRestarts = int(os.getenv('MEDIAVORTEX_MAX_SERVICE_RESTARTS', '3'))
        
        # Quality testing specific settings
        self.MaxConcurrentJobs = int(os.getenv('MEDIAVORTEX_MAX_CONCURRENT_JOBS', '1'))
        self.VMAFTimeout = int(os.getenv('MEDIAVORTEX_VMAF_TIMEOUT', '300'))  # 5 minutes
        self.WorkerSleepInterval = int(os.getenv('MEDIAVORTEX_WORKER_SLEEP_INTERVAL', '5'))
        
        # Service configurations
        self.ServiceInfo = {
            'Name': 'QualityTestService',
            'ServiceType': 'Microservice',
            'Version': '1.0.0',
            'Dependencies': ['MediaVortex'],
            'StartupTimeout': 45
        }
    
    def GetDatabasePath(self) -> str:
        """Get the database path."""
        return self.DatabasePath
    
    def GetLogLevel(self) -> str:
        """Get the log level."""
        return self.LogLevel
    
    def GetHealthCheckInterval(self) -> int:
        """Get the health check interval in seconds."""
        return self.HealthCheckInterval
    
    def GetServiceStartupTimeout(self) -> int:
        """Get the service startup timeout in seconds."""
        return self.ServiceStartupTimeout
    
    def GetMaxServiceRestarts(self) -> int:
        """Get the maximum number of service restarts."""
        return self.MaxServiceRestarts
    
    def GetMaxConcurrentJobs(self) -> int:
        """Get the maximum number of concurrent quality test jobs."""
        return self.MaxConcurrentJobs
    
    def GetVMAFTimeout(self) -> int:
        """Get the VMAF analysis timeout in seconds."""
        return self.VMAFTimeout
    
    def GetWorkerSleepInterval(self) -> int:
        """Get the worker sleep interval in seconds."""
        return self.WorkerSleepInterval
    
    def GetServiceInfo(self) -> Dict[str, Any]:
        """Get service information."""
        return self.ServiceInfo
