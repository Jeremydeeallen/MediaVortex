"""
Pure Windows Temperature Service - NO External Dependencies
Uses only built-in Windows APIs and standard Python libraries
"""

import subprocess
import platform
from typing import Dict, Any, Optional
from Services.LoggingService import LoggingService

class PureWindowsTemperatureService:
    """
    Service for reading CPU temperatures using ONLY Windows built-in methods.
    
    LIMITATION: Windows does NOT provide per-core temperatures natively.
    This service can only provide package/overall CPU temperature.
    
    For per-core temperatures, you MUST use external libraries/hardware access.
    """
    
    def __init__(self):
        self.Platform = platform.system()
        self.IsAvailable = False
        self._TestAvailability()
    
    def _TestAvailability(self):
        """Test if temperature reading is available."""
        try:
            if self.Platform == "Windows":
                temp = self._TryWmiThermalZone()
                if temp is not None:
                    self.IsAvailable = True
                    LoggingService.LogInfo("PureWindowsTemperatureService: WMI thermal zones available", "PureWindowsTemperatureService", "_TestAvailability")
                else:
                    LoggingService.LogInfo("PureWindowsTemperatureService: No WMI thermal zones found", "PureWindowsTemperatureService", "_TestAvailability")
        except Exception as e:
            LoggingService.LogInfo(f"PureWindowsTemperatureService not available: {e}", "PureWindowsTemperatureService", "_TestAvailability")
            self.IsAvailable = False
    
    def _TryWmiThermalZone(self) -> Optional[float]:
        """Get package temperature via WMI (Windows built-in only)."""
        try:
            ps_command = "Get-WmiObject -Namespace 'root\\wmi' -Class MSAcpi_ThermalZoneTemperature | Select-Object -ExpandProperty CurrentTemperature"
            result = subprocess.run([
                'powershell', '-Command', ps_command
            ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                temperatures = []
                for line in lines:
                    line = line.strip()
                    if line and line.isdigit():
                        # WMI returns temperature in tenths of Kelvin
                        temp_kelvin = int(line) / 10.0
                        temp_celsius = temp_kelvin - 273.15
                        if 0 < temp_celsius < 150:
                            temperatures.append(round(temp_celsius, 1))
                
                if temperatures:
                    return max(temperatures)
            return None
        except Exception as e:
            LoggingService.LogInfo(f"WMI thermal zone failed: {e}", "PureWindowsTemperatureService", "_TryWmiThermalZone")
            return None
    
    def GetCpuTemperatures(self) -> Optional[Dict[str, Any]]:
        """
        Get CPU temperatures using ONLY Windows built-in APIs.
        
        WARNING: Windows does not provide per-core temperatures.
        This will only return package temperature.
        All cores will be returned with Temperature: None (N/A).
        """
        if not self.IsAvailable:
            return None
        
        try:
            package_temp = self._TryWmiThermalZone()
            
            if package_temp is not None:
                # Get core count for display
                try:
                    import psutil
                    total_cores = psutil.cpu_count(logical=False) or psutil.cpu_count()
                except (ImportError, AttributeError, OSError):
                    total_cores = 24  # Default for i9-14900KF
                
                # Create cores list with N/A (Windows doesn't provide per-core temps)
                cores = []
                for core_num in range(total_cores):
                    cores.append({
                        "Core": core_num,
                        "Temperature": None  # Not available from Windows
                    })
                
                return {
                    "Package": package_temp,
                    "Max": package_temp,
                    "Average": package_temp,
                    "Cores": cores
                }
            
            return None
        except Exception as e:
            LoggingService.LogException(f"Error getting CPU temperatures: {e}", e, "PureWindowsTemperatureService", "GetCpuTemperatures")
            return None

# Global instance
PureWindowsTemperatureServiceInstance = PureWindowsTemperatureService()

