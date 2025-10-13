"""
WebService Configuration
"""

import os
from typing import Dict, Any

class WebServiceConfig:
    """Configuration for WebService."""
    
    def __init__(self):
        """Initialize configuration with default values."""
        self.DatabasePath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Data', 'MediaVortex.db')
        self.LogLevel = os.getenv('MEDIAVORTEX_LOG_LEVEL', 'INFO')
        self.HealthCheckInterval = int(os.getenv('MEDIAVORTEX_HEALTH_CHECK_INTERVAL', '30'))
        self.ServiceStartupTimeout = int(os.getenv('MEDIAVORTEX_SERVICE_STARTUP_TIMEOUT', '60'))
        self.MaxServiceRestarts = int(os.getenv('MEDIAVORTEX_MAX_SERVICE_RESTARTS', '3'))
        
        # Web service specific settings
        self.Host = os.getenv('MEDIAVORTEX_HOST', '0.0.0.0')
        self.Port = int(os.getenv('MEDIAVORTEX_PORT', '5000'))
        self.Debug = os.getenv('MEDIAVORTEX_DEBUG', 'False').lower() == 'true'
        self.SecretKey = os.getenv('MEDIAVORTEX_SECRET_KEY', 'mediavortex-secret-key-2024')
        
        # Service configurations
        self.ServiceInfo = {
            'Name': 'WebService',
            'ServiceType': 'WebApplication',
            'Version': '1.0.0',
            'Dependencies': [],
            'StartupTimeout': 30
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
    
    def GetHost(self) -> str:
        """Get the host address."""
        return self.Host
    
    def GetPort(self) -> int:
        """Get the port number."""
        return self.Port
    
    def GetDebug(self) -> bool:
        """Get the debug flag."""
        return self.Debug
    
    def GetSecretKey(self) -> str:
        """Get the secret key."""
        return self.SecretKey
    
    def GetServiceInfo(self) -> Dict[str, Any]:
        """Get service information."""
        return self.ServiceInfo
