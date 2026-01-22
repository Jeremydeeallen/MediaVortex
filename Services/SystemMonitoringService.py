"""
System Monitoring Service
Handles system resource monitoring including CPU temperature, CPU usage, and memory
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
                # Try WMI approach for Windows
                self._GetCpuTemperatureWindows()
                self.CpuTemperatureAvailable = True
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
        """Get CPU temperature in both Celsius and Fahrenheit with detailed core information."""
        try:
            if self.Platform == "Windows":
                temp_data = self._GetCpuTemperatureWindowsDetailed()
            else:
                temp_celsius = self._GetCpuTemperatureUnix()
                temp_data = {"Package": temp_celsius, "Cores": [], "Max": temp_celsius, "Average": temp_celsius} if temp_celsius else None
            
            if temp_data and temp_data.get("Package") is not None:
                package_celsius = temp_data["Package"]
                package_fahrenheit = (package_celsius * 9/5) + 32
                
                # Ensure all cores are represented
                cores = temp_data.get("Cores", [])
                detected_cores = {core["Core"]: core["Temperature"] for core in cores if "Core" in core}
                
                # Get total core count from system (physical cores preferred)
                try:
                    import psutil
                    total_cores = psutil.cpu_count(logical=False) or psutil.cpu_count()  # Prefer physical, fallback to logical
                except Exception:
                    # Fallback: use detected cores or default to 24
                    total_cores = max(detected_cores.keys()) + 1 if detected_cores else 24
                
                # Fill in missing cores with N/A
                complete_cores = []
                for core_num in range(total_cores):
                    if core_num in detected_cores:
                        complete_cores.append({
                            "Core": core_num,
                            "Temperature": detected_cores[core_num]
                        })
                    else:
                        complete_cores.append({
                            "Core": core_num,
                            "Temperature": None  # Will display as "N/A"
                        })
                
                result = {
                    "Celsius": round(package_celsius, 1),
                    "Fahrenheit": round(package_fahrenheit, 1),
                    "Package": round(package_celsius, 1),
                    "Max": round(temp_data.get("Max", package_celsius), 1),
                    "Average": round(temp_data.get("Average", package_celsius), 1),
                    "Cores": complete_cores
                }
                return result
            return None
        except Exception as e:
            LoggingService.LogException(f"Error getting CPU temperature: {e}", e, "SystemMonitoringService", "GetCpuTemperature")
            return None
    
    def _GetCpuTemperatureWindowsDetailed(self) -> Optional[Dict[str, Any]]:
        """Get detailed CPU temperature information on Windows using multiple methods."""
        # NOTE: Windows does not natively provide per-core temperatures.
        # All methods below are attempts to get this data, but they require either:
        # 1. External DLLs (LibreHardwareMonitorLib.dll)
        # 2. External software running (LibreHardwareMonitor, OpenHardwareMonitor)
        # 3. Or only provide package temperature (WMI thermal zones)
        
        # Method 1: Try HardwareMonitorService (direct DLL access - requires LibreHardwareMonitorLib.dll)
        try:
            from Services.HardwareMonitorService import HardwareMonitorServiceInstance
            if HardwareMonitorServiceInstance.IsInitialized:
                temp_data = HardwareMonitorServiceInstance.GetCpuCoreTemperatures()
                if temp_data is not None and temp_data.get("Cores"):
                    LoggingService.LogInfo(f"Got {len(temp_data['Cores'])} core temperatures from HardwareMonitorService", "SystemMonitoringService", "_GetCpuTemperatureWindowsDetailed")
                    return temp_data
        except ImportError:
            pass  # HardwareMonitorService not available (pythonnet or DLL not found)
        except Exception as e:
            LoggingService.LogInfo(f"HardwareMonitorService not available: {e}", "SystemMonitoringService", "_GetCpuTemperatureWindowsDetailed")
        
        # Method 2: Try LibreHardwareMonitor WMI (requires LibreHardwareMonitor software running)
        temp_data = self._TryLibreHardwareMonitorDetailed()
        if temp_data is not None and temp_data.get("Cores"):
            LoggingService.LogInfo(f"Temperature source: LibreHardwareMonitor WMI - Found {len(temp_data['Cores'])} core temperatures", "SystemMonitoringService", "_GetCpuTemperatureWindowsDetailed")
            return temp_data
        
        # Method 3: Try OpenHardwareMonitor WMI (requires OpenHardwareMonitor software running)
        temp_data = self._TryOpenHardwareMonitorDetailed()
        if temp_data is not None:
            return temp_data
        
        # Method 4: Try HWiNFO64 WMI (requires HWiNFO64 software running)
        temp_data = self._TryHWiNFO64Detailed()
        if temp_data is not None:
            return temp_data
        
        # Method 5: Fallback to Windows built-in WMI (package temp only - NO per-core temps)
        # This is the ONLY method that requires NO external dependencies
        temp = self._GetCpuTemperatureWindows()
        if temp is not None:
            # Windows only provides package temp, not per-core
            # Create cores list with N/A
            try:
                import psutil
                total_cores = psutil.cpu_count(logical=False) or psutil.cpu_count()
            except:
                total_cores = 24  # Default for i9-14900KF
            
            cores = []
            for core_num in range(total_cores):
                cores.append({
                    "Core": core_num,
                    "Temperature": None  # Not available from Windows built-in APIs
                })
            
            return {"Package": temp, "Cores": cores, "Max": temp, "Average": temp}
        
        return None
    
    def _GetCpuTemperatureWindows(self) -> Optional[float]:
        """Get CPU temperature on Windows using multiple methods."""
        # Method 1: Try WMI MSAcpi_ThermalZoneTemperature
        temp = self._TryWmiThermalZone()
        if temp is not None:
            return temp
        
        # Method 2: Try WMI Win32_TemperatureProbe
        temp = self._TryWmiTemperatureProbe()
        if temp is not None:
            return temp
        
        # Method 3: Try OpenHardwareMonitor WMI
        temp = self._TryOpenHardwareMonitor()
        if temp is not None:
            return temp
        
        # Method 4: Try CoreTemp WMI
        temp = self._TryCoreTempWmi()
        if temp is not None:
            return temp
        
        # Method 5: Try HWiNFO64 WMI
        temp = self._TryHWiNFO64Wmi()
        if temp is not None:
            return temp
        
        # Method 6: Try LibreHardwareMonitor WMI
        temp = self._TryLibreHardwareMonitorWmi()
        if temp is not None:
            return temp
        
        return None
    
    def _TryWmiThermalZone(self) -> Optional[float]:
        """Try WMI MSAcpi_ThermalZoneTemperature using PowerShell."""
        try:
            # Use PowerShell to access WMI with better elevation handling
            ps_command = "Get-WmiObject -Namespace 'root\\wmi' -Class MSAcpi_ThermalZoneTemperature | Select-Object -ExpandProperty CurrentTemperature"
            result = subprocess.run([
                'powershell', '-Command', ps_command
            ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if result.returncode == 0 and result.stdout.strip():
                # PowerShell returns each temperature on a new line
                lines = result.stdout.strip().split('\n')
                temperatures = []
                for line in lines:
                    line = line.strip()
                    if line and re.match(r'^\d+$', line):
                        # WMI returns temperature in tenths of Kelvin
                        temp_kelvin = int(line) / 10.0
                        temp_celsius = temp_kelvin - 273.15
                        if 0 < temp_celsius < 150:  # Reasonable temperature range
                            temperatures.append(round(temp_celsius, 1))
                
                # Return the highest temperature (likely CPU core temp)
                if temperatures:
                    return max(temperatures)
            return None
        except Exception as e:
            LoggingService.LogInfo(f"PowerShell WMI ThermalZone failed: {e}", "SystemMonitoringService", "_TryWmiThermalZone")
            return None
    
    def _TryWmiTemperatureProbe(self) -> Optional[float]:
        """Try WMI Win32_TemperatureProbe using PowerShell."""
        try:
            ps_command = "Get-WmiObject -Class Win32_TemperatureProbe | Select-Object -ExpandProperty CurrentReading"
            result = subprocess.run([
                'powershell', '-Command', ps_command
            ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line and re.match(r'^\d+$', line):
                        temp_celsius = int(line) / 10.0
                        if 0 < temp_celsius < 150:  # Reasonable temperature range
                            return round(temp_celsius, 1)
            return None
        except Exception as e:
            LoggingService.LogInfo(f"PowerShell WMI TemperatureProbe failed: {e}", "SystemMonitoringService", "_TryWmiTemperatureProbe")
            return None
    
    def _TryOpenHardwareMonitor(self) -> Optional[float]:
        """Try OpenHardwareMonitor WMI namespace using PowerShell."""
        try:
            # Try to get CPU-specific temperature sensors first
            ps_command = "Get-WmiObject -Namespace 'root\\OpenHardwareMonitor' -Class Sensor | Where-Object {$_.SensorType -eq 'Temperature' -and ($_.Name -like '*CPU*' -or $_.Name -like '*Core*' -or $_.Name -like '*Package*')} | Select-Object Name, Value"
            result = subprocess.run([
                'powershell', '-Command', ps_command
            ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                cpu_temps = []
                for line in lines:
                    if 'Name' in line and 'Value' in line:
                        continue  # Skip header
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        try:
                            temp_celsius = float(parts[-1])  # Value is usually last
                            if 20 < temp_celsius < 150:  # More realistic CPU temp range
                                cpu_temps.append(round(temp_celsius, 1))
                        except ValueError:
                            continue
                
                if cpu_temps:
                    return max(cpu_temps)  # Return highest CPU temperature
            
            # Fallback to any temperature sensor if no CPU-specific ones found
            ps_command = "Get-WmiObject -Namespace 'root\\OpenHardwareMonitor' -Class Sensor | Where-Object {$_.SensorType -eq 'Temperature'} | Select-Object -ExpandProperty Value"
            result = subprocess.run([
                'powershell', '-Command', ps_command
            ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                temperatures = []
                for line in lines:
                    line = line.strip()
                    if line and re.match(r'^\d+\.?\d*$', line):
                        temp_celsius = float(line)
                        if 20 < temp_celsius < 150:  # More realistic temperature range
                            temperatures.append(round(temp_celsius, 1))
                
                if temperatures:
                    return max(temperatures)  # Return highest temperature
            return None
        except Exception as e:
            LoggingService.LogInfo(f"PowerShell OpenHardwareMonitor WMI failed: {e}", "SystemMonitoringService", "_TryOpenHardwareMonitor")
            return None
    
    def _TryCoreTempWmi(self) -> Optional[float]:
        """Try CoreTemp WMI namespace using PowerShell."""
        try:
            ps_command = "Get-WmiObject -Namespace 'root\\OpenHardwareMonitor' -Class Sensor | Where-Object {$_.Name -eq 'CPU Package'} | Select-Object -ExpandProperty Value"
            result = subprocess.run([
                'powershell', '-Command', ps_command
            ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line and re.match(r'^\d+\.?\d*$', line):
                        temp_celsius = float(line)
                        if 20 < temp_celsius < 150:  # More realistic CPU temp range
                            return round(temp_celsius, 1)
            return None
        except Exception as e:
            LoggingService.LogInfo(f"PowerShell CoreTemp WMI failed: {e}", "SystemMonitoringService", "_TryCoreTempWmi")
            return None
    
    def _TryHWiNFO64Wmi(self) -> Optional[float]:
        """Try HWiNFO64 WMI namespace using PowerShell."""
        try:
            # Try HWiNFO64 WMI namespace for CPU temperature
            ps_command = "Get-WmiObject -Namespace 'root\\HWiNFO64' -Class HWiNFO64SensorInstance | Where-Object {$_.SensorName -like '*CPU*' -and $_.SensorType -eq 'Temperature'} | Select-Object SensorName, Value"
            result = subprocess.run([
                'powershell', '-Command', ps_command
            ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                cpu_temps = []
                for line in lines:
                    if 'SensorName' in line and 'Value' in line:
                        continue  # Skip header
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        try:
                            temp_celsius = float(parts[-1])  # Value is usually last
                            if 20 < temp_celsius < 150:  # More realistic CPU temp range
                                cpu_temps.append(round(temp_celsius, 1))
                        except ValueError:
                            continue
                
                if cpu_temps:
                    return max(cpu_temps)  # Return highest CPU temperature
            return None
        except Exception as e:
            LoggingService.LogInfo(f"PowerShell HWiNFO64 WMI failed: {e}", "SystemMonitoringService", "_TryHWiNFO64Wmi")
            return None
    
    def _TryLibreHardwareMonitorWmi(self) -> Optional[float]:
        """Try LibreHardwareMonitor WMI namespace using PowerShell."""
        try:
            # Try LibreHardwareMonitor WMI namespace for CPU temperature
            ps_command = "Get-WmiObject -Namespace 'root\\LibreHardwareMonitor' -Class Sensor | Where-Object {$_.SensorType -eq 'Temperature' -and ($_.Name -like '*CPU*' -or $_.Name -like '*Core*' -or $_.Name -like '*Package*')} | Select-Object Name, Value"
            result = subprocess.run([
                'powershell', '-Command', ps_command
            ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                cpu_temps = []
                for line in lines:
                    if 'Name' in line and 'Value' in line:
                        continue  # Skip header
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        try:
                            temp_celsius = float(parts[-1])  # Value is usually last
                            if 20 < temp_celsius < 150:  # More realistic CPU temp range
                                cpu_temps.append(round(temp_celsius, 1))
                        except ValueError:
                            continue
                
                if cpu_temps:
                    return max(cpu_temps)  # Return highest CPU temperature
            
            # Fallback: try any temperature sensor if no CPU-specific ones found
            ps_command = "Get-WmiObject -Namespace 'root\\LibreHardwareMonitor' -Class Sensor | Where-Object {$_.SensorType -eq 'Temperature'} | Select-Object Name, Value"
            result = subprocess.run([
                'powershell', '-Command', ps_command
            ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                temperatures = []
                for line in lines:
                    if 'Name' in line and 'Value' in line:
                        continue  # Skip header
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        try:
                            temp_celsius = float(parts[-1])  # Value is usually last
                            if 20 < temp_celsius < 150:  # More realistic temperature range
                                temperatures.append(round(temp_celsius, 1))
                        except ValueError:
                            continue
                
                if temperatures:
                    return max(temperatures)  # Return highest temperature
            return None
        except Exception as e:
            LoggingService.LogInfo(f"PowerShell LibreHardwareMonitor WMI failed: {e}", "SystemMonitoringService", "_TryLibreHardwareMonitorWmi")
            return None
    
    def _TryLibreHardwareMonitorDetailed(self) -> Optional[Dict[str, Any]]:
        """Try LibreHardwareMonitor WMI namespace for detailed temperature information."""
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
                        
                        # Skip if value is not a valid number (e.g., "-----")
                        if temp_str == "-----" or not (temp_str.replace('.', '').replace('-', '').isdigit()):
                            continue
                        
                        temp_celsius = float(temp_str)
                        
                        # Everything before the last part is the sensor name
                        name = ' '.join(parts[:-1])
                        
                        if 20 < temp_celsius < 150:  # Reasonable temperature range
                            sensors[name] = round(temp_celsius, 1)
                            
                            # Extract core temperatures - try multiple naming patterns
                            # Patterns we might see:
                            # "CPU Core #0", "CPU Core #1", "Core #0", "CPU Core 0", "Core 0"
                            # "CPU Core Temperature #0", "CPU Package", etc.
                            core_number = None
                            
                            # Skip package and distance sensors
                            if 'Distance to TjMax' in name or 'Package' in name:
                                pass
                            else:
                                # Try pattern: "CPU Core #0" or "Core #0"
                                core_match = re.search(r'(?:CPU\s+)?Core\s*#\s*(\d+)', name, re.IGNORECASE)
                                if core_match:
                                    core_number = int(core_match.group(1))
                                else:
                                    # Try pattern: "CPU Core 0" or "Core 0" (without #)
                                    alt_match = re.search(r'(?:CPU\s+)?Core\s+(\d+)', name, re.IGNORECASE)
                                    if alt_match:
                                        core_number = int(alt_match.group(1))
                                    else:
                                        # Try pattern: "CPU Core Temperature #0"
                                        temp_match = re.search(r'Core\s+(?:Temperature\s+)?#?\s*(\d+)', name, re.IGNORECASE)
                                        if temp_match:
                                            core_number = int(temp_match.group(1))
                                
                                if core_number is not None:
                                    # LibreHardwareMonitor reports cores as 1-based (1-24)
                                    # Map to 0-based (0-23) for consistency with psutil and display
                                    core_number_0_based = core_number - 1
                                    core_temps[core_number_0_based] = round(temp_celsius, 1)
                                    LoggingService.LogInfo(f"Found core {core_number_0_based} temperature: {temp_celsius}°C (sensor: {name}, LibreHardwareMonitor core #{core_number})", "SystemMonitoringService", "_TryLibreHardwareMonitorDetailed")
                                    
                    except (ValueError, AttributeError) as e:
                        LoggingService.LogInfo(f"Error parsing sensor data: {line}, error: {e}", "SystemMonitoringService", "_TryLibreHardwareMonitorDetailed")
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
                        LoggingService.LogInfo(f"Found {len(core_temps)} core temperatures: {sorted(core_temps.keys())}", "SystemMonitoringService", "_TryLibreHardwareMonitorDetailed")
                        # Sort by core number to ensure consistent ordering
                        for core_number in sorted(core_temps.keys()):
                            cores.append({
                                "Core": core_number,  # Use 0-based core number (0-23) mapped from LibreHardwareMonitor's 1-24
                                "Temperature": core_temps[core_number]
                            })
                        
                        # Find max and average core temperatures
                        max_temp = max(core_temps.values())
                        avg_temp = sum(core_temps.values()) / len(core_temps)
                    else:
                        LoggingService.LogInfo(f"No core temperatures found in sensors. Available sensors: {list(sensors.keys())[:10]}...", "SystemMonitoringService", "_TryLibreHardwareMonitorDetailed")
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
            LoggingService.LogInfo(f"PowerShell LibreHardwareMonitor detailed failed: {e}", "SystemMonitoringService", "_TryLibreHardwareMonitorDetailed")
            return None
    
    def _TryOpenHardwareMonitorDetailed(self) -> Optional[Dict[str, Any]]:
        """Try OpenHardwareMonitor WMI namespace for detailed temperature information."""
        # Placeholder - implement if needed
        return None
    
    def _TryHWiNFO64Detailed(self) -> Optional[Dict[str, Any]]:
        """Try HWiNFO64 WMI namespace for detailed temperature information."""
        # Placeholder - implement if needed
        return None
    
    def _GetCpuTemperatureUnix(self) -> Optional[float]:
        """Get CPU temperature on Unix-like systems."""
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
        """Get basic system information."""
        try:
            return {
                "Cores": psutil.cpu_count(),
                "Platform": self.Platform,
                "CpuTemperatureAvailable": self.CpuTemperatureAvailable
            }
        except Exception as e:
            LoggingService.LogException(f"Error getting system info: {e}", e, "SystemMonitoringService", "GetSystemInfo")
            return {"Cores": 0, "Platform": self.Platform, "CpuTemperatureAvailable": False}

# Global instance
SystemMonitoringServiceInstance = SystemMonitoringService()
