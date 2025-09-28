"""
QualityCompareService Health Monitoring
Handles health checks, status reporting, and performance monitoring.
"""

import psutil
import time
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta


class HealthMonitor:
    """Health monitoring and status reporting for QualityCompareService."""
    
    def __init__(self, DatabaseManager, Config):
        """Initialize health monitor."""
        self.DatabaseManager = DatabaseManager
        self.Config = Config
        self.StartTime = datetime.now()
        self.LastHealthCheck = datetime.now()
        self.HealthStatus = "Healthy"
        self.ErrorCount = 0
        self.MaxErrors = self.Config.MaxErrors
        self.IsMonitoring = False
        self.MonitoringThread = None
        
        # Performance metrics
        self.MemoryUsageHistory = []
        self.CPUUsageHistory = []
        self.DiskUsageHistory = []
        self.MaxHistorySize = 100
        
        # Health thresholds
        self.MemoryThresholdMB = self.Config.MemoryLimitMB
        self.CPUThresholdPercent = self.Config.CPULimitPercent
        self.DiskThresholdPercent = 90.0  # 90% disk usage threshold
        
        # Health check intervals
        self.HealthCheckInterval = self.Config.HealthCheckInterval
        self.PerformanceCheckInterval = 60  # Check performance every minute
    
    def StartMonitoring(self):
        """Start health monitoring."""
        try:
            self.IsMonitoring = True
            self.MonitoringThread = threading.Thread(target=self.MonitoringLoop, daemon=True)
            self.MonitoringThread.start()
            
        except Exception as e:
            print(f"Exception starting health monitoring: {str(e)}")
    
    def StopMonitoring(self):
        """Stop health monitoring."""
        try:
            self.IsMonitoring = False
            if self.MonitoringThread:
                self.MonitoringThread.join(timeout=5)
                
        except Exception as e:
            print(f"Exception stopping health monitoring: {str(e)}")
    
    def MonitoringLoop(self):
        """Main health monitoring loop."""
        try:
            while self.IsMonitoring:
                # Perform health check
                self.PerformHealthCheck()
                
                # Update performance metrics
                self.UpdatePerformanceMetrics()
                
                # Update service status in database
                self.UpdateServiceStatus()
                
                # Wait before next check
                time.sleep(self.HealthCheckInterval)
                
        except Exception as e:
            print(f"Exception in health monitoring loop: {str(e)}")
    
    def PerformHealthCheck(self):
        """Perform comprehensive health check."""
        try:
            self.LastHealthCheck = datetime.now()
            
            # Check database connection
            databaseHealthy = self.CheckDatabaseConnection()
            
            # Check memory usage
            memoryHealthy = self.CheckMemoryUsage()
            
            # Check CPU usage
            cpuHealthy = self.CheckCPUUsage()
            
            # Check disk space
            diskHealthy = self.CheckDiskSpace()
            
            # Check process health
            processHealthy = self.CheckProcessHealth()
            
            # Determine overall health status
            if databaseHealthy and memoryHealthy and cpuHealthy and diskHealthy and processHealthy:
                self.HealthStatus = "Healthy"
                self.ErrorCount = 0  # Reset error count on healthy status
            else:
                self.HealthStatus = "Unhealthy"
                self.ErrorCount += 1
                
                # Check if we've exceeded max errors
                if self.ErrorCount >= self.MaxErrors:
                    self.HealthStatus = "Critical"
            
        except Exception as e:
            self.HealthStatus = "Error"
            self.ErrorCount += 1
            print(f"Exception in health check: {str(e)}")
    
    def CheckDatabaseConnection(self) -> bool:
        """Check database connection health."""
        try:
            # Test database connection
            testResult = self.DatabaseManager.DatabaseService.ExecuteQuery("SELECT 1")
            return testResult is not None
            
        except Exception as e:
            print(f"Database connection check failed: {str(e)}")
            return False
    
    def CheckMemoryUsage(self) -> bool:
        """Check memory usage health."""
        try:
            process = psutil.Process()
            memoryUsageMB = process.memory_info().rss / 1024 / 1024
            
            # Check if memory usage exceeds threshold
            if memoryUsageMB > self.MemoryThresholdMB:
                print(f"Memory usage {memoryUsageMB:.2f}MB exceeds threshold {self.MemoryThresholdMB}MB")
                return False
            
            return True
            
        except Exception as e:
            print(f"Memory usage check failed: {str(e)}")
            return False
    
    def CheckCPUUsage(self) -> bool:
        """Check CPU usage health."""
        try:
            cpuUsagePercent = psutil.Process().cpu_percent(interval=1)
            
            # Check if CPU usage exceeds threshold
            if cpuUsagePercent > self.CPUThresholdPercent:
                print(f"CPU usage {cpuUsagePercent:.2f}% exceeds threshold {self.CPUThresholdPercent}%")
                return False
            
            return True
            
        except Exception as e:
            print(f"CPU usage check failed: {str(e)}")
            return False
    
    def CheckDiskSpace(self) -> bool:
        """Check disk space health."""
        try:
            diskUsage = psutil.disk_usage('/')
            diskUsagePercent = (diskUsage.used / diskUsage.total) * 100
            
            # Check if disk usage exceeds threshold
            if diskUsagePercent > self.DiskThresholdPercent:
                print(f"Disk usage {diskUsagePercent:.2f}% exceeds threshold {self.DiskThresholdPercent}%")
                return False
            
            return True
            
        except Exception as e:
            print(f"Disk space check failed: {str(e)}")
            return False
    
    def CheckProcessHealth(self) -> bool:
        """Check process health."""
        try:
            process = psutil.Process()
            
            # Check if process is still running
            if not process.is_running():
                print("Process is not running")
                return False
            
            # Check process status
            if process.status() == psutil.STATUS_ZOMBIE:
                print("Process is in zombie state")
                return False
            
            return True
            
        except Exception as e:
            print(f"Process health check failed: {str(e)}")
            return False
    
    def UpdatePerformanceMetrics(self):
        """Update performance metrics."""
        try:
            process = psutil.Process()
            
            # Get current metrics
            memoryUsageMB = process.memory_info().rss / 1024 / 1024
            cpuUsagePercent = process.cpu_percent()
            diskUsage = psutil.disk_usage('/')
            diskUsagePercent = (diskUsage.used / diskUsage.total) * 100
            
            # Add to history
            self.MemoryUsageHistory.append({
                'Timestamp': datetime.now(),
                'MemoryUsageMB': memoryUsageMB
            })
            
            self.CPUUsageHistory.append({
                'Timestamp': datetime.now(),
                'CPUUsagePercent': cpuUsagePercent
            })
            
            self.DiskUsageHistory.append({
                'Timestamp': datetime.now(),
                'DiskUsagePercent': diskUsagePercent
            })
            
            # Trim history to max size
            if len(self.MemoryUsageHistory) > self.MaxHistorySize:
                self.MemoryUsageHistory = self.MemoryUsageHistory[-self.MaxHistorySize:]
            
            if len(self.CPUUsageHistory) > self.MaxHistorySize:
                self.CPUUsageHistory = self.CPUUsageHistory[-self.MaxHistorySize:]
            
            if len(self.DiskUsageHistory) > self.MaxHistorySize:
                self.DiskUsageHistory = self.DiskUsageHistory[-self.MaxHistorySize:]
                
        except Exception as e:
            print(f"Exception updating performance metrics: {str(e)}")
    
    def UpdateServiceStatus(self):
        """Update service status in database."""
        try:
            uptime = (datetime.now() - self.StartTime).total_seconds()
            
            # Get current performance metrics
            currentMemory = self.MemoryUsageHistory[-1]['MemoryUsageMB'] if self.MemoryUsageHistory else 0
            currentCPU = self.CPUUsageHistory[-1]['CPUUsagePercent'] if self.CPUUsageHistory else 0
            currentDisk = self.DiskUsageHistory[-1]['DiskUsagePercent'] if self.DiskUsageHistory else 0
            
            serviceStatus = {
                'ServiceName': 'QualityCompareService',
                'Status': 'Running',
                'HealthStatus': self.HealthStatus,
                'LastHealthCheck': self.LastHealthCheck,
                'UptimeSeconds': int(uptime),
                'MemoryUsage': currentMemory,
                'CPUUsage': currentCPU,
                'DatabaseConnection': self.CheckDatabaseConnection(),
                'DiskSpace': 100 - currentDisk,  # Available disk space percentage
                'ErrorCount': self.ErrorCount,
                'MaxErrors': self.MaxErrors,
                'ActiveJobsCount': self.GetActiveJobsCount(),
                'IsProcessing': self.IsMonitoring
            }
            
            self.DatabaseManager.UpdateServiceStatus('QualityCompareService', serviceStatus)
            
        except Exception as e:
            print(f"Exception updating service status: {str(e)}")
    
    def GetActiveJobsCount(self) -> int:
        """Get count of active quality testing jobs."""
        try:
            # Query active jobs from QualityTestingQueue
            query = """
                SELECT COUNT(*) as ActiveJobs
                FROM QualityTestingQueue 
                WHERE Status IN ('Pending', 'Processing')
            """
            
            result = self.DatabaseManager.DatabaseService.ExecuteQuery(query)
            if result and len(result) > 0:
                return result[0]['ActiveJobs']
            
            return 0
            
        except Exception as e:
            print(f"Exception getting active jobs count: {str(e)}")
            return 0
    
    def GetHealthReport(self) -> Dict[str, Any]:
        """Get comprehensive health report."""
        try:
            uptime = (datetime.now() - self.StartTime).total_seconds()
            
            # Calculate average metrics
            avgMemory = sum(m['MemoryUsageMB'] for m in self.MemoryUsageHistory) / len(self.MemoryUsageHistory) if self.MemoryUsageHistory else 0
            avgCPU = sum(c['CPUUsagePercent'] for c in self.CPUUsageHistory) / len(self.CPUUsageHistory) if self.CPUUsageHistory else 0
            avgDisk = sum(d['DiskUsagePercent'] for d in self.DiskUsageHistory) / len(self.DiskUsageHistory) if self.DiskUsageHistory else 0
            
            return {
                'ServiceName': 'QualityCompareService',
                'HealthStatus': self.HealthStatus,
                'UptimeSeconds': int(uptime),
                'LastHealthCheck': self.LastHealthCheck,
                'ErrorCount': self.ErrorCount,
                'MaxErrors': self.MaxErrors,
                'CurrentMemoryUsageMB': self.MemoryUsageHistory[-1]['MemoryUsageMB'] if self.MemoryUsageHistory else 0,
                'AverageMemoryUsageMB': avgMemory,
                'CurrentCPUUsagePercent': self.CPUUsageHistory[-1]['CPUUsagePercent'] if self.CPUUsageHistory else 0,
                'AverageCPUUsagePercent': avgCPU,
                'CurrentDiskUsagePercent': self.DiskUsageHistory[-1]['DiskUsagePercent'] if self.DiskUsageHistory else 0,
                'AverageDiskUsagePercent': avgDisk,
                'DatabaseConnection': self.CheckDatabaseConnection(),
                'ActiveJobsCount': self.GetActiveJobsCount(),
                'IsMonitoring': self.IsMonitoring,
                'MemoryThresholdMB': self.MemoryThresholdMB,
                'CPUThresholdPercent': self.CPUThresholdPercent,
                'DiskThresholdPercent': self.DiskThresholdPercent
            }
            
        except Exception as e:
            print(f"Exception getting health report: {str(e)}")
            return {
                'ServiceName': 'QualityCompareService',
                'HealthStatus': 'Error',
                'ErrorMessage': str(e)
            }
    
    def GetPerformanceMetrics(self) -> Dict[str, Any]:
        """Get performance metrics history."""
        try:
            return {
                'MemoryUsageHistory': self.MemoryUsageHistory,
                'CPUUsageHistory': self.CPUUsageHistory,
                'DiskUsageHistory': self.DiskUsageHistory,
                'HistorySize': len(self.MemoryUsageHistory),
                'MaxHistorySize': self.MaxHistorySize
            }
            
        except Exception as e:
            print(f"Exception getting performance metrics: {str(e)}")
            return {
                'ErrorMessage': str(e)
            }
    
    def ResetErrorCount(self):
        """Reset error count."""
        self.ErrorCount = 0
        self.HealthStatus = "Healthy"
    
    def IsHealthy(self) -> bool:
        """Check if service is healthy."""
        return self.HealthStatus == "Healthy"
    
    def IsCritical(self) -> bool:
        """Check if service is in critical state."""
        return self.HealthStatus == "Critical"
