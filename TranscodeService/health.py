"""
TranscodeService Health Monitoring
Handles health checks and service status monitoring
"""

import os
import time
import psutil
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class HealthMonitor:
    """Health monitoring for TranscodeService."""
    
    def __init__(self, database_manager=None):
        """Initialize health monitor."""
        self.DatabaseManager = database_manager
        self.StartTime = datetime.now(timezone.utc)
        self.LastHealthCheck = None
        self.HealthStatus = "Unknown"
        self.ErrorCount = 0
        self.MaxErrors = 5
        
    def CheckHealth(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        try:
            health_data = {
                "ServiceName": "TranscodeService",
                "Status": "Healthy",
                "Timestamp": datetime.now(timezone.utc).isoformat(),
                "Uptime": self.GetUptime(),
                "MemoryUsage": self.GetMemoryUsage(),
                "CPUUsage": self.GetCPUUsage(),
                "DatabaseConnection": self.CheckDatabaseConnection(),
                "DiskSpace": self.CheckDiskSpace(),
                "LastHealthCheck": self.LastHealthCheck,
                "ErrorCount": self.ErrorCount
            }
            
            # Determine overall health status
            if not health_data["DatabaseConnection"]:
                health_data["Status"] = "Unhealthy"
                health_data["Issues"] = ["Database connection failed"]
            elif health_data["MemoryUsage"] > 90:
                health_data["Status"] = "Warning"
                health_data["Issues"] = ["High memory usage"]
            elif health_data["DiskSpace"] < 10:
                health_data["Status"] = "Warning"
                health_data["Issues"] = ["Low disk space"]
            else:
                health_data["Status"] = "Healthy"
                health_data["Issues"] = []
            
            self.HealthStatus = health_data["Status"]
            self.LastHealthCheck = datetime.now(timezone.utc)
            
            # Reset error count on successful health check
            if health_data["Status"] == "Healthy":
                self.ErrorCount = 0
            
            return health_data
            
        except Exception as e:
            logger.error(f"Error during health check: {str(e)}")
            self.ErrorCount += 1
            return {
                "ServiceName": "TranscodeService",
                "Status": "Unhealthy",
                "Timestamp": datetime.now(timezone.utc).isoformat(),
                "Error": str(e),
                "ErrorCount": self.ErrorCount
            }
    
    def GetUptime(self) -> str:
        """Get service uptime."""
        try:
            from Core.DateTimeHelpers import AsAwareUtc
            uptime = datetime.now(timezone.utc) - AsAwareUtc(self.StartTime)
            total_seconds = int(uptime.total_seconds())
            
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        except Exception:
            return "Unknown"
    
    def GetMemoryUsage(self) -> float:
        """Get current memory usage percentage."""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            system_memory = psutil.virtual_memory()
            
            # Calculate percentage of system memory used by this process
            memory_percent = (memory_info.rss / system_memory.total) * 100
            return round(memory_percent, 2)
        except Exception as e:
            logger.warning(f"Could not get memory usage: {str(e)}")
            return 0.0
    
    def GetCPUUsage(self) -> float:
        """Get current CPU usage percentage."""
        try:
            return round(psutil.cpu_percent(interval=1), 2)
        except Exception as e:
            logger.warning(f"Could not get CPU usage: {str(e)}")
            return 0.0
    
    def CheckDatabaseConnection(self) -> bool:
        """Check if database connection is healthy."""
        try:
            if self.DatabaseManager:
                # Try a simple query
                result = self.DatabaseManager.DatabaseService.ExecuteQuery("SELECT 1")
                return result is not None and len(result) > 0
            return False
        except Exception as e:
            logger.warning(f"Database connection check failed: {str(e)}")
            return False
    
    def CheckDiskSpace(self) -> float:
        """Check available disk space percentage."""
        try:
            disk_usage = psutil.disk_usage('/')
            if disk_usage.total > 0:
                free_percent = (disk_usage.free / disk_usage.total) * 100
                return round(free_percent, 2)
            return 0.0
        except Exception as e:
            logger.warning(f"Could not check disk space: {str(e)}")
            return 0.0
    
    def IsHealthy(self) -> bool:
        """Check if service is considered healthy."""
        return self.HealthStatus == "Healthy" and self.ErrorCount < self.MaxErrors
    
    def GetStatusSummary(self) -> str:
        """Get a brief status summary."""
        if self.IsHealthy():
            return f"Healthy (Uptime: {self.GetUptime()})"
        else:
            return f"Unhealthy (Status: {self.HealthStatus}, Errors: {self.ErrorCount})"
    
    def LogHealthStatus(self):
        """Log current health status."""
        try:
            health_data = self.CheckHealth()
            
            if health_data["Status"] == "Healthy":
                logger.info(f"Health check passed: {self.GetStatusSummary()}")
            elif health_data["Status"] == "Warning":
                logger.warning(f"Health check warning: {self.GetStatusSummary()}")
            else:
                logger.error(f"Health check failed: {self.GetStatusSummary()}")
                
        except Exception as e:
            logger.error(f"Error logging health status: {str(e)}")

# Global health monitor instance
health_monitor = None

def GetHealthMonitor() -> Optional[HealthMonitor]:
    """Get the global health monitor instance."""
    return health_monitor

def InitializeHealthMonitor(database_manager=None):
    """Initialize the global health monitor."""
    global health_monitor
    health_monitor = HealthMonitor(database_manager)
    return health_monitor
