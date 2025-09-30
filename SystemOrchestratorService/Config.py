"""
SystemOrchestratorService Configuration
"""

import os
from typing import Dict, Any

class SystemOrchestratorConfig:
    """Configuration for SystemOrchestratorService."""
    
    def __init__(self):
        """Initialize configuration with default values."""
        self.DatabasePath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Data', 'MediaVortex.db')
        self.LogLevel = os.getenv('MEDIAVORTEX_LOG_LEVEL', 'INFO')
        self.HealthCheckInterval = int(os.getenv('MEDIAVORTEX_HEALTH_CHECK_INTERVAL', '30'))
        self.ServiceStartupTimeout = int(os.getenv('MEDIAVORTEX_SERVICE_STARTUP_TIMEOUT', '60'))
        self.MaxServiceRestarts = int(os.getenv('MEDIAVORTEX_MAX_SERVICE_RESTARTS', '3'))
        
        # Service configurations
        self.Services = {
            'MediaVortex': {
                'Port': 5000,
                'Dependencies': [],
                'StartupTimeout': 30
            },
            'TranscodeService': {
                'Port': None,
                'Dependencies': ['MediaVortex'],
                'StartupTimeout': 45
            },
            'QualityCompareService': {
                'Port': None,
                'Dependencies': ['MediaVortex'],
                'StartupTimeout': 45
            }
        }
    
    def GetServiceConfig(self, service_name: str) -> Dict[str, Any]:
        """Get configuration for a specific service."""
        return self.Services.get(service_name, {})
    
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
