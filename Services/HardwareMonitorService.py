"""
Hardware Monitor Service using LibreHardwareMonitorLib.dll
Provides direct hardware access without requiring external software to run
"""

import sys
import os
from typing import Dict, Any, Optional, List
from Services.LoggingService import LoggingService

class HardwareMonitorService:
    """Service for monitoring hardware using LibreHardwareMonitorLib.dll via pythonnet."""
    
    def __init__(self):
        self.Computer = None
        self.IsInitialized = False
        self._Initialize()
    
    def _Initialize(self):
        """Initialize the LibreHardwareMonitor library."""
        try:
            import clr  # pythonnet
            
            # Try to find LibreHardwareMonitorLib.dll
            # Common locations:
            dll_paths = [
                r"C:\Program Files\LibreHardwareMonitor\LibreHardwareMonitorLib.dll",
                r"C:\Program Files (x86)\LibreHardwareMonitor\LibreHardwareMonitorLib.dll",
                os.path.join(os.path.dirname(__file__), "LibreHardwareMonitorLib.dll"),
                os.path.join(os.path.dirname(os.path.dirname(__file__)), "LibreHardwareMonitorLib.dll"),
            ]
            
            dll_found = False
            for dll_path in dll_paths:
                if os.path.exists(dll_path):
                    clr.AddReference(dll_path)
                    dll_found = True
                    LoggingService.LogInfo(f"Loaded LibreHardwareMonitorLib.dll from: {dll_path}", "HardwareMonitorService", "_Initialize")
                    break
            
            if not dll_found:
                LoggingService.LogWarning("LibreHardwareMonitorLib.dll not found. Please download from: https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases", "HardwareMonitorService", "_Initialize")
                LoggingService.LogWarning("Extract LibreHardwareMonitorLib.dll from the release and place it in the project directory or Program Files", "HardwareMonitorService", "_Initialize")
                return
            
            # Import the .NET types
            from LibreHardwareMonitor.Hardware import Computer, IHardware, ISensor, SensorType
            
            # Create computer instance and enable CPU monitoring
            self.Computer = Computer()
            self.Computer.IsCpuEnabled = True
            self.Computer.IsGpuEnabled = False
            self.Computer.IsMemoryEnabled = False
            self.Computer.IsMainboardEnabled = False
            self.Computer.IsControllerEnabled = False
            self.Computer.IsNetworkEnabled = False
            self.Computer.IsStorageEnabled = False
            
            # Open connection to hardware
            self.Computer.Open()
            self.IsInitialized = True
            
            LoggingService.LogInfo("HardwareMonitorService initialized successfully", "HardwareMonitorService", "_Initialize")
            
        except ImportError:
            LoggingService.LogWarning("pythonnet (clr) not installed. Install with: pip install pythonnet", "HardwareMonitorService", "_Initialize")
        except Exception as e:
            LoggingService.LogException(f"Error initializing HardwareMonitorService: {e}", e, "HardwareMonitorService", "_Initialize")
            self.IsInitialized = False
    
    def GetCpuCoreTemperatures(self) -> Optional[Dict[str, Any]]:
        """Get CPU core temperatures directly from hardware."""
        if not self.IsInitialized or not self.Computer:
            return None
        
        try:
            from LibreHardwareMonitor.Hardware import SensorType
            
            cores = {}
            package_temp = None
            all_temps = []
            
            # Update sensors
            for hardware in self.Computer.Hardware:
                hardware.Update()
                
                for sensor in hardware.Sensors:
                    if sensor.SensorType == SensorType.Temperature:
                        sensor_name = sensor.Name
                        sensor_value = sensor.Value
                        
                        if sensor_value is None:
                            continue
                        
                        temp_celsius = float(sensor_value)
                        
                        # Check if this is a core temperature
                        core_number = self._ExtractCoreNumber(sensor_name)
                        
                        if core_number is not None:
                            cores[core_number] = round(temp_celsius, 1)
                            all_temps.append(temp_celsius)
                            LoggingService.LogInfo(f"Core {core_number}: {temp_celsius}°C (sensor: {sensor_name})", "HardwareMonitorService", "GetCpuCoreTemperatures")
                        elif 'Package' in sensor_name or 'CPU Package' in sensor_name:
                            package_temp = round(temp_celsius, 1)
                            LoggingService.LogInfo(f"Package temp: {temp_celsius}°C", "HardwareMonitorService", "GetCpuCoreTemperatures")
            
            if not cores and not package_temp:
                return None
            
            # If no package temp found, use max core temp
            if package_temp is None and all_temps:
                package_temp = max(all_temps)
            
            # Create core list sorted by core number
            core_list = []
            for core_num in sorted(cores.keys()):
                core_list.append({
                    "Core": core_num,
                    "Temperature": cores[core_num]
                })
            
            max_temp = max(all_temps) if all_temps else package_temp
            avg_temp = sum(all_temps) / len(all_temps) if all_temps else package_temp
            
            return {
                "Package": package_temp,
                "Max": round(max_temp, 1) if max_temp else None,
                "Average": round(avg_temp, 1) if avg_temp else None,
                "Cores": core_list
            }
            
        except Exception as e:
            LoggingService.LogException(f"Error getting CPU temperatures: {e}", e, "HardwareMonitorService", "GetCpuCoreTemperatures")
            return None
    
    def _ExtractCoreNumber(self, sensor_name: str) -> Optional[int]:
        """Extract core number from sensor name."""
        try:
            import re
            # Try various patterns
            patterns = [
                r'Core\s*#?\s*(\d+)',  # "Core #0", "Core 0"
                r'CPU\s+Core\s*#?\s*(\d+)',  # "CPU Core #0"
                r'(\d+)',  # Just a number
            ]
            
            for pattern in patterns:
                match = re.search(pattern, sensor_name, re.IGNORECASE)
                if match:
                    core_num = int(match.group(1))
                    # Validate it's a reasonable core number (0-31 for most CPUs)
                    if 0 <= core_num <= 31:
                        return core_num
            
            return None
        except Exception:
            return None
    
    def Close(self):
        """Close hardware connections."""
        if self.Computer:
            try:
                self.Computer.Close()
                self.IsInitialized = False
                LoggingService.LogInfo("HardwareMonitorService closed", "HardwareMonitorService", "Close")
            except Exception as e:
                LoggingService.LogException(f"Error closing HardwareMonitorService: {e}", e, "HardwareMonitorService", "Close")

# Global instance
HardwareMonitorServiceInstance = HardwareMonitorService()

