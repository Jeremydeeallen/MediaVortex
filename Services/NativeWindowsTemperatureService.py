"""
Native Windows Temperature Service
Uses only Windows built-in APIs - no external libraries or DLLs
"""

import ctypes
import platform
from typing import Dict, Any, Optional
from Services.LoggingService import LoggingService

class NativeWindowsTemperatureService:
    """Service for reading CPU temperatures using only Windows built-in APIs."""
    
    def __init__(self):
        self.Platform = platform.system()
        self.IsAvailable = False
        self._TestAvailability()
    
    def _TestAvailability(self):
        """Test if native temperature reading is available."""
        try:
            if self.Platform == "Windows":
                # Try WMI first (built into Windows)
                temp = self._TryWmiThermalZone()
                if temp is not None:
                    self.IsAvailable = True
                    LoggingService.LogInfo("NativeWindowsTemperatureService: WMI thermal zones available", "NativeWindowsTemperatureService", "_TestAvailability")
        except Exception as e:
            LoggingService.LogInfo(f"NativeWindowsTemperatureService not available: {e}", "NativeWindowsTemperatureService", "_TestAvailability")
            self.IsAvailable = False
    
    def _TryWmiThermalZone(self) -> Optional[float]:
        """Try WMI MSAcpi_ThermalZoneTemperature (built into Windows)."""
        try:
            import subprocess
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
            LoggingService.LogInfo(f"WMI thermal zone failed: {e}", "NativeWindowsTemperatureService", "_TryWmiThermalZone")
            return None
    
    def GetCpuTemperatures(self) -> Optional[Dict[str, Any]]:
        """
        Get CPU temperatures using only Windows built-in methods.
        
        NOTE: Windows does not natively expose per-core temperatures.
        This method can only get package/overall CPU temperature via WMI.
        Per-core temperatures require:
        1. Hardware/BIOS support that exposes them via WMI
        2. Or external monitoring software (which we're avoiding)
        3. Or manufacturer-specific drivers/APIs
        
        Returns package temperature only - cores will be None.
        """
        if not self.IsAvailable:
            return None
        
        try:
            package_temp = self._TryWmiThermalZone()
            
            if package_temp is not None:
                # Windows doesn't expose per-core temps natively
                # We can only return package temperature
                return {
                    "Package": package_temp,
                    "Max": package_temp,
                    "Average": package_temp,
                    "Cores": []  # Empty - Windows doesn't provide this
                }
            
            return None
        except Exception as e:
            LoggingService.LogException(f"Error getting CPU temperatures: {e}", e, "NativeWindowsTemperatureService", "GetCpuTemperatures")
            return None

# Global instance
NativeWindowsTemperatureServiceInstance = NativeWindowsTemperatureService()

