"""
System Monitoring Service
Handles system resource monitoring including CPU temperature, CPU usage, and memory

NOTE: CPU temperature monitoring requires LibreHardwareMonitor to be running.
Download from: https://github.com/LibreHardwareMonitor/LibreHardwareMonitor
"""

import psutil
import platform
import subprocess
import re
from typing import Dict, Any, Optional
from Services.LoggingService import LoggingService

class SystemMonitoringService:
    """Service for monitoring system resources."""

    def __init__(self):
        self.Platform = platform.system()
        self.CpuTemperatureAvailable = False
        self._TestTemperatureAvailability()

    def _TestTemperatureAvailability(self):
        """Test if CPU temperature monitoring is available."""
        try:
            if self.Platform == "Windows":
                # Check if LibreHardwareMonitor is available
                temp_data = self._GetLibreHardwareMonitorTemperature()
                self.CpuTemperatureAvailable = temp_data is not None
            else:
                # Try psutil sensors for Linux/Mac
                temps = psutil.sensors_temperatures()
                self.CpuTemperatureAvailable = len(temps) > 0
        except Exception as e:
            LoggingService.LogInfo(f"CPU temperature monitoring not available: {e}", "SystemMonitoringService", "_TestTemperatureAvailability")
            self.CpuTemperatureAvailable = False

    def GetSystemResources(self) -> Dict[str, Any]:
        """Get comprehensive system resource information."""
        try:
            LoggingService.LogFunctionEntry("GetSystemResources", "SystemMonitoringService")

            resources = {
                "CpuUsage": self.GetCpuUsage(),
                "MemoryUsage": self.GetMemoryUsage(),
                "CpuTemperature": self.GetCpuTemperature(),
                "DiskUsage": self.GetDiskUsage(),
                "SystemInfo": self.GetSystemInfo()
            }

            LoggingService.LogInfo("Successfully retrieved system resources", "SystemMonitoringService", "GetSystemResources")
            return resources

        except Exception as e:
            error_msg = f"Exception getting system resources: {str(e)}"
            LoggingService.LogException(error_msg, e, "SystemMonitoringService", "GetSystemResources")
            return {
                "CpuUsage": 0.0,
                "MemoryUsage": {"Used": 0, "Total": 0, "Percent": 0.0},
                "CpuTemperature": None,
                "DiskUsage": {"Free": 0, "Total": 0, "Percent": 0.0},
                "SystemInfo": {"Cores": 0, "Platform": self.Platform}
            }

    def GetCpuUsage(self) -> float:
        """Get current CPU usage percentage."""
        try:
            return psutil.cpu_percent(interval=1)
        except Exception as e:
            LoggingService.LogException(f"Error getting CPU usage: {e}", e, "SystemMonitoringService", "GetCpuUsage")
            return 0.0

    def GetMemoryUsage(self) -> Dict[str, Any]:
        """Get memory usage information."""
        try:
            memory = psutil.virtual_memory()
            return {
                "Used": round(memory.used / (1024**3), 2),  # GB
                "Total": round(memory.total / (1024**3), 2),  # GB
                "Percent": memory.percent
            }
        except Exception as e:
            LoggingService.LogException(f"Error getting memory usage: {e}", e, "SystemMonitoringService", "GetMemoryUsage")
            return {"Used": 0, "Total": 0, "Percent": 0.0}

    def GetCpuTemperature(self) -> Optional[Dict[str, Any]]:
        """
        Get CPU temperature in both Celsius and Fahrenheit with detailed core information.

        Requires LibreHardwareMonitor to be running on Windows.
        Download from: https://github.com/LibreHardwareMonitor/LibreHardwareMonitor
        """
        try:
            if self.Platform == "Windows":
                temp_data = self._GetLibreHardwareMonitorTemperature()
            else:
                temp_celsius = self._GetCpuTemperatureUnix()
                temp_data = {"Package": temp_celsius, "Cores": [], "Max": temp_celsius, "Average": temp_celsius} if temp_celsius else None

            if temp_data and temp_data.get("Package") is not None:
                package_celsius = temp_data["Package"]
                package_fahrenheit = (package_celsius * 9/5) + 32

                # Ensure all cores are represented
                cores = temp_data.get("Cores", [])
                detected_cores = {core["Core"]: core["Temperature"] for core in cores if "Core" in core}

                # Fill in missing cores with None if we have some core data
                if detected_cores:
                    try:
                        total_cores = psutil.cpu_count(logical=False) or psutil.cpu_count()
                    except:
                        total_cores = 24  # Default for i9-14900KF

                    # Ensure all core slots exist
                    filled_cores = []
                    for core_num in range(total_cores):
                        filled_cores.append({
                            "Core": core_num,
                            "Temperature": detected_cores.get(core_num, None)
                        })
                    cores = filled_cores

                result = {
                    "Celsius": package_celsius,
                    "Fahrenheit": round(package_fahrenheit, 1),
                    "Package": package_celsius,
                    "Max": temp_data.get("Max", package_celsius),
                    "Average": temp_data.get("Average", package_celsius),
                    "Cores": cores
                }
                return result
            return None
        except Exception as e:
            LoggingService.LogException(f"Error getting CPU temperature: {e}", e, "SystemMonitoringService", "GetCpuTemperature")
            return None

    def _GetLibreHardwareMonitorTemperature(self) -> Optional[Dict[str, Any]]:
        """
        Get CPU temperature from LibreHardwareMonitor WMI namespace.

        This is the ONLY method that works reliably for per-core temperatures on Windows.
        Requires LibreHardwareMonitor software to be running.
        """
        try:
            # Get all temperature sensors from LibreHardwareMonitor
            ps_command = "Get-WmiObject -Namespace 'root\\LibreHardwareMonitor' -Class Sensor | Where-Object {$_.SensorType -eq 'Temperature'} | Select-Object Name, Value | Sort-Object Name"
            result = subprocess.run([
                'powershell', '-Command', ps_command
            ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)

            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                sensors = {}
                core_temps = {}  # Dictionary: core_number -> temperature

                for line in lines:
                    line = line.strip()
                    if not line or 'Name' in line and 'Value' in line:
                        continue  # Skip header or empty lines

                    # PowerShell output format: "Name Value" or "Name    Value"
                    # Try to split on whitespace, but the name might contain spaces
                    # The value should be the last token (a number)
                    try:
                        # Split line and find where the numeric value starts
                        parts = line.split()
                        if len(parts) < 2:
                            continue

                        # The last part should be the temperature value
                        temp_str = parts[-1]

                        # Try to parse the temperature
                        try:
                            temp_celsius = float(temp_str)
                        except ValueError:
                            # If last part isn't a number, skip this line
                            continue

                        # Validate temperature is reasonable (0-150°C)
                        if not (0 < temp_celsius < 150):
                            continue

                        # The name is everything except the last part
                        name = ' '.join(parts[:-1])

                        # Store the sensor
                        sensors[name] = round(temp_celsius, 1)

                        # Extract core number if this is a core temperature
                        # LibreHardwareMonitor uses "CPU Core #1", "CPU Core #2", etc.
                        core_match = re.match(r'CPU Core #(\d+)', name, re.IGNORECASE)
                        if core_match:
                            # LibreHardwareMonitor uses 1-indexed core numbers (1-24)
                            # Convert to 0-indexed (0-23) for consistency
                            core_number = int(core_match.group(1))
                            core_number_0_based = core_number - 1

                            # Only add if it's a reasonable core number (0-63)
                            if 0 <= core_number_0_based < 64:
                                core_temps[core_number_0_based] = round(temp_celsius, 1)
                                LoggingService.LogDebug(f"Found core {core_number_0_based} temperature: {temp_celsius}°C", "SystemMonitoringService", "_GetLibreHardwareMonitorTemperature")

                    except (ValueError, AttributeError) as e:
                        LoggingService.LogDebug(f"Error parsing sensor data: {line}, error: {e}", "SystemMonitoringService", "_GetLibreHardwareMonitorTemperature")
                        continue

                if sensors:
                    # Find package temperature (prefer CPU Package, fallback to highest temp)
                    package_temp = sensors.get('CPU Package')
                    if package_temp is None:
                        # Try to find package in sensors dict with variations
                        for sensor_name, sensor_temp in sensors.items():
                            if 'Package' in sensor_name and 'CPU' in sensor_name:
                                package_temp = sensor_temp
                                break
                        if package_temp is None:
                            package_temp = max(sensors.values())

                    # Create core details list with actual core numbers
                    cores = []
                    if core_temps:
                        LoggingService.LogInfo(f"Found {len(core_temps)} core temperatures", "SystemMonitoringService", "_GetLibreHardwareMonitorTemperature")
                        # Sort by core number to ensure consistent ordering
                        for core_number in sorted(core_temps.keys()):
                            cores.append({
                                "Core": core_number,  # Use 0-based core number (0-23)
                                "Temperature": core_temps[core_number]
                            })

                        # Find max and average core temperatures
                        max_temp = max(core_temps.values())
                        avg_temp = sum(core_temps.values()) / len(core_temps)
                    else:
                        LoggingService.LogInfo("No core temperatures found, using package temperature only", "SystemMonitoringService", "_GetLibreHardwareMonitorTemperature")
                        max_temp = package_temp
                        avg_temp = package_temp

                    return {
                        "Package": package_temp,
                        "Max": max_temp,
                        "Average": round(avg_temp, 1),
                        "Cores": cores,
                        "Sensors": sensors
                    }
            return None
        except Exception as e:
            LoggingService.LogInfo(f"LibreHardwareMonitor not available: {e}", "SystemMonitoringService", "_GetLibreHardwareMonitorTemperature")
            return None

    def _GetCpuTemperatureUnix(self) -> Optional[float]:
        """Get CPU temperature on Unix-like systems (Linux/Mac)."""
        try:
            # Check if sensors_temperatures is available
            if not hasattr(psutil, 'sensors_temperatures'):
                LoggingService.LogInfo("psutil.sensors_temperatures() not available on this platform", "SystemMonitoringService", "_GetCpuTemperatureUnix")
                return None

            temps = psutil.sensors_temperatures()
            if 'coretemp' in temps:
                for entry in temps['coretemp']:
                    if 'Package' in entry.label or 'Core 0' in entry.label:
                        return entry.current
            return None
        except Exception as e:
            LoggingService.LogInfo(f"psutil temperature query failed: {e}", "SystemMonitoringService", "_GetCpuTemperatureUnix")
            return None

    def GetDiskUsage(self) -> Dict[str, Any]:
        """Get disk usage information."""
        try:
            disk = psutil.disk_usage('/')
            return {
                "Free": round(disk.free / (1024**3), 2),  # GB
                "Total": round(disk.total / (1024**3), 2),  # GB
                "Percent": round((disk.used / disk.total) * 100, 1)
            }
        except Exception as e:
            LoggingService.LogException(f"Error getting disk usage: {e}", e, "SystemMonitoringService", "GetDiskUsage")
            return {"Free": 0, "Total": 0, "Percent": 0.0}

    def GetSystemInfo(self) -> Dict[str, Any]:
        """Get system information."""
        try:
            return {
                "Cores": psutil.cpu_count(logical=False),
                "Threads": psutil.cpu_count(logical=True),
                "Platform": self.Platform,
                "Architecture": platform.machine()
            }
        except Exception as e:
            LoggingService.LogException(f"Error getting system info: {e}", e, "SystemMonitoringService", "GetSystemInfo")
            return {"Cores": 0, "Threads": 0, "Platform": self.Platform, "Architecture": "unknown"}


# Create a singleton instance for use throughout the application
SystemMonitoringServiceInstance = SystemMonitoringService()
