"""
TranscodeService Configuration
Manages configuration settings for the transcoding microservice
"""

import os
from typing import Dict, Any

class TranscodeServiceConfig:
    """Configuration class for TranscodeService."""
    
    def __init__(self):
        """Initialize configuration with default values."""
        self.DatabasePath = self.GetDatabasePath()
        self.LogLevel = self.GetLogLevel()
        self.MaxConcurrentJobs = self.GetMaxConcurrentJobs()
        self.HealthCheckInterval = self.GetHealthCheckInterval()
        self.ProcessingCheckInterval = self.GetProcessingCheckInterval()
        self.LogFile = self.GetLogFile()
        self.ServiceName = "TranscodeService"
        self.Version = "1.0.0"
    
    def GetDatabasePath(self) -> str:
        """Get database path from environment or use default."""
        return os.environ.get('MEDIAVORTEX_DB_PATH', 'Data/MediaVortex.db')
    
    def GetLogLevel(self) -> str:
        """Get log level from environment or use default."""
        return os.environ.get('TRANSCODE_LOG_LEVEL', 'INFO').upper()
    
    def GetMaxConcurrentJobs(self) -> int:
        """Get max concurrent jobs from environment or use default."""
        try:
            return int(os.environ.get('TRANSCODE_MAX_JOBS', '1'))
        except ValueError:
            return 1
    
    def GetHealthCheckInterval(self) -> int:
        """Get health check interval from environment or use default."""
        try:
            return int(os.environ.get('TRANSCODE_HEALTH_INTERVAL', '30'))
        except ValueError:
            return 30
    
    def GetProcessingCheckInterval(self) -> int:
        """Get processing check interval from environment or use default."""
        try:
            return int(os.environ.get('TRANSCODE_PROCESSING_INTERVAL', '10'))
        except ValueError:
            return 10
    
    def GetLogFile(self) -> str:
        """Get log file path from environment or use default."""
        return os.environ.get('TRANSCODE_LOG_FILE', 'TranscodeService.log')
    
    def GetConfigDict(self) -> Dict[str, Any]:
        """Get configuration as dictionary."""
        return {
            'DatabasePath': self.DatabasePath,
            'LogLevel': self.LogLevel,
            'MaxConcurrentJobs': self.MaxConcurrentJobs,
            'HealthCheckInterval': self.HealthCheckInterval,
            'ProcessingCheckInterval': self.ProcessingCheckInterval,
            'LogFile': self.LogFile,
            'ServiceName': self.ServiceName,
            'Version': self.Version
        }
    
    def ValidateConfig(self) -> bool:
        """Validate configuration settings."""
        try:
            # Check if database path exists
            if not os.path.exists(self.DatabasePath):
                print(f"Warning: Database path does not exist: {self.DatabasePath}")
            
            # Validate log level
            valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
            if self.LogLevel not in valid_log_levels:
                print(f"Warning: Invalid log level {self.LogLevel}, using INFO")
                self.LogLevel = 'INFO'
            
            # Validate numeric values
            if self.MaxConcurrentJobs < 1 or self.MaxConcurrentJobs > 5:
                print(f"Warning: MaxConcurrentJobs must be between 1-5, using 1")
                self.MaxConcurrentJobs = 1
            
            if self.HealthCheckInterval < 10:
                print(f"Warning: HealthCheckInterval too low, using 30")
                self.HealthCheckInterval = 30
            
            if self.ProcessingCheckInterval < 5:
                print(f"Warning: ProcessingCheckInterval too low, using 10")
                self.ProcessingCheckInterval = 10
            
            return True
            
        except Exception as e:
            print(f"Error validating configuration: {str(e)}")
            return False
    
    def PrintConfig(self):
        """Print current configuration."""
        print("TranscodeService Configuration:")
        print(f"  Database Path: {self.DatabasePath}")
        print(f"  Log Level: {self.LogLevel}")
        print(f"  Max Concurrent Jobs: {self.MaxConcurrentJobs}")
        print(f"  Health Check Interval: {self.HealthCheckInterval}s")
        print(f"  Processing Check Interval: {self.ProcessingCheckInterval}s")
        print(f"  Log File: {self.LogFile}")
        print(f"  Service Name: {self.ServiceName}")
        print(f"  Version: {self.Version}")

# Global configuration instance
config = TranscodeServiceConfig()
