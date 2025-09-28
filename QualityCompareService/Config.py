"""
QualityCompareService Configuration Management
Handles configuration settings and environment variables.
"""

import os
from typing import Dict, Any, Optional
from datetime import datetime


class QualityCompareServiceConfig:
    """Configuration management for QualityCompareService."""
    
    def __init__(self):
        """Initialize configuration with default values."""
        self.ServiceName = "QualityCompareService"
        self.Version = "1.0.0"
        self.ServiceType = "QualityTesting"
        
        # Database settings
        self.DatabasePath = self.GetEnvironmentVariable("MEDIAVORTEX_DATABASE_PATH", "Data/MediaVortex.db")
        self.DatabaseConnectionTimeout = int(self.GetEnvironmentVariable("DATABASE_CONNECTION_TIMEOUT", "30"))
        
        # Processing settings
        self.MaxConcurrentJobs = int(self.GetEnvironmentVariable("QUALITY_COMPARE_MAX_CONCURRENT_JOBS", "1"))
        self.ProcessingInterval = int(self.GetEnvironmentVariable("QUALITY_COMPARE_PROCESSING_INTERVAL", "5"))
        self.HealthCheckInterval = int(self.GetEnvironmentVariable("QUALITY_COMPARE_HEALTH_CHECK_INTERVAL", "30"))
        
        # Quality testing settings
        self.DefaultVMAFThreshold = float(self.GetEnvironmentVariable("QUALITY_COMPARE_DEFAULT_VMAF_THRESHOLD", "90.0"))
        self.DefaultMaxAttempts = int(self.GetEnvironmentVariable("QUALITY_COMPARE_DEFAULT_MAX_ATTEMPTS", "3"))
        self.DefaultStrategyType = self.GetEnvironmentVariable("QUALITY_COMPARE_DEFAULT_STRATEGY_TYPE", "Single")
        
        # FFmpeg settings
        self.FFmpegPath = self.GetEnvironmentVariable("FFMPEG_PATH", "")
        self.VMAFQualityWidth = int(self.GetEnvironmentVariable("VMAF_QUALITY_WIDTH", "1280"))
        self.VMAFQualityHeight = int(self.GetEnvironmentVariable("VMAF_QUALITY_HEIGHT", "720"))
        
        # Logging settings
        self.LogLevel = self.GetEnvironmentVariable("QUALITY_COMPARE_LOG_LEVEL", "INFO")
        self.LogToDatabase = self.GetEnvironmentVariable("QUALITY_COMPARE_LOG_TO_DATABASE", "true").lower() == "true"
        
        # Service management
        self.MaxErrors = int(self.GetEnvironmentVariable("QUALITY_COMPARE_MAX_ERRORS", "10"))
        self.RestartOnCrash = self.GetEnvironmentVariable("QUALITY_COMPARE_RESTART_ON_CRASH", "true").lower() == "true"
        self.GracefulShutdownTimeout = int(self.GetEnvironmentVariable("QUALITY_COMPARE_SHUTDOWN_TIMEOUT", "30"))
        
        # File system settings
        self.TempDirectory = self.GetEnvironmentVariable("QUALITY_COMPARE_TEMP_DIRECTORY", "Temp/QualityCompare")
        self.ResultsDirectory = self.GetEnvironmentVariable("QUALITY_COMPARE_RESULTS_DIRECTORY", "Results/QualityCompare")
        
        # Performance settings
        self.MemoryLimitMB = int(self.GetEnvironmentVariable("QUALITY_COMPARE_MEMORY_LIMIT_MB", "2048"))
        self.CPULimitPercent = float(self.GetEnvironmentVariable("QUALITY_COMPARE_CPU_LIMIT_PERCENT", "80.0"))
        
        # Strategy settings
        self.EnableSkipStrategy = self.GetEnvironmentVariable("QUALITY_COMPARE_ENABLE_SKIP_STRATEGY", "true").lower() == "true"
        self.EnableSingleStrategy = self.GetEnvironmentVariable("QUALITY_COMPARE_ENABLE_SINGLE_STRATEGY", "true").lower() == "true"
        self.EnableMultiStrategy = self.GetEnvironmentVariable("QUALITY_COMPARE_ENABLE_MULTI_STRATEGY", "true").lower() == "true"
        self.EnableCustomStrategy = self.GetEnvironmentVariable("QUALITY_COMPARE_ENABLE_CUSTOM_STRATEGY", "true").lower() == "true"
        
        # Multi-testing settings
        self.MaxAlternativeProfiles = int(self.GetEnvironmentVariable("QUALITY_COMPARE_MAX_ALTERNATIVE_PROFILES", "5"))
        self.MultiTestingTimeout = int(self.GetEnvironmentVariable("QUALITY_COMPARE_MULTI_TESTING_TIMEOUT", "3600"))  # 1 hour
        
        # Result management
        self.KeepResultsForDays = int(self.GetEnvironmentVariable("QUALITY_COMPARE_KEEP_RESULTS_DAYS", "30"))
        self.AutoCleanupResults = self.GetEnvironmentVariable("QUALITY_COMPARE_AUTO_CLEANUP_RESULTS", "true").lower() == "true"
        
        # Notification settings
        self.EnableNotifications = self.GetEnvironmentVariable("QUALITY_COMPARE_ENABLE_NOTIFICATIONS", "false").lower() == "true"
        self.NotificationWebhook = self.GetEnvironmentVariable("QUALITY_COMPARE_NOTIFICATION_WEBHOOK", "")
        
        # Debug settings
        self.DebugMode = self.GetEnvironmentVariable("QUALITY_COMPARE_DEBUG_MODE", "false").lower() == "true"
        self.VerboseLogging = self.GetEnvironmentVariable("QUALITY_COMPARE_VERBOSE_LOGGING", "false").lower() == "true"
        
        # Configuration validation
        self.ValidateConfiguration()
    
    def GetEnvironmentVariable(self, key: str, defaultValue: str) -> str:
        """Get environment variable with default value."""
        return os.environ.get(key, defaultValue)
    
    def ValidateConfiguration(self):
        """Validate configuration settings."""
        try:
            # Validate numeric settings
            if self.MaxConcurrentJobs < 1 or self.MaxConcurrentJobs > 10:
                raise ValueError("MaxConcurrentJobs must be between 1 and 10")
            
            if self.DefaultVMAFThreshold < 0 or self.DefaultVMAFThreshold > 100:
                raise ValueError("DefaultVMAFThreshold must be between 0 and 100")
            
            if self.DefaultMaxAttempts < 1 or self.DefaultMaxAttempts > 10:
                raise ValueError("DefaultMaxAttempts must be between 1 and 10")
            
            if self.VMAFQualityWidth < 320 or self.VMAFQualityWidth > 7680:
                raise ValueError("VMAFQualityWidth must be between 320 and 7680")
            
            if self.VMAFQualityHeight < 240 or self.VMAFQualityHeight > 4320:
                raise ValueError("VMAFQualityHeight must be between 240 and 4320")
            
            # Validate strategy type
            validStrategyTypes = ["Skip", "Single", "Multi", "Custom"]
            if self.DefaultStrategyType not in validStrategyTypes:
                raise ValueError(f"DefaultStrategyType must be one of: {validStrategyTypes}")
            
            # Validate log level
            validLogLevels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            if self.LogLevel not in validLogLevels:
                raise ValueError(f"LogLevel must be one of: {validLogLevels}")
            
        except Exception as e:
            raise ValueError(f"Configuration validation failed: {str(e)}")
    
    def GetDatabaseConnectionString(self) -> str:
        """Get database connection string."""
        return f"sqlite:///{self.DatabasePath}"
    
    def GetTempDirectoryPath(self) -> str:
        """Get temporary directory path."""
        return os.path.abspath(self.TempDirectory)
    
    def GetResultsDirectoryPath(self) -> str:
        """Get results directory path."""
        return os.path.abspath(self.ResultsDirectory)
    
    def IsStrategyEnabled(self, strategyType: str) -> bool:
        """Check if a strategy type is enabled."""
        strategyMap = {
            "Skip": self.EnableSkipStrategy,
            "Single": self.EnableSingleStrategy,
            "Multi": self.EnableMultiStrategy,
            "Custom": self.EnableCustomStrategy
        }
        return strategyMap.get(strategyType, False)
    
    def GetQualityTestingSettings(self) -> Dict[str, Any]:
        """Get quality testing specific settings."""
        return {
            "DefaultVMAFThreshold": self.DefaultVMAFThreshold,
            "DefaultMaxAttempts": self.DefaultMaxAttempts,
            "DefaultStrategyType": self.DefaultStrategyType,
            "MaxAlternativeProfiles": self.MaxAlternativeProfiles,
            "MultiTestingTimeout": self.MultiTestingTimeout,
            "VMAFQualityWidth": self.VMAFQualityWidth,
            "VMAFQualityHeight": self.VMAFQualityHeight
        }
    
    def GetServiceSettings(self) -> Dict[str, Any]:
        """Get service management settings."""
        return {
            "ServiceName": self.ServiceName,
            "Version": self.Version,
            "ServiceType": self.ServiceType,
            "MaxConcurrentJobs": self.MaxConcurrentJobs,
            "ProcessingInterval": self.ProcessingInterval,
            "HealthCheckInterval": self.HealthCheckInterval,
            "MaxErrors": self.MaxErrors,
            "RestartOnCrash": self.RestartOnCrash,
            "GracefulShutdownTimeout": self.GracefulShutdownTimeout
        }
    
    def GetPerformanceSettings(self) -> Dict[str, Any]:
        """Get performance monitoring settings."""
        return {
            "MemoryLimitMB": self.MemoryLimitMB,
            "CPULimitPercent": self.CPULimitPercent,
            "KeepResultsForDays": self.KeepResultsForDays,
            "AutoCleanupResults": self.AutoCleanupResults
        }
    
    def GetLoggingSettings(self) -> Dict[str, Any]:
        """Get logging configuration settings."""
        return {
            "LogLevel": self.LogLevel,
            "LogToDatabase": self.LogToDatabase,
            "DebugMode": self.DebugMode,
            "VerboseLogging": self.VerboseLogging
        }
    
    def ToDict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "ServiceName": self.ServiceName,
            "Version": self.Version,
            "ServiceType": self.ServiceType,
            "DatabasePath": self.DatabasePath,
            "DatabaseConnectionTimeout": self.DatabaseConnectionTimeout,
            "MaxConcurrentJobs": self.MaxConcurrentJobs,
            "ProcessingInterval": self.ProcessingInterval,
            "HealthCheckInterval": self.HealthCheckInterval,
            "DefaultVMAFThreshold": self.DefaultVMAFThreshold,
            "DefaultMaxAttempts": self.DefaultMaxAttempts,
            "DefaultStrategyType": self.DefaultStrategyType,
            "FFmpegPath": self.FFmpegPath,
            "VMAFQualityWidth": self.VMAFQualityWidth,
            "VMAFQualityHeight": self.VMAFQualityHeight,
            "LogLevel": self.LogLevel,
            "LogToDatabase": self.LogToDatabase,
            "MaxErrors": self.MaxErrors,
            "RestartOnCrash": self.RestartOnCrash,
            "GracefulShutdownTimeout": self.GracefulShutdownTimeout,
            "TempDirectory": self.TempDirectory,
            "ResultsDirectory": self.ResultsDirectory,
            "MemoryLimitMB": self.MemoryLimitMB,
            "CPULimitPercent": self.CPULimitPercent,
            "EnableSkipStrategy": self.EnableSkipStrategy,
            "EnableSingleStrategy": self.EnableSingleStrategy,
            "EnableMultiStrategy": self.EnableMultiStrategy,
            "EnableCustomStrategy": self.EnableCustomStrategy,
            "MaxAlternativeProfiles": self.MaxAlternativeProfiles,
            "MultiTestingTimeout": self.MultiTestingTimeout,
            "KeepResultsForDays": self.KeepResultsForDays,
            "AutoCleanupResults": self.AutoCleanupResults,
            "EnableNotifications": self.EnableNotifications,
            "NotificationWebhook": self.NotificationWebhook,
            "DebugMode": self.DebugMode,
            "VerboseLogging": self.VerboseLogging
        }
